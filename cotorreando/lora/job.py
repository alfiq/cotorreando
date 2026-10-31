"""One training run: gather the whole dataset, train, and keep the result only if it helps."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass

import numpy as np

from ..asr import Bias, Parakeet, model_dir
from ..paths import MODELS_DIR, PACKAGE_DIR
from ..vault import VAULT_DIR, reading_path
from . import env
from .align import word_errors

log = logging.getLogger(__name__)

DATASET_DIR = PACKAGE_DIR / "lora" / "datasets"
CHECKPOINT = VAULT_DIR / "checkpoint.sealed"
HOLDOUT_EVERY = 6
BASE_STEPS, STEPS_PER_RECORD, MAX_STEPS = 150, 5, 400
MIN_NEW_RECORDS = 5
MIN_NEW_WORDS = 5
MIN_JOURNAL = 30             # sealed events; what they hold is unknown until the password is given
MAX_PANELS = 5


@dataclass
class Result:
    adapter: str = ""            # the new model, if it beat the current one
    paused: bool = False
    before: float | None = None
    after: float | None = None


def read_panels(language: str) -> list[str]:
    lines = (DATASET_DIR / f"{language}.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _holds_out(index: int) -> bool:
    """Only calibration readings, by position: the evaluation set never changes as the dataset grows."""
    return index % HOLDOUT_EVERY == HOLDOUT_EVERY - 1


def _readings(vault) -> list[dict]:
    rows = []
    for language in ("es", "en"):
        for index, text in enumerate(read_panels(language)):
            if reading_path(language, index).exists():
                rows.append({"id": f"{language}/{index:03d}", "kind": "reading", "text": text,
                             "held": _holds_out(index), "language": language, "index": index})
    return rows


def has_evaluation_set() -> bool:
    return any(reading_path(lang, i).exists() and _holds_out(i)
               for lang in ("es", "en") for i in range(len(read_panels(lang))))


def is_pending(learner) -> bool:
    """Something new to learn, or a run left unfinished. Never needs the password."""
    if not learner.vault.ready or not env.installed() or not has_evaluation_set():
        return False
    if CHECKPOINT.exists() or len(learner.words_to_practice(MIN_NEW_WORDS)) >= MIN_NEW_WORDS:
        return True
    if learner.vault.journal_size() >= MIN_JOURNAL:
        return True
    return len(set(learner.vault.record_ids()) - set(learner.vault.trained_ids())) >= MIN_NEW_RECORDS


def _gather(vault) -> tuple[list[dict], list[np.ndarray]]:
    rows, audio = [], []
    for row in _readings(vault):
        rows.append(row)
        audio.append(vault.read_reading(row["language"], row["index"]))
    for rid in vault.record_ids():
        meta, samples = vault.read_record(rid)
        rows.append({"id": rid, "kind": meta["kind"], "text": meta["text"], "old": meta.get("old"),
                     "verified": meta.get("verified"), "held": False})
        audio.append(samples)
    for row, samples in zip(rows, audio):
        row["samples"] = int(samples.size)
    return rows, audio


def _session_key(vault) -> str:
    state = vault.load_private("training", {})
    if "key" not in state:
        state["key"] = os.urandom(32).hex()
        vault.save_private("training", state)
    return state["key"]


def _evaluator(directory) -> Parakeet:
    return Parakeet(directory, use_gpu=False)


def error_rate(model: Parakeet, rows: list[dict], audio: dict[str, np.ndarray], words=None) -> float:
    """Error rate of a loaded model the way the app really uses it: streaming ONNX."""
    model.bias = Bias(words) if words else None
    errors = total = 0
    for row in rows:
        e, n = word_errors(row["text"], model.transcribe(audio[row["id"]]))
        errors, total = errors + e, total + n
    return errors / max(total, 1)


def run(learner, settings, log_line=log.info) -> Result:
    """The vault must be unlocked. Corrections the audio does not back up are deleted."""
    vault = learner.vault
    rows, audio = _gather(vault)
    by_id = {row["id"]: samples for row, samples in zip(rows, audio)}
    records = sum(row["kind"] != "reading" for row in rows)
    steps = min(BASE_STEPS + STEPS_PER_RECORD * records, MAX_STEPS)
    header = json.dumps({"key": _session_key(vault), "rows": rows}, ensure_ascii=False).encode("utf-8") + b"\n"
    payload = header + b"".join(samples.astype(np.float32).tobytes() for samples in audio)
    name = time.strftime("voz-%Y%m%d-%H%M")
    out = MODELS_DIR / "adapters" / name
    result = Result()
    rejected, accepted, ended = [], [], []

    def on_line(line: str) -> None:
        parts = line.split()
        if parts[:1] == ["VERIFY"]:
            (accepted if parts[2] == "1" else rejected).append(parts[1])
        elif parts[:1] == ["PAUSED"]:
            result.paused = True
        ended.append(line in ("PAUSED", "DONE", "NOIMPROVE"))
        log_line(line)

    try:
        env.run_train(["--base-onnx", str(model_dir()), "--checkpoint", str(CHECKPOINT), "--out", str(out),
                       "--steps", str(steps)], on_line, payload)
    except RuntimeError:         # NeMo can crash on its way out, after the work is done
        if not any(ended):
            raise
    finally:                     # verdicts stand even if the run failed later on
        for rid in accepted:
            vault.update_record(rid, {"verified": True})
        for rid in rejected:
            row = next(r for r in rows if r["id"] == rid)
            for old, new in _changed_words(row):
                learner.forget_correction(old, new)
            vault.delete_record(rid)
    if result.paused:
        return result

    CHECKPOINT.unlink(missing_ok=True)
    kept = [row for row in rows if row["id"] not in rejected]
    vault.set_trained_ids([row["id"] for row in kept if row["kind"] != "reading"])

    # Measured on the held-out readings, against the model in use right now.
    held = [row for row in kept if row["held"]]
    current = MODELS_DIR / "adapters" / settings.lora_adapter
    current = current if settings.lora_adapter and current.exists() else model_dir()
    best, model, plain = current, None, None     # plain: best's rate without vocabulary, once known
    if out.exists():
        # One model in memory at a time, each near 0.8 GB; the current one is reloaded only if the vocabulary needs it.
        result.before = error_rate(_evaluator(current), held, by_id)
        model = _evaluator(out)
        result.after = error_rate(model, held, by_id)
        if result.after < result.before:
            result.adapter, best, plain = name, out, result.after
        else:
            model, plain = None, result.before   # the loser is not used again
            shutil.rmtree(out)
    words = learner.vocabulary()
    helps = False
    if words:
        model = model or _evaluator(best)
        biased = error_rate(model, held, by_id, words)
        helps = biased < (error_rate(model, held, by_id) if plain is None else plain)
    settings.vocabulary_on = helps
    return result


def _changed_words(row: dict) -> list[tuple[str, str]]:
    from ..learning import find_corrections
    found = find_corrections(row.get("old") or "", row["text"])
    return found[1] if found else []


def write_panels(learner, language: str, log_line=log.info) -> list[dict]:
    """Short texts containing the words to practise; empty if Qwen cannot run here."""
    words = learner.words_to_practice(MAX_PANELS)
    if not words or not env.has_nvidia():
        return []
    panels: list[dict] = []

    def on_line(line: str) -> None:
        if line.startswith("PANEL "):
            panels.append(json.loads(line[6:]))
        else:
            log_line(line)

    try:
        env.run_panels(json.dumps({"words": words, "language": language}).encode("utf-8") + b"\n", on_line)
    except Exception:
        log.exception("Could not write panels")
    return panels
