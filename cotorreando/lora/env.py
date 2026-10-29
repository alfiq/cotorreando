"""The optional training environment.

Training needs PyTorch and NeMo (several GB), so they never ship with the app.
On demand we fetch ``uv``, create a dedicated virtual environment under the
data folder and install them there. Scripts are then run with that Python.
"""

from __future__ import annotations

import io
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from ..paths import DATA_DIR, PACKAGE_DIR

UV_URL = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
TOOLS_DIR = DATA_DIR / "tools"
ENV_DIR = DATA_DIR / "train-env"
PYTHON = ENV_DIR / "Scripts" / "python.exe"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
PACKAGES = ["nemo_toolkit[asr]", "onnx", "onnxruntime"]
TRAIN_SCRIPT = PACKAGE_DIR / "lora" / "train.py"
NO_WINDOW = subprocess.CREATE_NO_WINDOW


def installed() -> bool:
    if not PYTHON.exists():
        return False
    probe = subprocess.run([str(PYTHON), "-c", "import nemo.collections.asr, torch"],
                           capture_output=True, creationflags=NO_WINDOW)
    return probe.returncode == 0


def _uv() -> Path:
    uv = TOOLS_DIR / "uv.exe"
    if not uv.exists():
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(UV_URL) as r:
            with zipfile.ZipFile(io.BytesIO(r.read())) as z:
                uv.write_bytes(z.read("uv.exe"))
    return uv


def _stream(cmd: list[str], log) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    for line in proc.stdout:
        log(line.rstrip())
    if proc.wait():
        raise RuntimeError(f"{cmd[0]} exited with {proc.returncode}")


def install(log=print) -> None:
    uv = str(_uv())
    _stream([uv, "venv", "--python", "3.12", str(ENV_DIR)], log)
    _stream([uv, "pip", "install", "--python", str(PYTHON), "torch", "torchaudio",
             "--index-url", TORCH_INDEX], log)
    _stream([uv, "pip", "install", "--python", str(PYTHON), *PACKAGES], log)


def run_train(args: list[str], log=print) -> None:
    _stream([str(PYTHON), "-u", str(TRAIN_SCRIPT), *args], log)
