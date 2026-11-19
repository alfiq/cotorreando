"""Voice activity detection on synthetic audio: speech against silence, with a stand-in model.

The ONNX graph is replaced by an energy detector, so these tests check how SileroVAD feeds
the model (chunks, context, state) and how its probabilities separate voice from silence.
The threshold rules live in the listener and are tested in test_listener.py.
"""

import numpy as np
import pytest

from cotorreando import vad

RNG = np.random.default_rng(7)


def tone(amplitude, n=vad.CHUNK):
    t = np.arange(n) / 16000
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def hiss(amplitude, n=vad.CHUNK):
    return (amplitude * RNG.standard_normal(n)).astype(np.float32)


class EnergySession:
    """Stands in for the ONNX session: probability rises with the energy of the new chunk."""

    def __init__(self):
        self.feeds = []

    def run(self, outputs, feeds):
        self.feeds.append({k: np.array(v, copy=True) for k, v in feeds.items()})
        new = feeds["input"][0, vad.CONTEXT :]
        prob = 0.95 if np.sqrt(np.mean(new * new)) > 0.02 else 0.02
        return np.array([[prob]], np.float32), feeds["state"] + 1.0


@pytest.fixture
def detector():
    obj = object.__new__(vad.SileroVAD)
    obj.session = EnergySession()
    obj.sr = np.array(16000, np.int64)
    obj.reset()
    return obj


def test_chunk_and_context_sizes_match_the_model():
    # 512 samples is 32 ms at 16 kHz; the model wants 64 samples of left context
    assert vad.CHUNK == 512 and vad.CONTEXT == 64


def test_speech_is_detected_and_silence_is_not(detector):
    probs = [detector(hiss(0.001)) for _ in range(5)]
    probs += [detector(tone(0.2)) for _ in range(5)]
    probs += [detector(hiss(0.001)) for _ in range(5)]
    assert all(p < 0.1 for p in probs[:5]) and all(p > 0.9 for p in probs[5:10])
    assert all(p < 0.1 for p in probs[10:])


def test_probability_is_a_plain_float_in_range(detector):
    for chunk in (hiss(0.001), tone(0.2)):
        p = detector(chunk)
        assert isinstance(p, float) and 0.0 <= p <= 1.0


def test_every_call_sends_context_plus_one_chunk(detector):
    for _ in range(4):
        detector(tone(0.2))
    assert all(f["input"].shape == (1, vad.CONTEXT + vad.CHUNK) for f in detector.session.feeds)


def test_state_is_carried_from_one_call_to_the_next(detector):
    for _ in range(3):
        detector(hiss(0.001))
    # the stand-in adds one to the state on every call: after three calls it is 2, 3 and 4
    assert detector.session.feeds[0]["state"].max() == 0.0
    assert detector.session.feeds[2]["state"].min() == 2.0


def test_reset_between_utterances_restarts_the_model(detector):
    detector(tone(0.2))
    detector.reset()
    detector(hiss(0.001))
    assert detector.session.feeds[-1]["state"].max() == 0.0
    assert not detector.session.feeds[-1]["input"][0, : vad.CONTEXT].any()


def test_session_is_built_on_cpu_with_one_thread(isolated_data, monkeypatch):
    seen = {}

    class Recorder:
        def __init__(self, path, opts, providers):
            seen.update(path=path, threads=opts.intra_op_num_threads, providers=providers)

        def run(self, outputs, feeds):  # pragma: no cover - never called here
            raise AssertionError

    monkeypatch.setattr(vad, "ensure_model", lambda: None)
    monkeypatch.setattr(vad.ort, "InferenceSession", Recorder)
    obj = vad.SileroVAD()
    assert seen["providers"] == ["CPUExecutionProvider"] and seen["threads"] == 1
    assert seen["path"] == str(vad.PATH)
    assert obj.sr.dtype == np.int64 and int(obj.sr) == 16000
    assert obj.state.shape == (2, 1, 128) and not obj.state.any()
