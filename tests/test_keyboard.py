"""The hotkey text and the recorder are pure logic: no key is ever pressed here."""

import pytest

from cotorreando import keyboard
from cotorreando.keyboard import HotkeyRecorder, hotkey_from_vks, hotkey_label, hotkey_valid, parse_hotkey

LCTRL, RCTRL, CTRL = 0xA2, 0xA3, 0x11
LSHIFT, LALT, LWIN, RWIN = 0xA0, 0xA4, 0x5B, 0x5C
F5, SPACE, ESC, A = 0x74, 0x20, 0x1B, ord("A")


@pytest.mark.parametrize("vks, text", [
    ({LWIN, LCTRL}, "ctrl+win"),                       # canonical order, whatever the input
    ({RWIN, RCTRL, CTRL}, "ctrl+win"),                 # left, right and generic are one key
    ({LSHIFT, LALT, LCTRL, LWIN, A}, "ctrl+alt+shift+win+a"),
    ({F5}, "f5"),
    ({LCTRL, SPACE}, "ctrl+space"),
    ({LCTRL, 0x41, 0x42}, "ctrl+a"),                   # one plain key only: the lowest
    ({LCTRL, 0xE8, 0x70 - 0x10}, "ctrl"),              # keys a hotkey cannot use are ignored
    (set(), ""),
])
def test_hotkey_from_vks(vks, text):
    assert hotkey_from_vks(vks) == text


@pytest.mark.parametrize("text", ["ctrl+win", "ctrl+alt+shift+win+a", "f5", "ctrl+space", "alt+9", "pause",
                                  "ctrl+f24"])
def test_text_round_trips_through_parse_hotkey(text):
    groups = parse_hotkey(text)
    vks = {sorted(g)[0] for g in groups}
    assert hotkey_from_vks(vks) == text


@pytest.mark.parametrize("text, ok", [
    ("ctrl+win", True), ("ctrl+a", True), ("alt+space", True), ("win+f1", True), ("ctrl+shift", True),
    ("f5", True), ("f24", True), ("pause", True),
    ("ctrl", False), ("win", False), ("shift", False), ("shift+a", False), ("shift+f5", False),
    ("a", False), ("space", False), ("", False), ("nonsense", False), ("ctrl+nonsense", False),
])
def test_hotkey_valid(text, ok):
    assert hotkey_valid(text) is ok


@pytest.mark.parametrize("text, label", [
    ("ctrl+win", "Ctrl+Win"), ("f5", "F5"), ("ctrl+alt+a", "Ctrl+Alt+A"), ("ctrl+space", "Ctrl+Space"),
    ("pause", "Pause"), ("not+a+hotkey", "not+a+hotkey"),
])
def test_hotkey_label(text, label):
    assert hotkey_label(text) == label


def run(rec, *snapshots):
    return [rec.feed(s) for s in snapshots]


def test_recorder_ends_when_everything_is_released_and_keeps_the_biggest_set():
    rec = HotkeyRecorder()
    states = run(rec, set(), {LCTRL}, {LCTRL, LWIN}, {LWIN}, set())
    assert states == ["idle", "live", "live", "live", "done"]
    assert rec.result == "ctrl+win"


def test_recorder_tie_keeps_the_first_set():
    rec = HotkeyRecorder()
    run(rec, set(), {LCTRL}, {A}, set())
    assert rec.result == ""                      # a lone ctrl is invalid...
    rec = HotkeyRecorder()
    states = run(rec, set(), {A, LCTRL}, {F5}, set())
    assert states[-1] == "done" and rec.result == "ctrl+a"


def test_recorder_live_text_follows_what_is_down():
    rec = HotkeyRecorder()
    run(rec, set(), {LCTRL, LWIN})
    assert rec.text == "ctrl+win"


def test_recorder_escape_cancels():
    rec = HotkeyRecorder()
    assert run(rec, set(), {ESC}) == ["idle", "cancel"]


def test_recorder_invalid_listens_again():
    rec = HotkeyRecorder()
    states = run(rec, set(), {LSHIFT, A}, set(), {LCTRL, F5}, set())
    assert states == ["idle", "live", "invalid", "live", "done"] and rec.result == "ctrl+f5"


def test_recorder_ignores_keys_already_down_when_it_starts():
    rec = HotkeyRecorder()
    states = run(rec, {SPACE}, {SPACE}, set(), {LCTRL, A}, set())
    assert states == ["idle", "idle", "idle", "live", "done"] and rec.result == "ctrl+a"


def test_recorder_ignores_unknown_keys():
    rec = HotkeyRecorder()
    assert run(rec, {0xE8}, set(), {0xE8}) == ["idle", "idle", "idle"]


def test_hotkey_paused_stops_the_monitor_and_releases_the_hotkey(monkeypatch):
    events = []
    monitor = keyboard.KeyboardMonitor("ctrl+win", lambda: events.append("down"), lambda: events.append("up"))
    monkeypatch.setattr(keyboard, "_is_down", lambda vk: True)
    monkeypatch.setattr(keyboard, "cancel_start_menu", lambda: None)
    monitor._check_hotkey()
    keyboard.hotkey_paused.set()
    try:
        monitor._check_hotkey()
        monitor._check_hotkey()
    finally:
        keyboard.hotkey_paused.clear()
    assert events == ["down", "up"]


@pytest.fixture
def held(monkeypatch):
    """A fake keyboard: ``held`` is the set of virtual keys currently down."""
    keys = set()
    monkeypatch.setattr(keyboard, "_is_down", lambda vk: vk in keys)
    monkeypatch.setattr(keyboard, "cancel_start_menu", lambda: None)
    keyboard.hotkey_paused.clear()
    yield keys
    keyboard.hotkey_paused.clear()


CTRL, WIN, F1 = 0x11, 0x5B, 0x70


def test_hotkey_held_through_a_pause_does_not_fire_until_released(held):
    events = []
    monitor = keyboard.KeyboardMonitor("ctrl+win", lambda: events.append("down"), lambda: events.append("up"))
    held.update({CTRL, WIN})
    keyboard.hotkey_paused.set()
    monitor._check_hotkey()
    keyboard.hotkey_paused.clear()
    monitor._check_hotkey()
    monitor._check_hotkey()
    assert events == []
    held.clear()
    monitor._check_hotkey()
    held.update({CTRL, WIN})
    monitor._check_hotkey()
    assert events == ["down"]


def test_set_hotkey_with_its_keys_held_does_not_fire(held):
    events = []
    monitor = keyboard.KeyboardMonitor("ctrl+win", lambda: events.append("down"), lambda: events.append("up"))
    held.update({CTRL, 0x70})
    monitor.set_hotkey("ctrl+f1")
    monitor._check_hotkey()
    assert events == []
    held.clear()
    monitor._check_hotkey()
    held.update({CTRL, F1})
    monitor._check_hotkey()
    assert events == ["down"]


def test_push_to_talk_held_across_a_pause_gives_one_down_and_one_up(held):
    events = []
    monitor = keyboard.KeyboardMonitor("ctrl+win", lambda: events.append("down"), lambda: events.append("up"))
    held.update({CTRL, WIN})
    monitor._check_hotkey()
    keyboard.hotkey_paused.set()
    monitor._check_hotkey()
    keyboard.hotkey_paused.clear()
    monitor._check_hotkey()
    held.clear()
    monitor._check_hotkey()
    assert events == ["down", "up"]
