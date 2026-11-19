"""The focused field (UI Automation, on a fake COM tree) and the incremental correction of dictation.

The correction tests run the real ``Cotorreando._recognizer`` and ``_rewrite`` against a fake keyboard
that edits a string, so the text on "screen" is checked after every step, and every backspace is counted.
"""

import queue
import random
import string
import sys
import threading
import time
import types
from concurrent.futures import Future
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from cotorreando import app, keyboard
from cotorreando.config import Settings
from cotorreando.field import MAX_CHARS, FieldReader, Snapshot

ENDPOINT_END, ENDPOINT_START = 1, 0

# -- a fake UI Automation tree -----------------------------------------------------------

uia = types.ModuleType("UIAutomationClient")
uia.UIA_TextPatternId, uia.UIA_ValuePatternId = 10, 11
uia.IUIAutomationTextPattern = uia.IUIAutomationValuePattern = object
uia.CUIAutomation = uia.IUIAutomation = object


class FakeRange:
    def __init__(self, doc, start, end):
        self.doc, self.start, self.end = doc, start, end

    def GetText(self, n):  # like UI Automation: the first n characters of the range
        return self.doc.text[self.start : self.end][:n]

    def Clone(self):
        return FakeRange(self.doc, self.start, self.end)

    def MoveEndpointByRange(self, endpoint, other, other_endpoint):
        assert other_endpoint == ENDPOINT_START
        if endpoint == ENDPOINT_END:
            self.end = other.start
        else:
            self.start = other.start

    def MoveEndpointByUnit(self, endpoint, unit, count):  # character units only; stops at the document start
        assert endpoint == ENDPOINT_START and unit == 0
        self.start = max(0, self.start + count)
        return count


class FakeSelection:
    def __init__(self, doc, caret, length):
        self.Length, self._caret, self._doc = length, caret, doc

    def GetElement(self, i):
        return FakeRange(self._doc, self._caret, self._caret)


class FakeTextPattern:
    def __init__(self, text, caret, selection_length):
        self.text = text
        self.DocumentRange = FakeRange(self, 0, len(text))
        self._selection = None if caret is None else FakeSelection(self, caret, selection_length)

    def QueryInterface(self, _iface):
        return self

    def GetSelection(self):
        return self._selection


class FakeValuePattern:
    def __init__(self, value):
        self.CurrentValue = value

    def QueryInterface(self, _iface):
        return self


class FakeElement:
    def __init__(self, password=False, text=None, caret=None, selection_length=1, value=None):
        self.CurrentIsPassword = password
        self._patterns = {}
        if text is not None:
            self._patterns[uia.UIA_TextPatternId] = FakeTextPattern(text, caret, selection_length)
        if value is not None:
            self._patterns[uia.UIA_ValuePatternId] = FakeValuePattern(value)

    def GetCurrentPattern(self, pattern_id):
        return self._patterns.get(pattern_id)


class FakeAutomation:
    def __init__(self):
        self.focused = None
        self.fail = False
        self.gate = None  # when set, GetFocusedElement waits on it: an application that hangs

    def GetFocusedElement(self):
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            raise OSError("window closed")
        return self.focused

    def CompareElements(self, a, b):
        return a is b


@pytest.fixture
def automation(monkeypatch):
    """Route ``import comtypes`` to the fakes, so the reader's real worker thread runs against them."""
    auto = FakeAutomation()
    comtypes = types.ModuleType("comtypes")
    comtypes.CoInitialize = lambda: None
    client = types.ModuleType("comtypes.client")
    client.GetModule = lambda name: None
    client.CreateObject = lambda cls, interface: auto
    gen = types.ModuleType("comtypes.gen")
    gen.UIAutomationClient = uia
    comtypes.client, comtypes.gen = client, gen
    for name, module in {
        "comtypes": comtypes,
        "comtypes.client": client,
        "comtypes.gen": gen,
        "comtypes.gen.UIAutomationClient": uia,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return auto


@pytest.fixture
def reader(automation):
    r = FieldReader()
    for _ in range(500):  # the worker thread must have taken the fakes before they are removed
        if hasattr(r, "automation"):
            break
        time.sleep(0.01)
    assert hasattr(r, "automation")
    return r


def test_snapshot_reads_the_text_and_what_precedes_the_caret(reader, automation):
    el = FakeElement(text="Hola mundo", caret=4)
    automation.focused = el
    snap = reader.snapshot(timeout=2)
    assert snap.element is el and not snap.password
    assert snap.text == "Hola mundo" and snap.before == "Hola"


def test_snapshot_without_a_selection_does_not_know_the_caret(reader, automation):
    automation.focused = FakeElement(text="Hola", caret=None)
    assert reader.snapshot(timeout=2).before is None


def test_snapshot_with_an_empty_selection_does_not_know_the_caret(reader, automation):
    automation.focused = FakeElement(text="Hola", caret=2, selection_length=0)
    assert reader.snapshot(timeout=2).before is None


def test_password_field_gives_no_text_at_all(reader, automation):
    automation.focused = FakeElement(password=True, text="secreto", caret=3)
    snap = reader.snapshot(timeout=2)
    assert snap.password and snap.text == "" and snap.before is None


def test_value_pattern_is_used_when_there_is_no_text_pattern(reader, automation):
    automation.focused = FakeElement(value="campo")
    snap = reader.snapshot(timeout=2)
    assert snap.text == "campo" and snap.before is None


def test_element_that_exposes_nothing_gives_empty_text(reader, automation):
    automation.focused = FakeElement()
    assert reader.snapshot(timeout=2) == Snapshot(automation.focused)


def test_value_is_cut_to_the_maximum_length(reader, automation):
    automation.focused = FakeElement(value="x" * (MAX_CHARS + 5000))
    assert len(reader.snapshot(timeout=2).text) == MAX_CHARS


def test_read_if_focused_reads_only_the_field_that_has_focus(reader, automation):
    el = FakeElement(text="Hola")
    automation.focused = el
    assert reader.read_if_focused(el, timeout=2) == "Hola"


def test_read_if_focused_reads_nothing_once_the_user_has_left_the_field(reader, automation):
    el = FakeElement(text="Hola")
    automation.focused = FakeElement(text="otro campo")
    assert reader.read_if_focused(el, timeout=2) is None


def test_read_if_focused_never_returns_a_password(reader, automation):
    el = FakeElement(password=True, text="secreto")
    automation.focused = el
    assert reader.read_if_focused(el, timeout=2) is None


def test_an_application_that_fails_gives_no_context_and_the_worker_survives(reader, automation):
    automation.fail = True
    assert reader.snapshot(timeout=2) is None
    automation.fail = False
    automation.focused = FakeElement(text="de nuevo", caret=2)
    assert reader.snapshot(timeout=2).before == "de"


def test_a_hanging_application_times_out_and_jobs_do_not_pile_up(reader, automation):
    gate = threading.Event()
    automation.gate = gate
    automation.focused = FakeElement(text="Hola")
    started = time.monotonic()
    assert reader.snapshot(timeout=0.05) is None  # the caller waits only briefly
    assert reader.snapshot(timeout=0.05) is None  # busy: refused at once, nothing queued
    assert time.monotonic() - started < 1.5
    assert reader.jobs.qsize() <= 1
    automation.gate = None
    gate.set()
    for _ in range(500):
        if not reader.busy and reader.jobs.qsize() == 0:
            break
        time.sleep(0.01)
    assert reader.snapshot(timeout=2).text == "Hola"


def test_submit_refuses_to_queue_behind_a_pending_job():
    r = object.__new__(FieldReader)
    r.jobs, r.busy = queue.Queue(), False
    r.jobs.put(("pending", Future()))
    assert r._submit(lambda: 1) is None
    r.jobs.get()
    assert isinstance(r._submit(lambda: 1), Future) and r.jobs.qsize() == 1


def test_without_ui_automation_every_question_gets_no_answer(monkeypatch):
    monkeypatch.setitem(sys.modules, "comtypes", None)  # importing it fails, as on a system without it
    r = FieldReader()
    assert r.snapshot(timeout=2) is None
    assert r.read_if_focused(object(), timeout=2) is None
    assert not hasattr(r, "automation")


def test_before_the_caret_is_the_text_next_to_it_in_long_documents(reader, automation):
    rng = random.Random(3)
    text = "".join(rng.choice(string.ascii_lowercase) for _ in range(25000))
    caret = 24000
    automation.focused = FakeElement(text=text, caret=caret)
    snap = reader.snapshot(timeout=2)
    assert snap.before.endswith(text[caret - 100 : caret])


# -- incremental correction -------------------------------------------------------------


class Screen:
    """The text of the focused field: backspaces remove the last character, Unicode keys append."""

    def __init__(self):
        self.text, self.backspaces, self.sends = "", 0, 0

    def send(self, inputs):
        self.sends += 1
        for item in inputs:
            k = item.ki
            if k.dwFlags & keyboard.KEYEVENTF_KEYUP:
                continue
            if k.wVk == keyboard.VK_BACK:
                self.text, self.backspaces = self.text[:-1], self.backspaces + 1
            elif k.wVk == keyboard.VK_RETURN:
                self.text += "\n"
            elif k.dwFlags & keyboard.KEYEVENTF_UNICODE:
                self.text += chr(k.wScan)


@pytest.fixture
def screen(monkeypatch):
    s = Screen()
    monkeypatch.setattr(keyboard, "send", s.send)
    monkeypatch.setattr(app, "ours_in_front", lambda: False)
    monkeypatch.setattr(app, "foreground", lambda: WINDOW["hwnd"])
    WINDOW["hwnd"] = 1
    return s


WINDOW = {"hwnd": 1}


class Script:
    """What the recognizer hears: one (final, tentative) pair per streamed audio step, then the finish text."""

    feeds: list = []
    finish_text = ""


class ScriptedStream:
    def __init__(self, model):
        self.trace, self.tail = [], ""

    def feed(self, audio):
        final, self.tail = Script.feeds.pop(0)
        return final

    def finish(self):
        self.tail = ""
        return Script.finish_text


class StopJobs(Exception):
    pass


class Jobs:
    """Hands out queued jobs; a job may be a callable that acts on the app first. Then the loop ends."""

    def __init__(self, items):
        self.items = list(items)

    def get(self):
        if not self.items:
            raise StopJobs
        item = self.items.pop(0)
        return item() if callable(item) else item


class FakeModel:
    closed = False

    def set_phrases(self, phrases):
        pass


class FakeLearner:
    def __init__(self):
        self.finished = []

    def begin(self, window):
        return None

    def bias_words(self, field):
        return {}

    def finish(self, typed, audio, trace, field):
        self.finished.append(typed)


class Holder:
    failed, available = False, True

    def __init__(self):
        self.model = FakeModel()  # one model for the whole session: a new one would cancel the utterance

    @contextmanager
    def using(self):
        yield self.model


class Dictation:
    """The recognizer's own methods, bound to a fake app state."""

    _fit = app.Cotorreando._fit
    _should_stream = app.Cotorreando._should_stream
    _rewrite = app.Cotorreando._rewrite
    _type = app.Cotorreando._type
    _apply_activation = app.Cotorreando._apply_activation
    _finish_utterance = app.Cotorreando._finish_utterance
    _recognizer = app.Cotorreando._recognizer

    def __init__(self, items, settings=None):
        self.s = settings or Settings()
        self.enabled = True
        self.holder, self.learner = Holder(), FakeLearner()
        self.keyboard = SimpleNamespace(last_click=0.0, last_typed=0.0)
        self.listener = SimpleNamespace(awake=True, wake=lambda: None)
        self.writing = SimpleNamespace(emit=lambda on: None)
        self.jobs = Jobs(items)
        self._tail, self._tail_since, self._tail_window = "", 0.0, 0
        self._typed, self._started, self._before = "", False, None


@pytest.fixture
def stream_class(monkeypatch):
    monkeypatch.setattr(app.asr, "Stream", ScriptedStream)
    Script.feeds, Script.finish_text = [], ""
    return Script


def audio(uid):
    return ("audio", uid, np.zeros(1600, np.float32))


def end(uid):
    return ("end", uid, None)


def then(action, job):
    """A job preceded by an action on the app, such as a click or a keystroke."""

    def run():
        action()
        return job

    return run


def run_recognizer(d):
    with pytest.raises(StopJobs):
        d._recognizer()


def test_only_the_last_words_are_corrected_and_the_final_ones_are_never_touched(screen, stream_class):
    stream_class.feeds = [("Hola", " mundo"), (" mundo", " cruel"), ("", " cruo")]
    stream_class.finish_text = " cruo"
    seen = []

    def mark(job):
        return then(lambda: seen.append(screen.text), job)

    d = Dictation([mark(audio(1)), mark(audio(1)), mark(audio(1)), mark(end(1))])
    run_recognizer(d)
    assert screen.text == "Hola mundo cruo "
    assert screen.backspaces == 2  # only the two letters of the tentative "cruel" that changed
    assert all(s.startswith("Hola mundo") for s in seen[1:])  # what was final never changed
    assert d.learner.finished == ["Hola mundo cruo "]  # the learner gets what was typed


def test_unchanged_tentative_text_sends_nothing(screen, stream_class):
    stream_class.feeds = [("Hola", " mundo"), ("", " mundo")]
    run_recognizer(Dictation([audio(1), audio(1)]))
    assert screen.text == "Hola mundo" and screen.sends == 1


def test_a_click_moves_the_caret_so_nothing_before_it_is_deleted(screen, stream_class):
    stream_class.feeds = [("Hola", " mundo"), (" que tal", "")]
    d = Dictation([audio(1), then(lambda: setattr(d.keyboard, "last_click", time.monotonic() + 1), audio(1))])
    run_recognizer(d)
    assert screen.backspaces == 0 and screen.text == "Hola mundo que tal"


def test_switching_windows_is_treated_as_a_moved_caret(screen, stream_class):
    stream_class.feeds = [("Hola", " mundo"), (" que tal", "")]

    def switch():
        WINDOW["hwnd"] = 2

    d = Dictation([audio(1), then(switch, audio(1))])
    run_recognizer(d)
    assert screen.backspaces == 0 and screen.text == "Hola mundo que tal"


def test_typing_drops_the_utterance_and_leaves_the_screen_as_it_is(screen, stream_class):
    stream_class.feeds = [("Hola", " mundo"), (" Adios", "")]
    d = Dictation(
        [
            audio(1),
            then(lambda: setattr(d.keyboard, "last_typed", time.monotonic()), audio(1)),  # the user types
            end(1),
            then(lambda: setattr(d.keyboard, "last_typed", 0.0), audio(2)),
            end(2),
        ]
    )
    run_recognizer(d)
    assert screen.backspaces == 0 and screen.text == "Hola mundo Adios"
    assert d.learner.finished == [" Adios"]  # the dropped utterance was never learnt from


def test_without_streaming_the_whole_utterance_is_typed_once_at_the_end(screen, stream_class):
    stream_class.feeds = [("Hola mundo", "")]
    d = Dictation([audio(1), audio(1), end(1)], Settings(streaming=False))
    run_recognizer(d)
    assert screen.text == "Hola mundo " and screen.backspaces == 0


def test_replace_text_removes_only_the_part_that_differs(screen):
    screen.text = "abc"
    keyboard.replace_text("abc", "abd")
    assert screen.text == "abd" and screen.backspaces == 1
    keyboard.replace_text("abd", "abd")
    assert screen.sends == 1  # nothing differs: no key is sent
