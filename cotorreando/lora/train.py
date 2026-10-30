"""LoRA fine-tuning of Parakeet TDT on the user's recordings.

Runs inside the optional training environment (PyTorch + NeMo), never inside
the app itself, so it must not import the ``cotorreando`` package.

Low-rank adapters are added to the query/key/value/output projections of every
Conformer self-attention block. Only the adapters are trained; afterwards they
are merged into the base weights and the model is exported to ONNX (int8) in
the same layout the app already loads. A few recordings are held out to compare
the error rate before and after; if training did not help, nothing is exported.

    python train.py --manifest m.jsonl --base-onnx DIR --out DIR
    python train.py --export-only --out DIR
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import torch
from torch import nn

BASE_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
TARGETS = ("linear_q", "linear_k", "linear_v", "linear_out")
COPIED = ("nemo128.onnx", "vocab.txt", "config.json")
HOLDOUT_EVERY = 6   # one recording in six is kept for the evaluation
DURATIONS = 5       # the model predicts frame skips 0..4


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


def tdt_cost(acts, labels, frames: int, length: int, durations: int):
    """Negative log-likelihood of one utterance: the forward algorithm over (frame, label).

    From each cell a blank advances 1..D-1 frames; a token advances 0..D-1 frames and one label.
    """
    tokens = acts.size(-1) - durations
    tok = torch.log_softmax(acts[..., :tokens], -1)
    dur = torch.log_softmax(acts[..., tokens:], -1)
    blank = tokens - 1
    index = torch.arange(length, device=acts.device)
    start = torch.full((length + 1,), -1e4, device=acts.device, dtype=acts.dtype)
    incoming = [start.clone() for _ in range(frames + 1)]
    incoming[0] = torch.cat([start[:1] * 0, start[1:]])
    for t in range(frames):
        emit = tok[t, index, labels[:length]]            # label u from cell u
        stay = emit + dur[t, index, 0]
        cells = [incoming[t][0]]
        for u in range(length):                          # zero-duration tokens, within the frame
            cells.append(torch.logaddexp(incoming[t][u + 1], cells[u] + stay[u]))
        row = torch.stack(cells)
        for d in range(1, durations):
            target = min(t + d, frames)
            step = row + tok[t, :length + 1, blank] + dur[t, :length + 1, d]
            moved = torch.cat([start[:1], row[:-1] + emit + dur[t, index, d]])
            incoming[target] = torch.logaddexp(incoming[target], torch.logaddexp(step, moved))
    return -incoming[frames][length] / frames


def use_portable_loss(model) -> None:
    """NeMo's TDT loss needs numba's CUDA backend, whose nvvm.dll pip does not ship on Windows."""
    def forward(acts, labels, act_lens, label_lens):
        acts = acts.float()
        return torch.stack([tdt_cost(acts[i], labels[i], int(act_lens[i]), int(label_lens[i]), DURATIONS)
                            for i in range(acts.size(0))])

    model.loss._loss.forward = forward  # noqa: SLF001


def train(model, manifest: str, steps: int, lr: float) -> None:
    import lightning.pytorch as pl

    use_portable_loss(model)
    model.setup_training_data({
        "manifest_filepath": manifest, "sample_rate": 16000, "batch_size": 4,
        "shuffle": True, "num_workers": 0, "max_duration": 30, "use_lhotse": False,
    })
    model.setup_optimization({"name": "adamw", "lr": lr, "weight_decay": 0.0})
    model._validation_dl = None  # noqa: SLF001 - we have no validation split
    gpu = torch.cuda.is_available()

    class Progress(pl.Callback):
        def on_train_batch_start(self, *_):
            # A few minutes of audio must not shift the normalisation statistics.
            for module in model.modules():
                if isinstance(module, nn.modules.batchnorm._BatchNorm):  # noqa: SLF001
                    module.eval()

        def on_train_batch_end(self, trainer, *_):
            print(f"PROGRESS {trainer.global_step} {steps}", flush=True)

    trainer = pl.Trainer(max_steps=steps, accelerator="gpu" if gpu else "cpu", devices=1,
                         precision="bf16-mixed" if gpu else "32-true", logger=False,
                         enable_checkpointing=False, log_every_n_steps=5, limit_val_batches=0,
                         callbacks=[Progress()], enable_progress_bar=False)
    model.set_trainer(trainer)
    trainer.fit(model)


def split_manifest(manifest: str, folder: Path) -> tuple[str, list[dict]]:
    """Write the training part of the manifest; return its path and the held-out rows."""
    rows = [json.loads(line) for line in Path(manifest).read_text(encoding="utf-8").splitlines()]
    held = rows[HOLDOUT_EVERY - 1::HOLDOUT_EVERY]
    kept = [r for r in rows if r not in held]
    path = folder / "train.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    return str(path), held


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
    results = model.transcribe([r["audio_filepath"] for r in rows], batch_size=2, verbose=False)
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
    ap.add_argument("--manifest")
    ap.add_argument("--base-onnx", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=BASE_MODEL)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--alpha", type=float, default=16)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()

    model = nemo_asr.models.ASRModel.from_pretrained(args.model)
    if not args.export_only:
        if torch.cuda.is_available():
            model = model.cuda()
        with tempfile.TemporaryDirectory() as folder:
            manifest, held = split_manifest(args.manifest, Path(folder))
            before = word_error_rate(model, held)
            add_lora(model, args.rank, args.alpha)
            trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
            print(f"Trainable parameters: {trainable:,}", flush=True)
            train(model, manifest, args.steps, args.lr)
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
