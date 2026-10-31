"""LoRA fine-tuning of Parakeet TDT on the user's recordings.

Runs inside the optional training environment (PyTorch + NeMo), never inside
the app itself, so it must not import the ``cotorreando`` package.

Low-rank adapters are added to the query/key/value/output projections of every
Conformer self-attention block. Only the adapters are trained; afterwards they
are merged into the base weights and the model is exported to ONNX (int8) in
the same layout the app already loads. A few recordings are held out to compare
the error rate before and after; if training did not help, nothing is exported.

Recordings arrive through stdin, so decrypted audio stays out of the disk. A line
``STOP`` on stdin saves the state in ``--checkpoint`` (encrypted) and ends the run; a later
run over the same recordings continues from there.

    python train.py --base-onnx DIR --checkpoint FILE --out DIR < job
    python train.py --export-only --out DIR
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import threading
from pathlib import Path

import numpy as np
import torch
from torch import nn

BASE_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
TARGETS = ("linear_q", "linear_k", "linear_v", "linear_out")
COPIED = ("nemo128.onnx", "vocab.txt", "config.json")
DURATIONS = 5       # the model predicts frame skips 0..4
RATE = 16000
MAX_SECONDS = 30
CHECKPOINT_EVERY = 25
VERIFY_MARGIN = 0.05  # per-frame cost a corrected text may add over the original


class LoRALinear(nn.Module):
    """y = W x + (alpha / r) * B A x, with W frozen and B initialised to zero."""

    def __init__(self, base: nn.Linear, rank: int, alpha: float):
        super().__init__()
        self.base = base
        self.scale = alpha / rank
        self.a = nn.Parameter(torch.randn(rank, base.in_features) * 0.01)
        self.b = nn.Parameter(torch.zeros(base.out_features, rank))

    def forward(self, x):
        return self.base(x) + (x @ self.a.t() @ self.b.t()) * self.scale

    def merged(self) -> nn.Linear:
        with torch.no_grad():
            self.base.weight += (self.b @ self.a) * self.scale
        return self.base


def attention_blocks(model):
    return [layer.self_attn for layer in model.encoder.layers]


def add_lora(model, rank: int, alpha: float) -> None:
    for p in model.parameters():
        p.requires_grad = False
    for att in attention_blocks(model):
        for name in TARGETS:
            setattr(att, name, LoRALinear(getattr(att, name), rank, alpha))


def merge_lora(model) -> None:
    for att in attention_blocks(model):
        for name in TARGETS:
            module = getattr(att, name)
            if isinstance(module, LoRALinear):
                setattr(att, name, module.merged())


def _tdt_forward_backward(emit, blank, dur, backward: bool):
    """Log-likelihood and, if ``backward``, the expected use of each log-probability (numpy fp64 arrays)."""
    frames, length = emit.shape
    add = np.logaddexp
    stay = emit + dur[:, :length, 0]
    prefix = np.zeros((frames, length + 1))
    prefix[:, 1:] = np.cumsum(stay, 1)
    leave = (blank[..., None] + dur[..., 1:]).transpose(0, 2, 1)     # frame, d - 1, cell
    move = (emit[..., None] + dur[:, :length, 1:]).transpose(0, 2, 1)
    reach = leave.shape[1]
    alpha = np.full((frames + 1, length + 1), -1e4)      # a floor: the cost of a hopeless text is capped
    alpha[0, 0] = 0.0
    rows = np.empty((frames, length + 1))
    for t in range(frames):
        rows[t] = row = prefix[t] + add.accumulate(alpha[t] - prefix[t])   # zero-duration tokens, in closed form
        out = leave[t] + row
        out[:, 1:] = add(out[:, 1:], move[t] + row[:-1])
        k = min(reach, frames - t)
        alpha[t + 1:t + 1 + k] = add(alpha[t + 1:t + 1 + k], out[:k])
        if k < reach:                                                      # skips past the end land on the last frame
            alpha[frames] = add(alpha[frames], add.reduce(out[k:], 0))
    z = alpha[frames, length]
    if not backward:
        return z, ()
    beta = np.full((frames + 1, length + 1), -np.inf)
    beta[frames, length] = 0.0
    target = np.minimum(np.arange(frames)[:, None] + np.arange(1, reach + 1)[None], frames)
    for t in range(frames - 1, -1, -1):
        after = beta[target[t]]
        out = leave[t] + after
        out[:, :length] = add(out[:, :length], move[t] + after[:, 1:])
        beta[t] = add.accumulate((add.reduce(out, 0) + prefix[t])[::-1])[::-1] - prefix[t]
    after = beta[target]
    use_stay = np.exp(rows[:, :length] + stay + beta[:frames, 1:] - z)
    use_step = np.exp(rows[:, None] + leave + after - z)
    use_move = np.exp(rows[:, None, :length] + move + after[:, :, 1:] - z)
    use_dur = np.zeros_like(dur)
    use_dur[:, :length, 0] = use_stay
    use_dur[:, :, 1:] = use_step.transpose(0, 2, 1)
    use_dur[:, :length, 1:] += use_move.transpose(0, 2, 1)
    return z, (use_stay + use_move.sum(1), use_step.sum(1), use_dur)


def tdt_cost(acts, labels, frames: int, length: int, durations: int):
    """Negative log-likelihood of one utterance: the forward algorithm over (frame, label).

    From each cell a blank advances 1..D-1 frames; a token advances 0..D-1 frames and one label.
    The gradient of a log-likelihood is the expected use of each log-probability: forward-backward
    gives that directly, so autograd only has to carry it back from the log-probabilities.
    """
    tokens = acts.size(-1) - durations
    wants_grad = torch.is_grad_enabled() and acts.requires_grad
    acts = acts[:frames, :length + 1]                    # without the batch's padding
    tok = torch.log_softmax(acts[..., :tokens], -1)
    dur = torch.log_softmax(acts[..., tokens:], -1)
    logs = (tok[:, torch.arange(length, device=acts.device), labels[:length]],   # label u from cell u
            tok[..., tokens - 1], dur)
    logs = tuple(x.clamp_min(-1e4) for x in logs)        # -inf would turn the expected uses into NaN
    z, uses = _tdt_forward_backward(*(x.detach().double().cpu().numpy() for x in logs), wants_grad)
    if not wants_grad:
        return -dur.new_tensor(z) / frames
    # Value z, gradient sum(use * d log-probability).
    expected = sum((torch.from_numpy(u).to(x.device, x.dtype) * x).sum() for u, x in zip(uses, logs))
    return -(expected - expected.detach() + float(z)) / frames


def use_portable_loss(model) -> None:
    """NeMo's TDT loss needs numba's CUDA backend, whose nvvm.dll pip does not ship on Windows."""
    def forward(acts, labels, act_lens, label_lens):
        acts = acts.float()
        return torch.stack([tdt_cost(acts[i], labels[i], int(act_lens[i]), int(label_lens[i]), DURATIONS)
                            for i in range(acts.size(0))])

    model.loss._loss.forward = forward  # noqa: SLF001
    # One by one: otherwise the joint also computes the whole batch's padding rows, and the
    # VRAM it reserves can outgrow the card and start paging.
    model.joint._fused_batch_size = 1  # noqa: SLF001


class Readings(torch.utils.data.Dataset):
    """Recordings held in memory: decrypted audio never touches the disk."""

    def __init__(self, model, rows: list[dict]):
        self.items = [(torch.from_numpy(r["audio"]), torch.tensor(model.tokenizer.text_to_ids(r["text"])))
                      for r in rows if r["audio"].size <= MAX_SECONDS * RATE]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]

    @staticmethod
    def collate(batch):
        audio, tokens = zip(*batch)
        return (nn.utils.rnn.pad_sequence(audio, batch_first=True), torch.tensor([a.numel() for a in audio]),
                nn.utils.rnn.pad_sequence(tokens, batch_first=True), torch.tensor([t.numel() for t in tokens]))


def adapter_state(model) -> dict:
    return {k: v.detach().cpu() for k, v in model.named_parameters() if v.requires_grad}


def save_checkpoint(path: Path, key: bytes, digest: str, step: int, model, optimizer) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    buffer = io.BytesIO()
    torch.save({"digest": digest, "step": step, "adapters": adapter_state(model),
                "optimizer": optimizer.state_dict()}, buffer)
    nonce = os.urandom(12)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(nonce + AESGCM(key).encrypt(nonce, buffer.getvalue(), None))
    temp.replace(path)


def load_checkpoint(path: Path, key: bytes, digest: str) -> dict | None:
    """The saved state, if there is one for exactly this dataset."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        data = path.read_bytes()
        state = torch.load(io.BytesIO(AESGCM(key).decrypt(data[:12], data[12:], None)), weights_only=True)
    except (OSError, InvalidTag, ValueError):
        return None
    return state if state["digest"] == digest else None


def train(model, rows: list[dict], steps: int, lr: float, stopping: threading.Event, checkpoint: Path,
          key: bytes, digest: str) -> bool:
    """Returns False if it stopped early, with its state saved in ``checkpoint``."""
    import lightning.pytorch as pl

    use_portable_loss(model)
    saved = load_checkpoint(checkpoint, key, digest)
    done = 0
    if saved:
        model.load_state_dict(saved["adapters"], strict=False)
        done = saved["step"]
        print(f"RESUMED {done}", flush=True)
    if done >= steps:
        return True
    model._train_dl = torch.utils.data.DataLoader(Readings(model, rows), batch_size=4, shuffle=True,  # noqa: SLF001
                                                  collate_fn=Readings.collate, drop_last=False)
    model.setup_optimization({"name": "adamw", "lr": lr, "weight_decay": 0.0})
    model._validation_dl = None  # noqa: SLF001 - we have no validation split
    gpu = torch.cuda.is_available()

    class Progress(pl.Callback):
        def on_train_start(self, trainer, *_):
            if saved:
                trainer.optimizers[0].load_state_dict(saved["optimizer"])

        def on_train_batch_start(self, *_):
            # A few minutes of audio must not shift the normalisation statistics.
            for module in model.modules():
                if isinstance(module, nn.modules.batchnorm._BatchNorm):  # noqa: SLF001
                    module.eval()

        def on_train_batch_end(self, trainer, *_):
            step = done + trainer.global_step
            print(f"PROGRESS {step} {steps}", flush=True)
            if stopping.is_set() or step % CHECKPOINT_EVERY == 0:
                save_checkpoint(checkpoint, key, digest, step, model, trainer.optimizers[0])
            if stopping.is_set():
                trainer.should_stop = True

    # log_every_n_steps past the last step: at each one NeMo would decode the batch for a WER nobody reads.
    trainer = pl.Trainer(max_steps=steps - done, accelerator="gpu" if gpu else "cpu", devices=1,
                         precision="bf16-mixed" if gpu else "32-true", logger=False,
                         enable_checkpointing=False, log_every_n_steps=steps - done + 1, limit_val_batches=0,
                         callbacks=[Progress()], enable_progress_bar=False)
    model.set_trainer(trainer)
    trainer.fit(model)
    if gpu:
        model.cuda()               # Lightning leaves the model on the CPU
    return not stopping.is_set()


def text_cost(model, audio, text: str) -> float:
    """How badly ``text`` explains ``audio``, per frame. Lower is better."""
    device = next(model.parameters()).device
    labels = torch.tensor(model.tokenizer.text_to_ids(text), device=device)
    signal = torch.from_numpy(audio).to(device)[None]
    encoded, frames = model.forward(input_signal=signal, input_signal_length=torch.tensor([signal.size(1)], device=device))
    decoded, _, _ = model.decoder(targets=labels[None], target_length=torch.tensor([labels.numel()], device=device))
    acts = model.joint.joint(encoded.transpose(1, 2), decoded.transpose(1, 2))
    return float(tdt_cost(acts[0].float(), labels, int(frames[0]), labels.numel(), DURATIONS))


def verify_corrections(model, rows: list[dict]) -> list[dict]:
    """Keep a correction only if the corrected text explains the audio about as well as the original."""
    was_training = model.training
    model.eval()
    kept = []
    with torch.no_grad():
        for row in rows:
            if row.get("kind") == "correction" and not row.get("verified"):
                accepted = text_cost(model, row["audio"], row["text"]) <= (
                    text_cost(model, row["audio"], row["old"]) + VERIFY_MARGIN)
                print(f"VERIFY {row['id']} {int(accepted)}", flush=True)
                if not accepted:
                    continue
            kept.append(row)
    model.train(was_training)
    return kept


def read_job() -> tuple[bytes, list[dict]]:
    """A JSON line (the checkpoint key and the rows), then each row's audio as float32."""
    source = sys.stdin.buffer
    job = json.loads(source.readline())
    for row in job["rows"]:
        data = source.read(row["samples"] * 4)
        row["audio"] = np.frombuffer(data, np.float32).copy()
    return bytes.fromhex(job["key"]), job["rows"]


def watch_for_stop(stopping: threading.Event) -> None:
    def watch():
        for line in sys.stdin.buffer:
            if line.strip() == b"STOP":
                stopping.set()

    threading.Thread(target=watch, daemon=True).start()


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", "", text.lower()).split()


def _edits(a: list[str], b: list[str]) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def word_error_rate(model, rows: list[dict]) -> float:
    was_training = model.training
    model.eval()
    results = model.transcribe([r["audio"] for r in rows], batch_size=2, verbose=False)
    if was_training:
        model.train()
    errors = sum(_edits(_words(r["text"]), _words(h.text)) for r, h in zip(rows, results))
    return errors / max(sum(len(_words(r["text"])) for r in rows), 1)


def export(model, out: Path, base_onnx: Path | None) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    out.mkdir(parents=True, exist_ok=True)
    model.eval()
    model.export(str(out / "model.onnx"))  # writes encoder-model.onnx and decoder_joint-model.onnx
    for stem in ("encoder-model", "decoder_joint-model"):
        fp32 = out / f"{stem}.onnx"
        quantize_dynamic(fp32, out / f"{stem}.int8.onnx", weight_type=QuantType.QUInt8,
                         use_external_data_format=False)
        fp32.unlink()
    for leftover in out.iterdir():   # the fp32 export scatters its tensors in loose files
        if not leftover.name.endswith(".int8.onnx"):
            leftover.unlink()
    if base_onnx:
        for name in COPIED:
            shutil.copy2(base_onnx / name, out / name)
    else:
        write_vocab(model, out)


def write_vocab(model, out: Path) -> None:
    """Needed only when exporting from scratch (no ONNX download available)."""
    vocab = model.tokenizer.vocab
    lines = [f"{tok} {i}" for i, tok in enumerate(vocab)] + [f"<blk> {len(vocab)}"]
    (out / "vocab.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    model.preprocessor.export(str(out / "nemo128.onnx"))


def main() -> None:
    import nemo.collections.asr as nemo_asr

    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path)
    ap.add_argument("--base-onnx", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=BASE_MODEL)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--alpha", type=float, default=16)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()

    if not args.export_only:
        key, rows = read_job()     # first, so that the sender never waits on a loading model
        stopping = threading.Event()
        watch_for_stop(stopping)
    model = nemo_asr.models.ASRModel.from_pretrained(args.model)
    if not args.export_only:
        if torch.cuda.is_available():
            model = model.cuda()
        rows = verify_corrections(model, rows)
        digest = hashlib.sha256("|".join(sorted(r["id"] for r in rows)).encode()).hexdigest()
        held = [r for r in rows if r["held"]]
        before = word_error_rate(model, held)
        add_lora(model, args.rank, args.alpha)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Trainable parameters: {trainable:,}", flush=True)
        finished = train(model, [r for r in rows if not r["held"]], args.steps, args.lr, stopping,
                         args.checkpoint, key, digest)
        if not finished:
            print("PAUSED", flush=True)
            os._exit(0)            # the stdin watcher must not delay or upset the exit
        merge_lora(model)
        after = word_error_rate(model, held)
        print(f"EVAL {before:.4f} {after:.4f}", flush=True)
        if after >= before:
            print("NOIMPROVE", flush=True)
            return
        print("EXPORTING", flush=True)
    export(model.cpu(), args.out, args.base_onnx)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
    # NeMo's native libraries can crash during interpreter shutdown, after the work is done.
    sys.stdout.flush()
    os._exit(0)
