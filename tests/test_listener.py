"""Splits the microphone into utterances: pauses, the four listening modes and the threshold rules.

The VAD is a stand-in (see EnergyVAD) and the clock is a variable, so every test is deterministic.
Hiss at 0.0005 is about -66 dBFS (background), at 0.0012 about -58 dBFS (a murmur), and at 0.1
about -20 dBFS (speech).
"""

from types import SimpleNamespace

import numpy as np
import pytest

from cotorreando import listener
from cotorreando.audio import RATE
from cotorreando.config import Settings
from cotorreando.listener import CALIBRATION_FRAMES, CHUNK, Listener, dbfs

RNG = np.random.default_rng(11)
BACKGROUND, MURMUR, SPEECH = 0.0005, 0.0012, 0.1
SILENCE_CHUNK = CHUNK / RATE  # seconds per decision, 32 ms


def hiss(amplitude):
    return (amplitude * RNG.standard_normal(CHUNK)).astype(np.float32)


class EnergyVAD:
    """Hears voice when the chunk is loud enough; counts how often it was asked."""

    calls = 0

    def __init__(self):
        pass

    def __call__(self, chunk):
        EnergyVAD.calls += 1
        return 0.95 if dbfs(chunk) > -40 else 0.02


class EarVAD(EnergyVAD):
    """Hears voice in everything, whatever the level: only the energy rule can then reject it."""

    def __call__(self, chunk):
        return 0.95


class Clock:
    now = 0.0


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    Clock.now = 0.0
    monkeypatch.setattr(listener, "time", SimpleNamespace(monotonic=lambda: Clock.now))
    EnergyVAD.calls = 0
    monkeypatch.setattr(listener, "SileroVAD", EnergyVAD)
    return Clock


class Sink:
    def __init__(self):
        self.audio, self.ends, self.levels, self.events = [], [], [], []

    def on_audio(self, uid, audio):
        self.audio.append((uid, len(audio)))
        self.events.append(("audio", uid))

    def on_end(self, uid):
        self.ends.append(uid)
        self.events.append(("end", uid))

    def on_level(self, level, threshold, voiced):
        self.levels.append((level, threshold, voiced))


def make(mode="activation", **settings):
    sink = Sink()
    lst = Listener(Settings(mode=mode, **settings), sink.on_audio, sink.on_end, sink.on_level)
    return lst, sink


def feed(lst, amplitude, chunks):
    for _ in range(chunks):
        lst.feed(hiss(amplitude))


def uids_with_audio(sink):
    return sorted({uid for uid, _ in sink.audio})


# -- segmentation by pauses -----------------------------------------------------------


def test_silence_never_opens_an_utterance():
    lst, sink = make()
    feed(lst, BACKGROUND, 50)
    assert sink.audio == [] and sink.ends == []


def test_speech_opens_an_utterance_that_starts_with_the_preroll():
    lst, sink = make()
    feed(lst, BACKGROUND, 20)
    feed(lst, SPEECH, 1)
    uid, size = sink.audio[0]
    assert uid == 1
    assert size == (int(listener.PREROLL_S * RATE / CHUNK) + 1) * CHUNK  # 0.6 s of lead-in, the speech chunk included


def test_utterance_ends_after_seven_hundred_milliseconds_of_silence():
    lst, sink = make()
    feed(lst, SPEECH, 5)
    feed(lst, BACKGROUND, 30)
    # 22 silent chunks are 704 ms, the first count to reach silence_ms (700); each is still sent
    assert sink.ends == [1]
    assert len([1 for uid, _ in sink.audio if uid == 1]) == 5 + 22


def test_short_pause_does_not_split_the_utterance():
    lst, sink = make()
    feed(lst, SPEECH, 5)
    feed(lst, BACKGROUND, 10)  # 320 ms, under silence_ms
    feed(lst, SPEECH, 5)
    assert sink.ends == [] and uids_with_audio(sink) == [1]


def test_long_pause_splits_into_two_utterances_in_order():
    lst, sink = make()
    feed(lst, SPEECH, 5)
    feed(lst, BACKGROUND, 30)
    feed(lst, SPEECH, 5)
    assert sink.ends == [1]
    assert uids_with_audio(sink) == [1, 2]
    assert sink.events.index(("end", 1)) < sink.events.index(("audio", 2))


def test_feed_waits_for_a_whole_chunk_before_deciding():
    lst, _ = make()
    for _ in range(3):
        lst.feed(np.zeros(160, np.float32))  # three 10 ms frames: 480 samples
    assert EnergyVAD.calls == 0
    lst.feed(np.zeros(160, np.float32))  # 640 samples: one chunk and 128 left over
    assert EnergyVAD.calls == 1 and lst.pending.size == 640 - CHUNK


def test_on_level_reports_level_threshold_and_decision_for_every_chunk():
    lst, sink = make()
    feed(lst, BACKGROUND, 2)
    feed(lst, SPEECH, 1)
    assert [voiced for _, _, voiced in sink.levels] == [False, False, True]
    background, speech = sink.levels[0][0], sink.levels[-1][0]
    assert background < -55 and speech > -30  # about -66 and -20 dBFS
    assert sink.levels[0][1] == lst.s.energy_threshold_db  # the first chunks use the fixed threshold


# -- the four listening modes ---------------------------------------------------------


def test_open_mode_hears_every_pause_split_without_a_wake_word():
    lst, sink = make("open")
    feed(lst, SPEECH, 5)
    feed(lst, BACKGROUND, 30)
    assert sink.ends == [1]
    assert lst.awake  # always awake in open mode


def test_activation_needs_loud_enough_voice_while_open_mode_only_needs_the_vad(monkeypatch):
    monkeypatch.setattr(listener, "SileroVAD", EarVAD)
    quiet = make("activation", auto_threshold=False, energy_threshold_db=-50.0)
    feed(quiet[0], MURMUR, 10)  # the VAD says voice, the level is below -50 dB
    assert quiet[1].audio == []
    open_mode = make("open", auto_threshold=False, energy_threshold_db=-50.0)
    feed(open_mode[0], MURMUR, 10)
    assert open_mode[1].audio and open_mode[1].audio[0][0] == 1


def test_push_to_talk_records_only_while_the_key_is_held_and_ignores_the_vad():
    lst, sink = make("ptt")
    feed(lst, SPEECH, 3)  # not held: nothing is kept
    assert sink.audio == []
    lst.push_to_talk(True)
    feed(lst, BACKGROUND, 4)  # silence is recorded too while held
    assert [uid for uid, _ in sink.audio] == [1, 1, 1, 1]
    lst.push_to_talk(False)
    assert sink.ends == [1]
    lst.push_to_talk(True)
    feed(lst, BACKGROUND, 2)
    assert uids_with_audio(sink) == [1, 2]


def test_releasing_the_key_without_audio_ends_nothing():
    lst, sink = make("ptt")
    lst.push_to_talk(False)
    assert sink.ends == []


def test_awake_window_lasts_the_session_timeout_and_renews_on_wake(clock):
    lst, _ = make("activation", session_timeout_s=6.0)
    assert not lst.awake
    lst.wake()
    clock.now = 5.9
    assert lst.awake
    lst.wake()  # speaking again renews the session
    clock.now = 10.0
    assert lst.awake
    clock.now = 16.0
    assert not lst.awake


# -- typing pauses --------------------------------------------------------------------


def test_typing_cancels_the_utterance_without_ending_it_and_pauses_listening(clock):
    lst, sink = make()
    feed(lst, SPEECH, 5)
    lst.pause_for_typing(1.0)
    assert not lst.active and sink.ends == []  # cancelled: no end was reported
    clock.now = 0.5
    feed(lst, SPEECH, 3)  # still paused
    assert uids_with_audio(sink) == [1]
    clock.now = 1.5
    feed(lst, SPEECH, 1)
    assert uids_with_audio(sink) == [1, 2]


def test_typing_during_push_to_talk_drops_the_held_audio(clock):
    lst, sink = make("ptt")
    lst.push_to_talk(True)
    feed(lst, SPEECH, 2)
    lst.pause_for_typing(1.0)
    feed(lst, SPEECH, 2)
    assert len(sink.audio) == 2


# -- the threshold --------------------------------------------------------------------


def test_fixed_threshold_is_used_when_auto_is_off():
    lst, _ = make(auto_threshold=False, energy_threshold_db=-40.0)
    feed(lst, BACKGROUND, 30)
    assert lst.threshold_db == -40.0


def test_auto_threshold_is_the_background_plus_twelve_dB():
    lst, _ = make()
    feed(lst, BACKGROUND, 40)
    assert lst.threshold_db == pytest.approx(np.percentile(list(lst.noise_floor), 20) + listener.AUTO_MARGIN_DB)
    assert -56 < lst.threshold_db < -52  # 0.0005 RMS is about -66 dBFS


def test_auto_threshold_needs_twenty_quiet_chunks_before_it_is_trusted():
    lst, _ = make()
    feed(lst, BACKGROUND, 19)
    assert lst.threshold_db == lst.s.energy_threshold_db
    feed(lst, BACKGROUND, 1)
    assert lst.threshold_db != lst.s.energy_threshold_db


def test_the_threshold_follows_a_louder_room():
    lst, _ = make()
    feed(lst, BACKGROUND, 30)
    quiet = lst.threshold_db
    feed(lst, 0.005, 300)  # 0.005 RMS is about -46 dBFS
    assert lst.threshold_db > quiet + 10


def test_speech_is_never_counted_as_background():
    lst, _ = make()
    feed(lst, SPEECH, 10)
    assert len(lst.noise_floor) == 0


def test_background_memory_is_bounded():
    lst, _ = make()
    feed(lst, BACKGROUND, CALIBRATION_FRAMES + 100)
    assert len(lst.noise_floor) == CALIBRATION_FRAMES


def test_calibrate_forgets_the_background():
    lst, _ = make(energy_threshold_db=-45.0)
    feed(lst, BACKGROUND, 30)
    lst.calibrate()
    assert lst.threshold_db == -45.0


def test_dbfs_of_known_levels():
    assert dbfs(np.full(100, 0.1, np.float32)) == pytest.approx(-20.0, abs=1e-3)
    assert dbfs(np.zeros(100, np.float32)) < -150  # silence has a floor, not minus infinity
