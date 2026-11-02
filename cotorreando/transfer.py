"""Moving settings and learned words to another install, in one file sealed with a password.

The file is age encrypted with a passphrase (scrypt), so it only needs its password and
does not depend on this install's key. Decrypted, it is one line of UTF-8 JSON, a newline,
and then the audio of the records:

    {"format": "cotorreando-export", "version": 1,
     "settings": {...},                       # Settings fields, minus MACHINE_FIELDS
     "custom_words": ["...", ...],
     "corrections": {"heard|corrected": count, ...},
     "hard_words": {"word": {"word": ..., "count": ..., "read": ...}, ...},
     "records": [{"id": "...", "meta": {...}, "samples": n}, ...]}
    \\n
    float32 little-endian samples at 16 kHz, record after record in the order of "records"

``records`` is empty and nothing follows the newline unless dictations were included.
Each record's audio is the next ``samples`` floats after the previous one's.

Importing adds the words to what this install already has (counts are summed), or replaces
its word lists with the file's when asked. Dictations are only ever added. Everything is
written through the vault, so it ends up sealed with this install's key, and the file's
password is not kept. A record remembers the id it had in the file as ``imported_from``
(or the one it was imported from before), so importing the same file twice, or a file
back into the install it came from, does not add its dictations again.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

import numpy as np
import pyrage
from pyrage import passphrase

from .vault import WrongPassword

FORMAT, VERSION = "cotorreando-export", 1

# What belongs to this computer rather than to the user: devices, where the blob sits,
# files that are not exported (adapters, calibration readings) and notices already shown.
MACHINE_FIELDS = {"microphone", "use_gpu", "autostart", "blob_x", "blob_y", "hidden",
                  "lora_adapter", "calibrated", "password_offered", "training_notice_shown"}


class NotAnExport(Exception):
    pass


def export(vault, settings, path: Path, password: str, include_dictations: bool) -> None:
    """The vault must be unlocked."""
    records, audio = [], []
    if include_dictations:
        for rid in vault.record_ids():
            meta, samples = vault.read_record(rid)
            records.append({"id": rid, "meta": meta, "samples": len(samples)})
            audio.append(samples.astype("<f4").tobytes())
    head = {"format": FORMAT, "version": VERSION,
            "settings": {k: v for k, v in asdict(settings).items() if k not in MACHINE_FIELDS},
            "custom_words": vault.load_private("custom_words", []),
            "corrections": vault.load_private("corrections", {}),
            "hard_words": vault.load_private("hard_words", {}),
            "records": records}
    payload = json.dumps(head, ensure_ascii=False).encode("utf-8") + b"\n" + b"".join(audio)
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(passphrase.encrypt(payload, password))
    temp.replace(path)


def read(path: Path, password: str) -> tuple[dict, bytes]:
    """The header and the audio, only in memory. Raises WrongPassword or NotAnExport."""
    try:
        data = passphrase.decrypt(Path(path).read_bytes(), password)
    except pyrage.DecryptError as err:
        raise WrongPassword from err
    line, _, audio = data.partition(b"\n")
    try:
        head = json.loads(line.decode("utf-8"))
    except ValueError as err:
        raise NotAnExport from err
    if not isinstance(head, dict) or head.get("format") != FORMAT or head.get("version", 0) > VERSION:
        raise NotAnExport
    return head, audio


def merge(vault, head: dict, audio: bytes, replace: bool = False) -> tuple[int, int, int]:
    """The vault must be unlocked. Returns how many words, corrections and dictations came in.

    ``replace`` starts the word lists from nothing instead of adding to them.
    """
    custom = [] if replace else vault.load_private("custom_words", [])
    words = [w for w in dict.fromkeys(head.get("custom_words", [])) if w not in custom]
    vault.save_private("custom_words", custom + words)
    counts = {} if replace else vault.load_private("corrections", {})
    for key, count in head.get("corrections", {}).items():
        counts[key] = counts.get(key, 0) + count
    vault.save_private("corrections", counts)
    hard = {} if replace else vault.load_private("hard_words", {})
    for plain, entry in head.get("hard_words", {}).items():
        mine = hard.setdefault(plain, {"word": entry["word"], "count": 0, "read": 0})
        mine["count"] += entry.get("count", 0)
        mine["read"] += entry.get("read", 0)
    vault.save_private("hard_words", hard)
    seen = set()
    for rid in vault.record_ids():
        seen.add(rid)
        seen.add(vault.read_record(rid)[0].get("imported_from"))
    added, start = 0, 0
    for record in head.get("records", []):
        samples = np.frombuffer(audio, "<f4", record["samples"], start * 4)
        start += record["samples"]
        origin = record["meta"].get("imported_from") or record["id"]
        if origin not in seen:
            vault.add_record({**record["meta"], "imported_from": origin}, samples.astype(np.float32))
            seen.add(origin)
            added += 1
    return len(words), len(head.get("corrections", {})), added


def apply_settings(settings, head: dict) -> None:
    """Only the fields this version knows that do not belong to the other computer."""
    known = {f.name: type(getattr(settings, f.name)) for f in fields(settings)}
    for name, value in head.get("settings", {}).items():
        kind = known.get(name)
        if name in MACHINE_FIELDS or kind is None:
            continue
        if kind is float and type(value) is int:
            value = float(value)
        if type(value) is kind:
            setattr(settings, name, value)
