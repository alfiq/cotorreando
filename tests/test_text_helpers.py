"""Small helpers around the model download and the voice-activity detector, without any model."""

import hashlib

import numpy as np
import pytest

from cotorreando import vad


# -- ensure_model --------------------------------------------------------------------

@pytest.fixture
def downloads(isolated_data, monkeypatch):
    calls = []

    def fake_retrieve(url, path):
        calls.append((url, path))
        with open(path, "wb") as f:
            f.write(b"onnx")

    monkeypatch.setattr(vad.urllib.request, "urlretrieve", fake_retrieve)
    monkeypatch.setattr(vad, "SHA256", hashlib.sha256(b"onnx").hexdigest())
    return calls


def test_tampered_model_is_rejected(downloads, monkeypatch):
    monkeypatch.setattr(vad, "SHA256", "0" * 64)
    with pytest.raises(OSError):
        vad.ensure_model()
    assert not vad.PATH.exists() and not vad.PATH.with_name(vad.PATH.name + ".part").exists()


def test_ensure_model_downloads_once(downloads):
    assert not vad.PATH.exists()
    vad.ensure_model()
    assert vad.PATH.read_bytes() == b"onnx" and len(downloads) == 1
    assert downloads[0][0] == vad.URL
    vad.ensure_model()              # already there: no second download
    assert len(downloads) == 1


def test_ensure_model_creates_the_folder(downloads):
    assert not vad.PATH.parent.exists()
    vad.ensure_model()
    assert vad.PATH.parent.is_dir()


def test_interrupted_download_is_fetched_again(isolated_data, monkeypatch):
    attempts = []

    def flaky(url, path):
        attempts.append(path)
        with open(path, "wb") as f:
            f.write(b"par")
        if len(attempts) == 1:
            raise ConnectionError("connection dropped")
        with open(path, "wb") as f:
            f.write(b"complete model")

    monkeypatch.setattr(vad.urllib.request, "urlretrieve", flaky)
    monkeypatch.setattr(vad, "SHA256", hashlib.sha256(b"complete model").hexdigest())
    with pytest.raises(ConnectionError):
        vad.ensure_model()
    vad.ensure_model()
    assert vad.PATH.read_bytes() == b"complete model"


# -- SileroVAD.__call__ ------------------------------------------------------------------

class StubSession:
    def __init__(self, probability=0.75):
        self.probability = probability
        self.feeds = []

    def run(self, outputs, feeds):
        self.feeds.append({k: np.array(v, copy=True) for k, v in feeds.items()})
        return np.array([[self.probability]], np.float32), np.ones((2, 1, 128), np.float32)


@pytest.fixture
def detector():
    obj = object.__new__(vad.SileroVAD)
    obj.session = StubSession()
    obj.sr = np.array(16000, np.int64)
    obj.reset()
    return obj


def test_reset_state(detector):
    assert detector.state.shape == (2, 1, 128) and not detector.state.any()
    assert detector.context.shape == (vad.CONTEXT,) and not detector.context.any()


def test_call_returns_probability_and_feeds_context(detector):
    chunk = np.arange(vad.CHUNK, dtype=np.float32) / vad.CHUNK
    assert detector(chunk) == pytest.approx(0.75)
    first = detector.session.feeds[0]
    assert first["input"].shape == (1, vad.CONTEXT + vad.CHUNK) and first["input"].dtype == np.float32
    assert not first["input"][0, :vad.CONTEXT].any()
    assert int(first["sr"]) == 16000
    # the next call carries the tail of this chunk and the state the model returned
    detector(chunk * 0)
    second = detector.session.feeds[1]
    np.testing.assert_array_equal(second["input"][0, :vad.CONTEXT], chunk[-vad.CONTEXT:])
    assert second["state"].all()


def test_reset_clears_state_after_use(detector):
    detector(np.ones(vad.CHUNK, np.float32))
    detector.reset()
    assert not detector.state.any() and not detector.context.any()
