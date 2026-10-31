"""Speech recognition with NVIDIA Parakeet TDT 0.6B v3 running on ONNX Runtime.

The model is split in three ONNX graphs (preprocessor, encoder and a fused
decoder+joint network). Decoding is the greedy Token-and-Duration Transducer
(TDT) algorithm: at each encoder frame the joint network predicts a token and
how many frames to skip.
"""

from __future__ import annotations

import copy
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
BIAS_BONUS = 1.5               # logits added to tokens that continue a preferred word
BIAS_CANDIDATES = 5            # only the best few tokens can receive it


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


class Bias:
    """Nudges the decoder towards preferred words when it hesitates between similar options."""

    def __init__(self, words):
        self.prefixes = {word.lower()[:i] for word in words for i in range(1, len(word) + 1)}

    def apply(self, scores: np.ndarray, word: str, model: "Parakeet") -> None:
        for i in np.argpartition(scores, -BIAS_CANDIDATES)[-BIAS_CANDIDATES:]:
            if i != model.blank and _extend(word, model.vocab[int(i)]) in self.prefixes:
                scores[i] += BIAS_BONUS


def _extend(word: str, piece: str) -> str:
    """The word being spelled once ``piece`` is added; a leading space starts a new word."""
    piece = piece.lower()
    return piece.strip() if piece.startswith(" ") else word + piece


class Parakeet:
    """Greedy TDT decoder over the three ONNX graphs."""

    def __init__(self, directory: Path | None = None, use_gpu: bool = True):
        """The encoder does the heavy lifting and runs on the GPU (DirectML) when
        there is one. The preprocessor and the decoder make many tiny calls,
        which are faster on the CPU; the decoder gets one thread that does not
        spin between calls."""
        directory = directory or model_dir()
        cpu = ["CPUExecutionProvider"]

        def load(name, providers=cpu, threads=0, spin=True):
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            if threads:
                opts.intra_op_num_threads = threads
            if threads or not spin:
                opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
            if providers is not cpu:
                opts.enable_mem_pattern = False   # required by DirectML
            return ort.InferenceSession(str(directory / name), opts, providers=providers)

        self.on_gpu = use_gpu and "DmlExecutionProvider" in ort.get_available_providers()
        gpu = ["DmlExecutionProvider"] + cpu if self.on_gpu else cpu
        self.preprocessor = load("nemo128.onnx")
        # On the CPU, spinning threads fight each other: a step takes ~160 ms without them, ~270 ms with.
        self.encoder = load(self._pick(directory, "encoder-model"), gpu, spin=self.on_gpu)
        self.decoder = load(self._pick(directory, "decoder_joint-model"), threads=1)

        vocab = {}
        for line in (directory / "vocab.txt").read_text(encoding="utf-8").splitlines():
            token, index = line.rsplit(" ", 1)
            vocab[int(index)] = token.replace("▁", " ")
        self.vocab = vocab
        self.bias: Bias | None = None
        self.blank = max(vocab)  # last entry is the blank symbol
        shape = self.decoder.get_inputs()[3].shape
        self.state_shape = (shape[0], 1, shape[2])
        self.transcribe(np.zeros(SAMPLE_RATE, np.float32))   # compile the window shape now

    @staticmethod
    def _pick(directory: Path, stem: str) -> str:
        for name in (f"{stem}.int8.onnx", f"{stem}.onnx"):
            if (directory / name).exists():
                return name
        raise FileNotFoundError(stem)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a whole utterance (mono float32, 16 kHz).

        It goes through the same fixed-size windows as streaming, so the GPU
        only ever sees one input shape.
        """
        if audio.size < SAMPLE_RATE // 10:
            return ""
        stream = Stream(self)
        return (stream.feed(audio) + stream.finish()).strip()

    def encode(self, audio: np.ndarray) -> np.ndarray:
        """Encoder output for ``audio``: (1024, frames), one frame per 80 ms."""
        wave = audio.astype(np.float32)[None, :]
        features, lengths = self.preprocessor.run(
            None, {"waveforms": wave, "waveforms_lens": np.array([wave.shape[1]], np.int64)})
        encoded, enc_len = self.encoder.run(None, {"audio_signal": features, "length": lengths})
        return encoded[0, :, :int(enc_len[0])]

    def decode(self, encoded: np.ndarray, start: int, end: int, state: "DecoderState",
               trace: list | None = None) -> str:
        """Greedy TDT over frames ``start..end``, continuing from ``state``.

        Returns the new text. A duration that jumps past ``end`` is remembered
        in ``state.carry`` so the next chunk starts at the right frame. Each emitted
        token is added to ``trace`` as (piece, frame, probability, margin over the runner-up).
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
            scores = logits[:self.blank + 1]
            if self.bias:
                self.bias.apply(scores, state.word, self)
            token = int(np.argmax(scores))
            skip = int(np.argmax(logits[self.blank + 1:]))
            if token != self.blank:
                tokens.append(token)
                state.word = _extend(state.word, self.vocab[token])
                if trace is not None:
                    second, first = np.partition(_softmax(scores), -2)[-2:]
                    trace.append((self.vocab[token], t, float(first), float(first - second)))
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
        self.word = ""             # the word being spelled, for Bias


class Stream:
    """True streaming over an offline model: chunked encoding, stateful decoding.

    Audio is encoded in a fixed-size sliding window of left context + new
    chunk + a short look-ahead. Only the frames of the new chunk are decoded, and the decoder
    keeps its state, so every token is produced exactly once and never revised.
    The cost per step is constant, so utterances can be arbitrarily long.
    """

    FRAME = 1280                   # samples per encoder frame (80 ms)
    LEFT = 32 * FRAME              # 2.6 s of context already decoded
    RIGHT = 12 * FRAME             # 0.96 s of look-ahead: with 0.48 s whole phrases get lost
    # New audio per step: 0.32 s on a GPU (~55 ms per step), 0.64 s on a CPU (~250 ms).
    GPU_CHUNK, CPU_CHUNK = 4 * FRAME, 8 * FRAME

    def __init__(self, model: Parakeet):
        self.model = model
        self.CHUNK = self.GPU_CHUNK if model.on_gpu else self.CPU_CHUNK
        self.state = DecoderState(model)
        self.audio = np.zeros(0, np.float32)
        self.offset = 0            # absolute sample index of self.audio[0]
        self.done = 0              # absolute sample index decoded so far
        self.started = False
        self.tail = ""             # tentative text of the look-ahead, replaced on every step
        self.trace: list[tuple[str, float, float, float]] = []   # piece, seconds, probability, margin

    def feed(self, audio: np.ndarray) -> str:
        """Add audio; return any text that became final. ``tail`` holds what may still change."""
        self.audio = np.concatenate([self.audio, audio.astype(np.float32)])
        text = ""
        while self.offset + self.audio.size >= self.done + self.CHUNK + self.RIGHT:
            text += self._step(self.done + self.CHUNK, preview=True)
        return text

    def finish(self) -> str:
        """Decode whatever is left; the stream ends here."""
        end, text = self.offset + self.audio.size, ""
        while self.done < end:
            text += self._step(min(self.done + self.CHUNK, end))
        self.tail = ""
        return text

    def _step(self, chunk_end: int, preview: bool = False) -> str:
        # The window always has the same size: DirectML is only fast for the
        # shape it compiled first. Missing audio at either end is filled with a
        # mirror image of the real audio, because silence would skew the
        # per-utterance feature normalisation.
        start = self.done - self.LEFT
        size = self.LEFT + self.CHUNK + self.RIGHT
        lo = max(start, self.offset)
        piece = self.audio[lo - self.offset:start + size - self.offset]
        before, after = lo - start, size - (lo - start) - piece.size
        window = np.concatenate([_mirror(piece[::-1], before)[::-1], piece, _mirror(piece, after)])
        encoded = self.model.encode(window)
        first = self.LEFT // self.FRAME
        last = first + (chunk_end - self.done + self.FRAME - 1) // self.FRAME
        trace: list = []
        text = self.model.decode(encoded, first, min(last, encoded.shape[1]), self.state, trace)
        origin = self.done - self.LEFT
        self.trace += [(piece, (origin + t * self.FRAME) / SAMPLE_RATE, p, m) for piece, t, p, m in trace]
        self.done = chunk_end
        # After a full stop the prediction network can get stuck emitting only blanks,
        # silently losing the rest of the speech. Each sentence starts from a clean state.
        if text.rstrip().endswith((".", "?", "!")):
            carry = self.state.carry
            self.state = DecoderState(self.model)
            self.state.carry = carry
        if preview:   # on a copy: the look-ahead is decoded again once it becomes final
            self.tail = self.model.decode(encoded, min(last, encoded.shape[1]), encoded.shape[1],
                                          copy.copy(self.state))
        # Keep only the left context needed for the next window.
        drop = max(0, self.done - self.LEFT - self.offset)
        self.audio, self.offset = self.audio[drop:], self.offset + drop
        if not self.started:
            text = text.lstrip()
            self.started = bool(text)
            self.tail = self.tail if text else self.tail.lstrip()
        return text


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def _mirror(x: np.ndarray, n: int) -> np.ndarray:
    """``n`` samples continuing ``x`` by reflecting it back and forth."""
    if n <= 0 or x.size == 0:
        return np.zeros(max(n, 0), np.float32)
    bounce = np.concatenate([x[::-1], x])
    return np.resize(bounce, n).astype(np.float32)
