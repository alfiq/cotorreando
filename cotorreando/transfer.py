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
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from pyrage import passphrase

FORMAT, VERSION = "cotorreando-export", 1

# What belongs to this computer rather than to the user: devices, where the blob sits,
# files that are not exported (adapters, calibration readings) and notices already shown.
MACHINE_FIELDS = {"microphone", "use_gpu", "autostart", "blob_x", "blob_y", "hidden",
                  "lora_adapter", "calibrated", "password_offered", "training_notice_shown"}


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
