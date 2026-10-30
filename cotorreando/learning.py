"""What Cotorreando learns while you dictate: hesitations, corrections and replacements.

Audio only reaches the disk for a correction that was accepted; everything else is
forgotten when the utterance has been checked.
"""

from __future__ import annotations

import ctypes
import difflib
import logging
import re
import threading
import time
import unicodedata
from ctypes import wintypes
from dataclasses import dataclass

import numpy as np

from .field import FieldReader, Snapshot
from .vault import Vault

log = logging.getLogger(__name__)

SETTLE_S = 45                # corrections are looked for this long after dictating
LOW_PROBABILITY = 0.6
LOW_MARGIN = 0.3
MAX_HARD_WORDS = 500
MIN_KEPT = 0.6               # share of the dictated words that must still be in the field
MAX_CHANGED_WORDS = 3
MIN_SOUND_ALIKE = 0.5
RULE_AFTER = 2               # the same correction this many times becomes a replacement
MAX_FIELD_WORDS = 300
WORD = re.compile(r"\w[\w'’-]*")
SENTENCE_END = (".", "?", "!", "\n", "\r", ":")
OPENERS = (" ", "\t", "\n", "\r", "(", "[", "¿", "¡", '"', "'", "“", "«", "/")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if c.isalnum() or c.isspace())


def _sound(text: str) -> str:
    """A rough spelling-independent form, so that b/v, s/z/c or a silent h do not count."""
    text = _plain(text)
    for old, new in (("qu", "k"), ("ll", "y"), ("ch", "x"), ("ce", "se"), ("ci", "si"),
                     ("c", "k"), ("z", "s"), ("v", "b"), ("h", ""), ("w", "u")):
        text = text.replace(old, new)
    return "".join(c for i, c in enumerate(text) if i == 0 or c != text[i - 1])


def sound_alike(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, _sound(a), _sound(b)).ratio() >= MIN_SOUND_ALIKE


def find_corrections(typed: str, field: str) -> tuple[str, list[tuple[str, str]]] | None:
    """Compare what was dictated with what the field holds now.

    Returns the corrected utterance and its (old, new) pairs, or None when the text
    is gone or was rewritten. Added or deleted words are ignored: those are edits, not
    recognition errors, and so is anything that does not sound like what was dictated.
    """
    a, b = list(WORD.finditer(typed)), list(WORD.finditer(field))
    if not a:
        return None
    a_words, b_words = [_plain(m.group()) for m in a], [_plain(m.group()) for m in b]
    matcher = difflib.SequenceMatcher(None, a_words, b_words, autojunk=False)
    if sum(block.size for block in matcher.get_matching_blocks()) < MIN_KEPT * len(a_words):
        return None
    pairs, fixed, cursor = [], [], 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or i2 - i1 > MAX_CHANGED_WORDS or j2 - j1 > MAX_CHANGED_WORDS:
            continue
        old = typed[a[i1].start():a[i2 - 1].end()]
        new = field[b[j1].start():b[j2 - 1].end()]
        if not sound_alike(old, new):
            continue
        pairs.append((old, new))
        fixed += [typed[cursor:a[i1].start()], new]
        cursor = a[i2 - 1].end()
    return "".join(fixed) + typed[cursor:], pairs


def fit_start(text: str, before: str | None) -> str:
    """Spacing and capitals of a new utterance, given what precedes the caret."""
    if before is None or not text:
        return text
    if not before.strip() or before.rstrip(" ").endswith(SENTENCE_END):
        text = text[0].upper() + text[1:]
        return text if not before or before.endswith(OPENERS) else " " + text
    if text[1:2].islower():    # not an acronym
        text = text[0].lower() + text[1:]
    return text if before.endswith(OPENERS) else " " + text


def exe_name(window: int) -> str:
    """The executable that owns ``window``, in lower case."""
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid.value)    # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(wintypes.HANDLE(handle), 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))


@dataclass
class Pending:
    element: object
    typed: str
    audio: np.ndarray
    since: float


class Learner:
    def __init__(self, settings):
        self.s = settings
        self.vault = Vault()
        if self.vault.ready:
            self.vault.migrate_readings()
        self.vault.delete_older_than(settings.retention_days)
        self.reader = FieldReader()
        self.lock = threading.Lock()
        self.loaded = False          # the word lists can only be read with the password
        self.hard: dict = {}
        self.counts: dict = {}
        self.rules: dict = {}
        self.rule_pattern = None
        self.pending: list[Pending] = []
        threading.Thread(target=self._watch, daemon=True, name="corrections").start()

    # -- password -------------------------------------------------------------

    def unlock(self, password: str) -> None:
        """Raises WrongPassword. The caller locks the vault again when done with it."""
        self.vault.unlock(password)
        self.activate()

    def recover(self, code: str, new_password: str) -> None:
        """Raises WrongPassword."""
        self.vault.recover(code, new_password)
        self.activate()

    def activate(self) -> None:
        """The vault is unlocked: read the word lists and merge what the journal gathered."""
        if self.loaded:
            return
        self.hard = self.vault.load_private("hard_words", {})
        self.counts = self.vault.load_private("corrections", {})
        self.loaded = True
        events = self.vault.read_events()
        for event in events:
            self._apply(event)
        if events:
            self._save_lists()
        self.vault.clear_events()
        self._build_rules()

    def _apply(self, event: dict) -> None:
        if event["op"] == "correction":
            key = f"{_plain(event['old'])}|{event['new']}"
            self.counts[key] = self.counts.get(key, 0) + 1
            words = WORD.findall(event["new"])
        else:
            words = [event["word"]]
        for word in words:
            clean = _plain(word)
            if len(clean) >= 4:
                entry = self.hard.setdefault(clean, {"word": word.strip(".,;:?!¿¡"), "count": 0, "read": 0})
                entry["count"] += 1

    def _note(self, event: dict) -> None:
        """Learn from this now, or leave it sealed for when the lists can be read."""
        if self.loaded:
            self._apply(event)
            self._save_lists()
            self._build_rules()
        else:
            self.vault.add_event(event)

    def _save_lists(self) -> None:
        self._save_hard()
        self.vault.save_private("corrections", self.counts)

    # -- during an utterance --------------------------------------------------

    def allowed(self, window: int) -> bool:
        excluded = {name.strip().lower() for name in self.s.excluded_apps.split(",") if name.strip()}
        return not excluded or exe_name(window) not in excluded

    def begin(self, window: int) -> Snapshot | None:
        """The field being dictated into, or None if it cannot or must not be used."""
        if not self.s.learning or not self.vault.ready or not self.allowed(window):
            return None
        return self.reader.snapshot()

    def bias_words(self, snapshot: Snapshot | None) -> set[str]:
        words = self.vocabulary()
        if snapshot and snapshot.text and not snapshot.password:
            words |= {w.lower() for w in WORD.findall(snapshot.text)[-MAX_FIELD_WORDS:] if len(w) >= 4}
        return words

    def vocabulary(self) -> set[str]:
        return {w.lower() for rule in self.rules.values() for w in WORD.findall(rule) if len(w) >= 4}

    def apply_rules(self, text: str) -> str:
        if not self.rule_pattern:
            return text
        return self.rule_pattern.sub(lambda m: self.rules[_plain(m.group())], text)

    def finish(self, typed: str, audio: np.ndarray, trace: list, snapshot: Snapshot | None) -> None:
        """An utterance ended: note its hesitations and start watching for corrections."""
        if not self.s.learning or snapshot is None or snapshot.password or not typed.strip():
            return
        self._note_hesitations(trace)
        if snapshot.element is not None:
            with self.lock:
                self.pending.append(Pending(snapshot.element, typed, audio, time.monotonic()))

    def _note_hesitations(self, trace: list) -> None:
        word, unsure = "", False
        for piece, _, probability, margin in list(trace) + [(" ", 0, 1, 1)]:
            if piece.startswith(" ") and word:
                clean = _plain(word)
                if unsure and len(clean) >= 4 and clean.isalpha():
                    self._note({"op": "word", "word": word.strip()})
                word, unsure = "", False
            word += piece
            unsure = unsure or probability < LOW_PROBABILITY or margin < LOW_MARGIN

    def _save_hard(self) -> None:
        if len(self.hard) > MAX_HARD_WORDS:
            kept = sorted(self.hard.items(), key=lambda kv: -kv[1]["count"])[:MAX_HARD_WORDS]
            self.hard = dict(kept)
        self.vault.save_private("hard_words", self.hard)

    # -- corrections ----------------------------------------------------------

    def _watch(self) -> None:
        while True:
            time.sleep(5)
            with self.lock:
                now = time.monotonic()
                ready = [p for p in self.pending if now - p.since >= SETTLE_S]
                self.pending = [p for p in self.pending if now - p.since < SETTLE_S]
            for item in ready:
                try:
                    self._settle(item)
                except Exception:
                    log.exception("Could not check for corrections")

    def _settle(self, item: Pending) -> None:
        field = self.reader.reread(item.element)
        if not field:
            return
        found = find_corrections(item.typed, field)
        if not found or not found[1]:
            return
        text, pairs = found
        self.vault.add_record({"kind": "correction", "text": text.strip(), "old": item.typed.strip()}, item.audio)
        log.info("Correction kept (%d words changed)", len(pairs))
        for old, new in pairs:
            self.count_correction(old, new)

    def count_correction(self, old: str, new: str) -> None:
        self._note({"op": "correction", "old": old, "new": new})

    def forget_correction(self, old: str, new: str) -> None:
        """The audio did not back this correction up after all."""
        key = f"{_plain(old)}|{new}"
        if key in self.counts:
            self.counts[key] -= 1
            if self.counts[key] <= 0:
                del self.counts[key]
            self.vault.save_private("corrections", self.counts)
            self._build_rules()

    def _build_rules(self) -> None:
        rules = {}
        for key, count in self.counts.items():
            old, new = key.split("|", 1)
            if count >= RULE_AFTER:
                rules[old] = new
        self.rules = rules
        if rules:
            options = "|".join(sorted(map(re.escape, rules), key=len, reverse=True))
            self.rule_pattern = re.compile(rf"(?<!\w)(?:{options})(?!\w)", re.IGNORECASE)
        else:
            self.rule_pattern = None

    def words_to_practice(self, limit: int = 5) -> list[str]:
        waiting = [e for e in self.hard.values() if e["count"] >= 3 and e["read"] == 0]
        return [e["word"] for e in sorted(waiting, key=lambda e: -e["count"])[:limit]]

    def mark_practiced(self, word: str) -> None:
        entry = self.hard.get(_plain(word))
        if entry:
            entry["read"] += 1
            self._save_hard()
