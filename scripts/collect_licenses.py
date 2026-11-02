"""Copy the license texts of everything bundled into the build.

Run by build.ps1. Usage: python scripts/collect_licenses.py <output dir>
"""

from __future__ import annotations

import importlib.metadata as metadata
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PACKAGES = ("numpy", "onnxruntime-directml", "PyAudioWPatch", "livekit", "cryptography", "cffi",
            "pyrage", "comtypes", "protobuf", "aiofiles")
MARKS = ("LICENSE", "LICENCE", "NOTICE", "COPYING", "THIRDPARTY", "CYCLONEDX")
# Their packages do not carry the text we need.
DOWNLOADS = {
    "Qt/LGPL-3.0.txt": "https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/LGPL-3.0-only.txt",
    "Qt/GPL-3.0.txt": "https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/GPL-3.0-only.txt",
    "OpenSSL/LICENSE.txt": "https://raw.githubusercontent.com/openssl/openssl/openssl-3.0/LICENSE.txt",
    "PortAudio/LICENSE.txt": "https://raw.githubusercontent.com/PortAudio/portaudio/master/LICENSE.txt",
    "flatbuffers/LICENSE.txt": "https://raw.githubusercontent.com/google/flatbuffers/master/LICENSE",
    "tokenizers/LICENSE.txt": "https://raw.githubusercontent.com/huggingface/tokenizers/main/LICENSE",
    "NeMo/LICENSE.txt": "https://raw.githubusercontent.com/NVIDIA/NeMo/main/LICENSE",
}
DIRECTML = "https://api.nuget.org/v3-flatcontainer/microsoft.ai.directml/1.15.4/microsoft.ai.directml.1.15.4.nupkg"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url) as r:
        return r.read()


def copy_package(name: str, out: Path) -> None:
    dist = metadata.distribution(name)
    # Skip files of the Python tooling, such as packaging/licenses/__init__.py.
    found = [f for f in dist.files or [] if f.suffix not in (".py", ".pyc")
             and any(mark in f.name.upper().replace("-", "").replace("_", "") for mark in MARKS)]
    if not found:
        raise SystemExit(f"No license files found for {name}")
    for file in found:
        # Keep the inner path: numpy has several files with the same name.
        parts = file.parts[1:] if file.parts[0].endswith(".dist-info") else file.parts
        dest = out / name / Path(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file.locate(), dest)


def main() -> None:
    out = Path(sys.argv[1])
    for name in PACKAGES:
        copy_package(name, out)
    # Python's file also covers libffi, bzip2 and the Visual C++ runtime it ships.
    (out / "Python").mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(sys.base_prefix) / "LICENSE.txt", out / "Python" / "LICENSE.txt")
    for path, url in DOWNLOADS.items():
        dest = out / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fetch(url))
    with zipfile.ZipFile(io.BytesIO(fetch(DIRECTML))) as z:
        wanted = [n for n in z.namelist() if n.upper().endswith(("LICENSE.TXT", "THIRDPARTYNOTICES.TXT"))]
        if not wanted:
            raise SystemExit("No license files found for DirectML")
        (out / "DirectML").mkdir(parents=True, exist_ok=True)
        for name in wanted:
            (out / "DirectML" / Path(name).name).write_bytes(z.read(name))


if __name__ == "__main__":
    main()
