"""The training half of scripts/lora_sweep.py; runs in the training environment.

Loads the base model once and, for each run it is sent, trains an adapter on all
readings but one fold (by default on the app's int8 weights, see train.AppWeights),
measures it on that fold in NeMo (offline) and grafts it
onto the app's own int8 encoder as fp32 branches, as train.py does. Then it prints
``READY <dir>`` and waits for ``NEXT`` before deleting the graft: the app's own
streaming evaluator, in the other process, measures it meanwhile.

Input on stdin: a JSON line ({"rows", "runs", "work", "base_onnx", "folds"}), each
row's audio as float32, then the ``NEXT`` lines. Audio never touches the disk.
"""

import json
import os
import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cotorreando" / "lora"))
import train as T  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

DEFAULTS = {"targets": "attn,ffn", "layers": "all", "rank": 4, "alpha": 8.0, "lr": 2e-4, "steps": 150,
            "sched": "constant", "init": "small", "dropout": 0.0, "app_weights": True}


def emit(tag: str, data) -> None:
    print(f"{tag} {json.dumps(data)}", flush=True)


def read_input():
    source = sys.stdin.buffer
    job = json.loads(source.readline())
    for row in job["rows"]:
        row["audio"] = np.frombuffer(source.read(row["samples"] * 4), np.float32).copy()
    return job


def delta_report(model) -> dict:
    """Size of the adapters' change: against the weights, and against one int8 step of them
    (what merging would have to survive; the graft does not quantize it)."""
    vs_step, norms = [], []
    for m in T.lora_modules(model):
        delta, w = m.delta().detach().float(), m.base.weight.detach().float()
        vs_step.append(float((delta.abs() / ((w.max() - w.min()) / 255)).mean()))
        norms.append(float(delta.norm() / w.norm()))
    return {"delta_vs_step": float(np.median(vs_step)), "delta_rel_norm": float(np.median(norms))}


def diagnose(model) -> dict:
    """Whether NeMo's own regularisation is on while training."""
    dropouts = sorted({m.p for m in model.modules() if isinstance(m, nn.Dropout)})
    cfg = model.cfg.get("spec_augment") if hasattr(model, "cfg") else None
    return {"dropout_p": dropouts, "spec_augment": {k: v for k, v in dict(cfg or {}).items() if not k.startswith("_")}}


def count_calls(module) -> list[int]:
    counter = [0]
    original = module.forward

    def forward(*args, **kwargs):
        counter[0] += module.training
        return original(*args, **kwargs)

    module.forward = forward
    return counter


def main() -> None:
    job = read_input()
    rows, work, folds = job["rows"], Path(job["work"]), job["folds"]
    base_onnx = Path(job["base_onnx"])
    model = T.load_base(T.BASE_MODEL)
    if torch.cuda.is_available():
        model = model.cuda()
    diag = diagnose(model)
    spec_calls = count_calls(model.spec_augmentation) if model.spec_augmentation is not None else None
    app = T.AppWeights(model, base_onnx)     # NeMo computing like the app's int8 encoder

    for fold in range(folds):
        held = [r for r in rows if r["fold"] == fold]
        emit("BASE", {"fold": fold, "wer_fp32": T.word_error_rate(model, held)})

    for run in job["runs"]:
        cfg = {**DEFAULTS, **run["config"]}
        fold = run["fold"]
        held = [r for r in rows if r["fold"] == fold]
        rest = [r for r in rows if r["fold"] != fold]
        T.remove_lora(model)           # the base weights are never trained: dropping the adapters resets it
        app.use(cfg["app_weights"])
        torch.manual_seed(0)
        T.add_lora(model, cfg["rank"], cfg["alpha"], cfg["targets"], cfg["layers"], cfg["init"], cfg["dropout"])
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        checkpoint = work / "checkpoint.sealed"
        checkpoint.unlink(missing_ok=True)
        T.train(model, rest, cfg["steps"], cfg["lr"], threading.Event(), checkpoint, os.urandom(32),
                run["id"], cfg["sched"])
        checkpoint.unlink(missing_ok=True)
        if spec_calls is not None and cfg["steps"]:
            diag["spec_augment_calls_while_training"] = spec_calls[0]
            spec_calls = None          # once is enough
            emit("DIAG", diag)
        report = delta_report(model)
        wer = T.word_error_rate(model, held)
        out = work / "run"
        shutil.rmtree(out, ignore_errors=True)
        T.graft(model, base_onnx, out / "graft")
        emit("RESULT", {"id": run["id"], "trainable": trainable, "wer_fp32": wer, **report})
        print(f"READY {out}", flush=True)
        if sys.stdin.buffer.readline().strip() != b"NEXT":
            break
        shutil.rmtree(out, ignore_errors=True)
    print("FINISHED", flush=True)


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)          # NeMo's native libraries can crash during interpreter shutdown
