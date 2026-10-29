"""LoRA fine-tuning of Parakeet TDT on the user's recordings.

Runs inside the optional training environment (PyTorch + NeMo), never inside
the app itself, so it must not import the ``cotorreando`` package.

Low-rank adapters are added to the query/key/value/output projections of every
Conformer self-attention block. Only the adapters are trained; afterwards they
are merged into the base weights and the model is exported to ONNX (int8) in
the same layout the app already loads.

    python train.py --manifest m.jsonl --base-onnx DIR --out DIR
    python train.py --export-only --out DIR
"""

import argparse
import shutil
from pathlib import Path

import torch
from torch import nn

BASE_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
TARGETS = ("linear_q", "linear_k", "linear_v", "linear_out")
COPIED = ("nemo128.onnx", "vocab.txt", "config.json")


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


def train(model, manifest: str, steps: int, lr: float) -> None:
    import lightning.pytorch as pl

    model.setup_training_data({
        "manifest_filepath": manifest, "sample_rate": 16000, "batch_size": 4,
        "shuffle": True, "num_workers": 0, "max_duration": 30, "use_lhotse": False,
    })
    model.setup_optimization({"name": "adamw", "lr": lr, "weight_decay": 0.0})
    model._validation_dl = None  # noqa: SLF001 - we have no validation split
    trainer = pl.Trainer(max_steps=steps, accelerator="gpu", devices=1, precision="bf16-mixed",
                         logger=False, enable_checkpointing=False, log_every_n_steps=5,
                         limit_val_batches=0)
    model.set_trainer(trainer)
    trainer.fit(model)


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
    for leftover in out.glob("*.data"):
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
        add_lora(model, args.rank, args.alpha)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Trainable parameters: {trainable:,}", flush=True)
        train(model, args.manifest, args.steps, args.lr)
        merge_lora(model)
    export(model.cpu(), args.out, args.base_onnx)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
