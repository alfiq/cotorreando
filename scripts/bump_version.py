"""Write a new version everywhere it lives and open its CHANGELOG entry.

    python scripts/bump_version.py X.Y.Z

Touches pyproject.toml, cotorreando/__init__.py, installer.iss and build.ps1, and adds an
empty "## X.Y.Z — <today>" heading to CHANGELOG.md. Line endings are kept as they are.
"""

import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (file, pattern whose group 1 is the version)
PLACES = [
    ("pyproject.toml", r'^version = "([^"]+)"'),
    ("cotorreando/__init__.py", r'^__version__ = "([^"]+)"'),
    ("installer.iss", r'^#define AppVersion "([^"]+)"'),
    ("build.ps1", r"--product-version=(\S+)"),
    ("build.ps1", r"--file-version=(\S+)"),
]


def replace(text: str, pattern: str, version: str) -> str:
    match = re.search(pattern, text, re.M)
    if not match:
        raise SystemExit(f"Pattern not found: {pattern}")
    return text[:match.start(1)] + version + text[match.end(1):]


def bump(version: str, root: Path = ROOT, today: datetime.date | None = None) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"Not X.Y.Z: {version}")
    texts = {}
    for name, pattern in PLACES:
        path = root / name
        text = texts.get(name) or path.read_bytes().decode("utf-8")
        texts[name] = replace(text, pattern, version)
    changelog = root / "CHANGELOG.md"
    text = changelog.read_bytes().decode("utf-8")
    if not re.search(rf"^## {re.escape(version)}\b", text, re.M):
        nl = "\r\n" if "\r\n" in text else "\n"
        first = re.search(r"^## ", text, re.M)
        at = first.start() if first else len(text)
        heading = f"## {version} — {(today or datetime.date.today()).isoformat()}{nl}{nl}- {nl}{nl}"
        texts["CHANGELOG.md"] = text[:at] + heading + text[at:]
    for name, text in texts.items():
        (root / name).write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    bump(sys.argv[1])
    print(f"Version {sys.argv[1]}: fill in CHANGELOG.md, then follow docs/VERSIONES.md.")
