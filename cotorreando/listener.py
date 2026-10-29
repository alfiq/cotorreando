"""Turns a stream of audio frames into utterances, according to the listening mode.

Modes
-----
open        Always listening; every utterance (split on pauses) is typed.
ptt         Push-to-talk; audio is recorded while the hotkey is held.
activation  Sleeps until woken by voice above the threshold or by the
            keyword, then dictates until ``session_timeout_s`` of silence.

The hotkey toggles the listener on and off in ``open`` and ``activation``.
"""

from __future__ import annotations

import collections
import time

import numpy as np

from .audio import RATE
from .vad import CHUNK, SileroVAD

PREROLL_S = 0.3
CALIBRATION_FRAMES = 300   # ~10 s of 32 ms chunks used for the noise floor
AUTO_MARGIN_DB = 12.0


def dbfs(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9)


class Listener:
    """Feed it frames with :meth:`feed`; it calls ``on_utterance(audio)``."""

    def __init__(self, settings, on_utterance, on_level):
        self.s = settings
        self.on_utterance = on_utterance
        self.on_level = on_level
        self.vad = SileroVAD()
        self.pending = np.zeros(0, np.float32)
        self.preroll: collections.deque[np.ndarray] = collections.deque(
            maxlen=int(PREROLL_S * RATE / CHUNK) + 1)
        self.noise_floor: collections.deque[float] = collections.deque(maxlen=CALIBRATION_FRAMES)
        self.segment: list[np.ndarray] = []
        self.silence = 0.0
        self.ptt_held = False
        self.awake_until = 0.0
        self.paused_until = 0.0
        self.speaking = False
        self.last_level = -90.0

    # -- public ---------------------------------------------------------------

    @property
    def threshold_db(self) -> float:
        if not self.s.auto_threshold or len(self.noise_floor) < 20:
            return self.s.energy_threshold_db
        return float(np.percentile(self.noise_floor, 20)) + AUTO_MARGIN_DB

    def calibrate(self) -> None:
        self.noise_floor.clear()

    def pause_for_typing(self, seconds: float) -> None:
        """The user is typing: drop the current utterance and wait."""
        self.paused_until = time.monotonic() + seconds
        self.segment.clear()

    def push_to_talk(self, held: bool) -> None:
        self.ptt_held = held
        if not held and self.segment:
            self._flush()

    def wake(self) -> None:
        self.awake_until = time.monotonic() + self.s.session_timeout_s

    @property
    def awake(self) -> bool:
        return self.s.mode == "open" or time.monotonic() < self.awake_until

    def feed(self, frame: np.ndarray) -> None:
        self.pending = np.concatenate([self.pending, frame])
        while self.pending.size >= CHUNK:
            chunk, self.pending = self.pending[:CHUNK], self.pending[CHUNK:]
            self._chunk(chunk)

    # -- internals ------------------------------------------------------------

    def _chunk(self, chunk: np.ndarray) -> None:
        level = dbfs(chunk)
        prob = self.vad(chunk)
        # Open mic trusts the VAD alone; activation also needs enough energy.
        loud = self.s.mode == "open" or level >= self.threshold_db
        voiced = prob >= self.s.vad_threshold and loud
        if prob < 0.2:
            self.noise_floor.append(level)
        self.speaking, self.last_level = voiced, level
        self.on_level(float(level), float(self.threshold_db), bool(voiced))

        now = time.monotonic()
        if now < self.paused_until:
            return
        if self.s.mode == "ptt":
            if self.ptt_held:
                self.segment.append(chunk)
            return

        if not self.segment:
            self.preroll.append(chunk)
        if voiced:
            if not self.segment:
                self.segment = list(self.preroll)
                self.preroll.clear()
            else:
                self.segment.append(chunk)
            self.silence = 0.0
        elif self.segment:
            self.segment.append(chunk)
            self.silence += CHUNK / RATE
            if self.silence * 1000 >= self.s.silence_ms:
                self._flush()
        if self.segment and len(self.segment) * CHUNK / RATE >= self.s.max_segment_s:
            self._flush()

    def _flush(self) -> None:
        audio = np.concatenate(self.segment) if self.segment else np.zeros(0, np.float32)
        self.segment, self.silence = [], 0.0
        if audio.size >= RATE // 4:
            self.on_utterance(audio)
