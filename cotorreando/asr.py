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
        """Transcribe a whole utterance (mono float32, 16 kHz) at once."""
        if audio.size < SAMPLE_RATE // 10:
            return ""
        encoded = self.encode(audio)
        state = DecoderState(self)
        return self.decode(encoded, 0, encoded.shape[1], state).strip()

    def encode(self, audio: np.ndarray) -> np.ndarray:
        """Encoder output for ``audio``: (1024, frames), one frame per 80 ms."""
        wave = audio.astype(np.float32)[None, :]
        features, lengths = self.preprocessor.run(
            None, {"waveforms": wave, "waveforms_lens": np.array([wave.shape[1]], np.int64)})
        encoded, enc_len = self.encoder.run(None, {"audio_signal": features, "length": lengths})
        return encoded[0, :, :int(enc_len[0])]

    def decode(self, encoded: np.ndarray, start: int, end: int, state: "DecoderState") -> str:
        """Greedy TDT over frames ``start..end``, continuing from ``state``.

        Returns the new text. A duration that jumps past ``end`` is remembered
        in ``state.carry`` so the next chunk starts at the right frame.
        """
        tokens: list[int] = []
        t, emitted = start + state.carry, 0
        while t < end:
            logits, _, new1, new2 = self.decoder.run(None, {
                "encoder_outputs": encoded[None, :, t:t + 1],
                "targets": np.array([[state.last]], np.int32),
                "target_length": np.array([1], np.int32),
                "input_states_1": state.h,
                "input_states_2": state.c,
            })
            logits = logits.reshape(-1)
            token = int(np.argmax(logits[:self.blank + 1]))
            skip = int(np.argmax(logits[self.blank + 1:]))
            if token != self.blank:
                tokens.append(token)
                state.last, state.h, state.c = token, new1, new2
                emitted += 1
            if skip or token == self.blank or emitted >= MAX_TOKENS_PER_FRAME:
                t += max(skip, 1)
                emitted = 0
        state.carry = t - end
        return "".join(self.vocab[i] for i in tokens)


class DecoderState:
    """Prediction-network state carried from one chunk to the next."""

    def __init__(self, model: Parakeet):
        self.h = np.zeros(model.state_shape, np.float32)
        self.c = np.zeros(model.state_shape, np.float32)
        self.last = model.blank
        self.carry = 0


class Stream:
    """True streaming over an offline model: chunked encoding, stateful decoding.

    Audio is encoded in a sliding window of left context + new chunk + a short
    look-ahead. Only the frames of the new chunk are decoded, and the decoder
    keeps its state, so every token is produced exactly once and never revised.
    The cost per step is constant, so utterances can be arbitrarily long.
    """

    FRAME = 1280                   # samples per encoder frame (80 ms)
    LEFT = 32 * FRAME              # 2.6 s of context already decoded
    CHUNK = 12 * FRAME             # 0.96 s of new audio per step
    RIGHT = 6 * FRAME              # 0.48 s of look-ahead

    def __init__(self, model: Parakeet):
        self.model = model
        self.state = DecoderState(model)
        self.audio = np.zeros(0, np.float32)
        self.offset = 0            # absolute sample index of self.audio[0]
        self.done = 0              # absolute sample index decoded so far
        self.started = False

    def feed(self, audio: np.ndarray) -> str:
        """Add audio; return any text that became final."""
        self.audio = np.concatenate([self.audio, audio.astype(np.float32)])
        text = ""
        while self.offset + self.audio.size >= self.done + self.CHUNK + self.RIGHT:
            text += self._step(self.done + self.CHUNK, self.done + self.CHUNK + self.RIGHT)
        return text

    def finish(self) -> str:
        """Decode whatever is left; the stream ends here."""
        end = self.offset + self.audio.size
        return self._step(end, end) if end > self.done else ""

    def _step(self, chunk_end: int, window_end: int) -> str:
        start = max(self.offset, self.done - self.LEFT)
        window = self.audio[start - self.offset:window_end - self.offset]
        encoded = self.model.encode(window)
        first = (self.done - start) // self.FRAME
        last = min(encoded.shape[1], (chunk_end - start + self.FRAME - 1) // self.FRAME)
        text = self.model.decode(encoded, first, last, self.state)
        self.done = chunk_end
        # Keep only the left context needed for the next window.
        drop = max(0, self.done - self.LEFT - self.offset)
        self.audio, self.offset = self.audio[drop:], self.offset + drop
        if not self.started:
            text = text.lstrip()
            self.started = bool(text)
        return text
