"""Silero VAD (v5) voice activity detection on ONNX Runtime."""

from __future__ import annotations

import hashlib
import urllib.request

import numpy as np
import onnxruntime as ort

from .paths import MODELS_DIR

URL = "https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx"
SHA256 = "2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f"
PATH = MODELS_DIR / "silero_vad.onnx"
CHUNK = 512      # samples per decision at 16 kHz (32 ms)
CONTEXT = 64     # v5 expects the tail of the previous chunk prepended


def ensure_model() -> None:
    if not PATH.exists():
        PATH.parent.mkdir(parents=True, exist_ok=True)
        part = PATH.with_name(PATH.name + ".part")    # renamed only once it is complete
        urllib.request.urlretrieve(URL, part)
        if hashlib.sha256(part.read_bytes()).hexdigest() != SHA256:
            part.unlink()
            raise OSError("silero_vad.onnx: checksum mismatch")
        part.replace(PATH)


class SileroVAD:
    def __init__(self):
        ensure_model()
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = opts.intra_op_num_threads = 1
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(PATH), opts, providers=["CPUExecutionProvider"])
        self.sr = np.array(16000, np.int64)
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), np.float32)
        self.context = np.zeros(CONTEXT, np.float32)

    def __call__(self, chunk: np.ndarray) -> float:
        """Speech probability for a 512-sample float32 chunk."""
        x = np.concatenate([self.context, chunk])[None, :].astype(np.float32)
        out, self.state = self.session.run(None, {"input": x, "state": self.state, "sr": self.sr})
        self.context = chunk[-CONTEXT:]
        return float(out[0, 0])
