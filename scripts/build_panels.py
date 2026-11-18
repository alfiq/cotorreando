"""Write calibration panels for the languages that have no hand-written ones.

The sentences come from Mozilla Common Voice (https://github.com/common-voice/common-voice), written
and reviewed by speakers of each language and dedicated to the public domain under CC0 1.0, so they
can be shipped without asking or crediting anyone. They are read at a fixed commit, so the same command always writes the same files:

    python scripts/build_panels.py            # every missing language
    python scripts/build_panels.py de fr      # only these, overwriting them

Each panel joins short sentences into 150-210 characters, as long as the hand-written ones
(15-20 seconds of reading).
"""

from __future__ import annotations

import json
import random
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cotorreando.languages import HAND_WRITTEN, LANGUAGES  # noqa: E402

DATASETS = ROOT / "cotorreando" / "lora" / "datasets"
COMMIT = "159d0badbda5c440885a5ad8f5e46f64441cde91"
FOLDER = {"sv": "sv-SE"}  # Common Voice folder, where it differs from the code
PANELS = 12
PANEL_CHARS = (150, 210)  # like the hand-written ones (up to ~185): 15-20 seconds of reading
MAX_FILE = 3_000_000  # of a huge corpus dump, only this many bytes, and only if the rest falls short
API = "https://api.github.com/repos/common-voice/common-voice/contents/server/data/{folder}?ref={commit}"
RAW = "https://raw.githubusercontent.com/common-voice/common-voice/{commit}/server/data/{folder}/{name}"


def _get(url: str, limit: int = 0) -> bytes:
    headers = {"User-Agent": "cotorreando-build-panels"}
    if limit:
        headers["Range"] = f"bytes=0-{limit - 1}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def sentences(code: str, whole: bool = True) -> list[str]:
    folder = FOLDER.get(code, code)
    listing = json.loads(_get(API.format(folder=folder, commit=COMMIT)))
    found: list[str] = []
    for entry in sorted(listing, key=lambda e: e["name"]):
        big = entry["size"] > MAX_FILE
        if not entry["name"].endswith(".txt") or big == whole:
            continue
        url = RAW.format(commit=COMMIT, folder=folder, name=entry["name"])
        lines = _get(url, MAX_FILE if big else 0).decode("utf-8", "replace").splitlines()
        found.extend(line.strip() for line in (lines[:-1] if big else lines))  # a cut last line
    return found


def usable(sentence: str) -> bool:
    words = sentence.split()
    return (
        5 <= len(words) <= 18
        and len(sentence) <= PANEL_CHARS[1] // 2
        and sentence[-1:] in ".!?"
        and not re.search(r"[0-9#@<>\[\]{}|_/\\]|https?:", sentence)
        and sentence[0].isupper()
    )


def panels(code: str) -> list[str]:
    pool = sorted({s for s in sentences(code) if usable(s)})
    if len(pool) < PANELS * 4:  # only a big dump has enough: read its beginning
        pool = sorted({s for s in sentences(code) + sentences(code, whole=False) if usable(s)})
    if len(pool) < PANELS * 4:
        raise SystemExit(f"{code}: only {len(pool)} usable sentences")
    random.Random(code).shuffle(pool)
    out, current = [], []
    for sentence in pool:
        if len(" ".join([*current, sentence])) > PANEL_CHARS[1]:
            continue
        current.append(sentence)
        if len(" ".join(current)) >= PANEL_CHARS[0]:
            out.append(" ".join(current))
            current = []
            if len(out) == PANELS:
                break
    return out


def write(code: str) -> None:
    own, _, english = LANGUAGES[code]
    header = (
        f"# {english} ({own}) calibration panels: one panel per line, about 15-20 seconds of reading each.\n"
        f"# Sentences from the Common Voice sentence collection (CC0), commit {COMMIT[:12]};\n"
        "# picked and joined by scripts/build_panels.py, not by a speaker of the language.\n"
    )
    (DATASETS / f"{code}.txt").write_text(header + "\n".join(panels(code)) + "\n", encoding="utf-8")
    print(code, "ok")


def main(codes: list[str]) -> None:
    targets = codes or [c for c in LANGUAGES if c not in HAND_WRITTEN and not (DATASETS / f"{c}.txt").exists()]
    for code in targets:
        write(code)


if __name__ == "__main__":
    main(sys.argv[1:])
