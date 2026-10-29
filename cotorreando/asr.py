"""Speech recognition with NVIDIA Parakeet TDT 0.6B v3 running on ONNX Runtime.

The model is split in three ONNX graphs (preprocessor, encoder and a fused
decoder+joint network). Decoding is the greedy Token-and-Duration Transducer
(TDT) algorithm: at each encoder frame the joint network predicts a token and
how many frames to skip.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

import numpy as np
import onnxruntime as ort

from .paths import MODELS_DIR

log = logging.getLogger(__name__)

MODEL_NAME = "parakeet-tdt-0.6b-v3"
ONNX_REPO = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/"
ORIGINAL_REPO = "nvidia/parakeet-tdt-0.6b-v3"
FILES = ("config.json", "vocab.txt", "nemo128.onnx",
         "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx")

SAMPLE_RATE = 16000
MAX_TOKENS_PER_FRAME = 10


def model_dir() -> Path:
    return MODELS_DIR / MODEL_NAME


def is_downloaded(directory: Path | None = None) -> bool:
    directory = directory or model_dir()
    return all((directory / f).exists() for f in FILES)


def download(progress=lambda done, total: None) -> Path:
    """Fetch the ONNX export. Falls back to exporting the original .nemo."""
    target = model_dir()
    target.mkdir(parents=True, exist_ok=True)
    try:
        for name in FILES:
            dest = target / name
            if dest.exists():
                continue
            tmp = dest.with_suffix(dest.suffix + ".part")
            with urllib.request.urlopen(ONNX_REPO + name) as r, open(tmp, "wb") as f:
                total, done = int(r.headers.get("Content-Length", 0)), 0
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    progress(done, total)
            tmp.replace(dest)
    except OSError as err:
        log.warning("ONNX download failed (%s); exporting original model", err)
        export_from_nemo(target)
    return target


def export_from_nemo(target: Path) -> None:
    """Export the original NeMo checkpoint. Needs the optional training environment."""
    from .lora import env
    if not env.installed():
        env.install(log.info)
    env.run_train(["--export-only", "--model", ORIGINAL_REPO, "--out", str(target)], log.info)


class Parakeet:
    """Greedy TDT decoder over the three ONNX graphs."""

    def __init__(self, directory: Path | None = None, use_gpu: bool = True):
        directory = directory or model_dir()
        providers = ["CPUExecutionProvider"]
        if use_gpu:
            available = ort.get_available_providers()
            for p in ("CUDAExecutionProvider", "DmlExecutionProvider"):
                if p in available:
                    providers.insert(0, p)
                    break
        opts = ort.SessionOptions()
        opts.log_severity_level = 3

        def load(name):
            return ort.InferenceSession(str(directory / name), opts, providers=providers)

        self.preprocessor = load("nemo128.onnx")
        self.encoder = load(self._pick(directory, "encoder-model"))
        self.decoder = load(self._pick(directory, "decoder_joint-model"))

        vocab = {}
        for line in (directory / "vocab.txt").read_text(encoding="utf-8").splitlines():
            token, index = line.rsplit(" ", 1)
            vocab[int(index)] = token.replace("▁", " ")
        self.vocab = vocab
        self.blank = max(vocab)  # last entry is the blank symbol
        shape = self.decoder.get_inputs()[3].shape
        self.state_shape = (shape[0], 1, shape[2])

    @staticmethod
    def _pick(directory: Path, stem: str) -> str:
        # A LoRA-merged export (fp32) takes priority over the stock int8 one.
        for name in (f"{stem}.onnx", f"{stem}.int8.onnx"):
            if (directory / name).exists():
                return name
        raise FileNotFoundError(stem)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe mono float32 audio sampled at 16 kHz."""
        if audio.size < SAMPLE_RATE // 10:
            return ""
        wave = audio.astype(np.float32)[None, :]
        features, lengths = self.preprocessor.run(
            None, {"waveforms": wave, "waveforms_lens": np.array([wave.shape[1]], np.int64)})
        encoded, enc_len = self.encoder.run(
            None, {"audio_signal": features, "length": lengths})
        return self._decode(encoded[0], int(enc_len[0]))

    def _decode(self, encoded: np.ndarray, length: int) -> str:
        state1 = np.zeros(self.state_shape, np.float32)
        state2 = np.zeros(self.state_shape, np.float32)
        tokens: list[int] = []
        last = self.blank
        t = emitted = 0
        while t < length:
            logits, _, new1, new2 = self.decoder.run(None, {
                "encoder_outputs": encoded[None, :, t:t + 1],
                "targets": np.array([[last]], np.int32),
                "target_length": np.array([1], np.int32),
                "input_states_1": state1,
                "input_states_2": state2,
            })
            logits = logits.reshape(-1)
            token = int(np.argmax(logits[:self.blank + 1]))
            skip = int(np.argmax(logits[self.blank + 1:]))
            if token != self.blank:
                tokens.append(token)
                last, state1, state2 = token, new1, new2
                emitted += 1
            if skip or token == self.blank or emitted >= MAX_TOKENS_PER_FRAME:
                t += max(skip, 1)
                emitted = 0
        return "".join(self.vocab[i] for i in tokens).strip()
