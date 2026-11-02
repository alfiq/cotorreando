"""The optional training environment.

Training needs PyTorch and NeMo (several GB), so they never ship with the app.
On demand we fetch ``uv``, create a dedicated virtual environment under the
data folder and install them there. Scripts are then run with that Python.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from pathlib import Path

from ..paths import DATA_DIR, PACKAGE_DIR

# A fixed release checked by hash: this executable gets run, so it must be exactly the one we expect.
UV_URL = "https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip"
UV_SHA256 = "a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f"
TOOLS_DIR = DATA_DIR / "tools"
ENV_DIR = DATA_DIR / "train-env"
PYTHON = ENV_DIR / "Scripts" / "python.exe"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"
# Every package pinned by version and hash; regenerate with scripts/lock_training.ps1.
LOCK = PACKAGE_DIR / "lora" / "requirements-cu128.txt"
LOCK_CPU = PACKAGE_DIR / "lora" / "requirements-cpu.txt"
TRAIN_SCRIPT = PACKAGE_DIR / "lora" / "train.py"
PANELS_SCRIPT = PACKAGE_DIR / "lora" / "panels.py"
NO_WINDOW = subprocess.CREATE_NO_WINDOW
_process: subprocess.Popen | None = None
_install_lock = threading.Lock()


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None


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
        with urllib.request.urlopen(UV_URL, timeout=60) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != UV_SHA256:
            raise RuntimeError("uv download: checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            uv.write_bytes(z.read("uv.exe"))
    return uv


def _stream(cmd: list[str], log, payload: bytes | None = None, extra_env: dict | None = None) -> None:
    """Run ``cmd``, passing each output line to ``log``. ``payload`` goes in through stdin,
    which then stays open so that ``pause`` can talk to the process."""
    global _process
    proc = _process = subprocess.Popen(cmd, stdin=subprocess.PIPE if payload is not None else None,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       creationflags=NO_WINDOW, env={**os.environ, "PYTHONUTF8": "1", **(extra_env or {})})

    def feed():
        try:
            proc.stdin.write(payload)
            proc.stdin.flush()
        except OSError:            # the process ended first; its exit code tells why
            pass

    if payload is not None:
        threading.Thread(target=feed, daemon=True).start()
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace")
        log(line.rstrip())
    if proc.wait():
        raise RuntimeError(f"{cmd[0]} exited with {proc.returncode}")


def _install_locked(log) -> None:
    gpu = has_nvidia()
    _stream([str(_uv()), "pip", "install", "--python", str(PYTHON), "--require-hashes",
             "-r", str(LOCK if gpu else LOCK_CPU),
             "--extra-index-url", TORCH_INDEX if gpu else TORCH_INDEX_CPU,
             "--index-strategy", "unsafe-best-match"], log)


def install(log=print) -> None:
    _stream([str(_uv()), "venv", "--clear", "--python", "3.12", str(ENV_DIR)], log)
    _install_locked(log)


def _has_extras() -> bool:
    code = "import cryptography, bitsandbytes, accelerate"
    return subprocess.run([str(PYTHON), "-c", code], capture_output=True,
                          creationflags=NO_WINDOW).returncode == 0


def ensure_installed(log=print) -> None:
    with _install_lock:
        if not installed():
            install(log)
        elif not _has_extras():    # an environment from before these were needed
            _install_locked(log)


def run_train(args: list[str], log=print, payload: bytes | None = None) -> None:
    # Idle OpenMP threads would otherwise spin on every core between training steps.
    _stream([str(PYTHON), "-u", str(TRAIN_SCRIPT), *args], log, payload, {"KMP_BLOCKTIME": "0"})


def run_panels(payload: bytes, log=print) -> None:
    _stream([str(PYTHON), "-u", str(PANELS_SCRIPT)], log, payload)


def pause() -> None:
    """Ask the running script to save its state and stop; kill it if it cannot be asked."""
    try:
        _process.stdin.write(b"STOP\n")
        _process.stdin.flush()
    except (AttributeError, OSError):
        stop()


def stop() -> None:
    """Called on exit, so that no download or training outlives the app."""
    if _process and _process.poll() is None:
        _process.kill()
