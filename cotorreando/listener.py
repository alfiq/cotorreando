"""Splits the microphone stream into utterances, according to the listening mode.

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

PREROLL_S = 0.6
CALIBRATION_FRAMES = 300  # ~10 s of 32 ms chunks used for the noise floor
AUTO_MARGIN_DB = 12.0


def dbfs(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9)


class Listener:
    """Feed it frames with :meth:`feed`.

    Utterances are reported as they happen through ``on_audio(uid, audio)``
    (called repeatedly while you speak) and ``on_end(uid)``. ``uid`` grows by
    one per utterance; one that never gets ``on_end`` was cancelled.
    """

    def __init__(self, settings, on_audio, on_end, on_level):
        self.s = settings
        self.on_audio, self.on_end, self.on_level = on_audio, on_end, on_level
        self.vad = SileroVAD()
        self.pending = np.zeros(0, np.float32)
        self.preroll: collections.deque[np.ndarray] = collections.deque(maxlen=int(PREROLL_S * RATE / CHUNK) + 1)
        self.noise_floor: collections.deque[float] = collections.deque(maxlen=CALIBRATION_FRAMES)
        self.active = False
        self.uid = 0
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
        """The user is typing: cancel the current utterance and wait."""
        self.paused_until = time.monotonic() + seconds
        self.active = False

    def push_to_talk(self, held: bool) -> None:
        self.ptt_held = held
        if not held and self.active:
            self._end()

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

        if time.monotonic() < self.paused_until:
            return
        if self.s.mode == "ptt":
            if self.ptt_held:
                self._begin() if not self.active else None
                self.on_audio(self.uid, chunk)
            return

        if not self.active:
            self.preroll.append(chunk)
            if voiced:
                self._begin()
                self.on_audio(self.uid, np.concatenate(self.preroll))
                self.preroll.clear()
            return
        self.on_audio(self.uid, chunk)
        self.silence = 0.0 if voiced else self.silence + CHUNK / RATE
        if self.silence * 1000 >= self.s.silence_ms:
            self._end()

    def _begin(self) -> None:
        self.uid += 1
        self.active, self.silence = True, 0.0

    def _end(self) -> None:
        self.active = False
        self.on_end(self.uid)
