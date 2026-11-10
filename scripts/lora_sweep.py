"""Compare LoRA designs on your own calibration readings, with k-fold cross-validation.

    python scripts/lora_sweep.py --phase 0
    python scripts/lora_sweep.py --phase 1
    python scripts/lora_sweep.py --phase 2 --base "{\"targets\": \"attn,ffn\"}"
    python scripts/lora_sweep.py --phase 3 --base "{\"targets\": \"attn,ffn\", \"sched\": \"cosine\", \"lr\": 5e-4}"

Run it from the project's own environment, with the training environment already
installed by the app. It asks for the vault password in the terminal (never as an
argument). Only the calibration readings are used; the vault is never modified.

Each configuration is trained once per fold, on the other folds. Every model is measured
like the app uses it: the app's own int8 encoder with the adapters grafted on as fp32
branches, transcribing in streaming. The fp32 model is measured too (NeMo, offline).
Results go to %LOCALAPPDATA%\\Cotorreando\\sweep\\phase<N>-<time>.csv (error rates only, no text).
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotorreando.asr import Parakeet, model_dir  # noqa: E402
from cotorreando.lora import env  # noqa: E402
from cotorreando.lora.job import _readings, error_rate  # noqa: E402
from cotorreando.paths import DATA_DIR  # noqa: E402
from cotorreando.vault import Vault, WrongPassword  # noqa: E402

WORKER = Path(__file__).resolve().parent / "lora_sweep_worker.py"
SWEEP_DIR = DATA_DIR / "sweep"
MIN_GAIN = 0.03  # relative WER gain a design must reach on average...
MIN_WINS = 4 / 6  # ...winning in at least this share of the folds

PHASES = {
    # D-control: no training (B stays zero), so the graft must give exactly the stock model's rate.
    # D-fp32: trained on NeMo's fp32 weights (as before); D-int8: on the app's int8 ones.
    0: {"D-control": {"steps": 0}, "D-fp32": {"app_weights": False}, "D-int8": {}},
    1: {
        "T1-attn": {"targets": "attn"},
        "T2-attn+ffn": {"targets": "attn,ffn"},
        "T3-ffn": {"targets": "ffn"},
        "T4-attn+ffn+conv": {"targets": "attn,ffn,conv"},
        "T5-attn+ffn-0-11": {"targets": "attn,ffn", "layers": "0-11"},
    },
    2: {
        "O1-const-2e-4": {"sched": "constant", "lr": 2e-4},
        "O2-cos-2e-4": {"sched": "cosine", "lr": 2e-4},
        "O3-cos-5e-4": {"sched": "cosine", "lr": 5e-4},
        "O4-cos-1e-3": {"sched": "cosine", "lr": 1e-3},
        "O5-cos-kaiming": {"sched": "cosine", "init": "kaiming"},
    },
    3: {
        "R1-drop0": {"dropout": 0.0},
        "R2-drop0.05": {"dropout": 0.05},
        "R3-drop0.1": {"dropout": 0.1},
        "R4-r4": {"rank": 4, "alpha": 8.0},
        "R5-r16": {"rank": 16, "alpha": 32.0},
    },
}


def unlock() -> Vault:
    vault = Vault()
    if not vault.ready:
        raise SystemExit("There is no vault yet: record the calibration in the app first.")
    for _ in range(3):
        try:
            vault.unlock(getpass.getpass("Vault password: "))
            return vault
        except WrongPassword:
            print("Wrong password.")
    raise SystemExit("Giving up.")


def gather(vault: Vault, folds: int, language: str) -> tuple[list[dict], dict]:
    rows, audio = [], {}
    for row in _readings(vault):
        if language != "both" and row["language"] != language:
            continue
        samples = vault.read_reading(row["language"], row["index"])
        row = {"id": row["id"], "text": row["text"], "samples": int(samples.size)}
        rows.append(row)
        audio[row["id"]] = samples
    for i, row in enumerate(rows):
        row["fold"] = i % folds
    return rows, audio


def streaming_rates(directory: Path, rows: list[dict], audio: dict, folds: int) -> list[float]:
    model = Parakeet(directory, use_gpu=False)
    return [error_rate(model, [r for r in rows if r["fold"] == f], audio) for f in range(folds)]


def summary(results: list[dict], stock: list[float], stock_fp32: list[float]) -> None:
    by_config: dict[str, list[dict]] = {}
    for r in results:
        by_config.setdefault(r["config"], []).append(r)
    print(f"\nStock model: app {statistics.mean(stock):.4f}, NeMo on the app weights {statistics.mean(stock_fp32):.4f}")
    print("fp32 column: NeMo offline, on the weights each run trained on; app: the graft, streaming")
    print("gain: relative to the stock streaming int8 mean; wins/ties/losses per fold")
    header = f"{'config':22} {'fp32':>7} {'app':>7} {'gain':>7} {'W/T/L':>7} {'dW/step':>8}  verdict"
    print(header + "\n" + "-" * len(header))
    for name, runs in by_config.items():
        runs.sort(key=lambda r: r["fold"])
        fp32, app = (statistics.mean(r[k] for r in runs) for k in ("wer_fp32", "wer_graft"))
        base = statistics.mean(stock[r["fold"]] for r in runs)
        gain = (base - app) / base if base else 0.0  # pooled: a fold at 0 % must not divide
        diffs = [stock[r["fold"]] - r["wer_graft"] for r in runs]
        wins, ties = sum(d > 0 for d in diffs), sum(d == 0 for d in diffs)
        ok = len(runs) == len(stock) and gain >= MIN_GAIN and wins >= MIN_WINS * len(stock)
        print(
            f"{name:22} {fp32:7.4f} {app:7.4f} {gain:+7.1%} {wins}/{ties}/{len(runs) - wins - ties:<3} "
            f"{statistics.mean(r['delta_vs_step'] for r in runs):8.3f}  {'ACCEPT' if ok else '-'}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", type=int, choices=sorted(PHASES), required=True)
    ap.add_argument("--base", default="{}", help="JSON fixed for every run (the winners of earlier phases)")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--language", choices=("es", "en", "both"), default="both")
    ap.add_argument("--only", help="comma-separated config names of the phase to run")
    args = ap.parse_args()
    if not env.installed():
        raise SystemExit("The training environment is not installed: start a training once from the app.")
    base = json.loads(args.base)
    configs = {k: {**base, **v} for k, v in PHASES[args.phase].items() if not args.only or k in args.only.split(",")}

    vault = unlock()
    rows, audio = gather(vault, args.folds, args.language)
    vault.lock()
    if len(rows) < 2 * args.folds:
        raise SystemExit(f"Only {len(rows)} readings: too few for {args.folds} folds.")
    print(
        f"{len(rows)} readings in {args.folds} folds; {len(configs)} configurations, "
        f"{len(configs) * args.folds} trainings."
    )

    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    print("Measuring the stock model…", flush=True)
    stock = streaming_rates(model_dir(), rows, audio, args.folds)
    runs = [
        {"id": f"{name}/{fold}", "config": cfg, "fold": fold, "name": name}
        for name, cfg in configs.items()
        for fold in range(args.folds)
    ]
    header = json.dumps(
        {
            "rows": rows,
            "runs": [{k: r[k] for k in ("id", "config", "fold")} for r in runs],
            "work": str(SWEEP_DIR),
            "base_onnx": str(model_dir()),
            "folds": args.folds,
        }
    )
    # -P: scripts/ must not shadow installed packages (numba imports "coverage", and so is scripts/coverage.py).
    worker = subprocess.Popen(
        [str(env.PYTHON), "-u", "-P", str(WORKER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={**os.environ, "KMP_BLOCKTIME": "0", "PYTHONIOENCODING": "utf-8"},
    )
    worker.stdin.write(header.encode("utf-8") + b"\n")
    for row in rows:
        worker.stdin.write(audio[row["id"]].astype("float32").tobytes())
    worker.stdin.flush()

    results, pending, by_id = [], None, {r["id"]: r for r in runs}
    stock_fp32 = [0.0] * args.folds
    csv_path = SWEEP_DIR / f"phase{args.phase}-{time.strftime('%Y%m%d-%H%M%S')}.csv"  # one file per sweep
    started = time.time()
    for raw in worker.stdout:
        line = raw.decode("utf-8", "replace").rstrip()
        tag, _, rest = line.partition(" ")
        if tag == "BASE":
            base = json.loads(rest)
            stock_fp32[base["fold"]] = base["wer_fp32"]
            print(f"  NeMo on the app weights, stock, fold {base['fold']}: {base['wer_fp32']:.4f}")
        elif tag == "DIAG":
            print(f"  Regularisation while training: {rest}")
        elif tag == "RESULT":
            pending = json.loads(rest)
        elif tag == "READY" and pending:
            run = by_id[pending["id"]]
            out = Path(rest)
            fold = run["fold"]
            held = [r for r in rows if r["fold"] == fold]
            graft = error_rate(Parakeet(out / "graft", use_gpu=False), held, audio)
            result = {
                "phase": args.phase,
                "config": run["name"],
                "fold": fold,
                "params": json.dumps(run["config"]),
                "stock": stock[fold],
                "stock_fp32": stock_fp32[fold],
                "wer_graft": graft,
                **pending,
            }
            results.append(result)
            new = not csv_path.exists()
            with csv_path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(result))
                if new:
                    writer.writeheader()
                writer.writerow(result)
            done = len(results)
            eta = (time.time() - started) / done * (len(runs) - done)
            print(
                f"[{done}/{len(runs)}] {run['id']}: stock {stock[fold]:.4f}  fp32 {pending['wer_fp32']:.4f}  "
                f"app (graft) {graft:.4f}  (~{eta / 60:.0f} min left)",
                flush=True,
            )
            pending = None
            worker.stdin.write(b"NEXT\n")
            worker.stdin.flush()
        elif tag == "PROGRESS":
            continue
        else:
            print(f"  {line}")
    worker.wait()
    if results:
        summary(results, stock, stock_fp32)
    print(f"\nResults: {csv_path}")


if __name__ == "__main__":
    main()
