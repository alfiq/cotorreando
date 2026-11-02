r"""Shared fixtures. Paths are frozen at import time, so every copy of them is patched here.

Nothing in the suite may touch the real %LOCALAPPDATA%\Cotorreando: tests that reach
the vault, the settings file or the models folder must use ``isolated_data``.
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from cotorreando import config, paths, vad, vault, vault_legacy
from cotorreando.audio import RATE

PASSWORD = "correct horse battery"
REAL_DATA = paths.DATA_DIR.resolve()

# Every module-level path that points into the data folder: (module, attribute, path under root).
_PATHS = [
    (vault, "VAULT_DIR", "vault"),
    (vault, "RECIPIENT_FILE", "vault/recipient.txt"),
    (vault, "IDENTITY_FILE", "vault/identity.age"),
    (vault, "RECOVERY_FILE", "vault/recovery.age"),
    (vault, "RECORDS_DIR", "vault/records"),
    (vault, "JOURNAL_DIR", "vault/journal"),
    (vault, "TRAINED_FILE", "vault/trained.json"),
    (vault, "RECORDINGS_DIR", "recordings"),
    (vault_legacy, "KEY_FILE", "vault/key.json"),
    (vault_legacy, "UNREADABLE_DIR", "vault/unreadable"),
    (vault_legacy, "VAULT_DIR", "vault"),
    (vault_legacy, "RECORDS_DIR", "vault/records"),
    (vault_legacy, "RECORDINGS_DIR", "recordings"),
    (config, "CONFIG_FILE", "settings.json"),
    (vad, "PATH", "models/silero_vad.onnx"),
    (paths, "DATA_DIR", ""),
    (paths, "MODELS_DIR", "models"),
    (paths, "RECORDINGS_DIR", "recordings"),
    (paths, "CONFIG_FILE", "settings.json"),
]


def _patch(monkeypatch, root: Path) -> None:
    for module, name, rel in _PATHS:
        monkeypatch.setattr(module, name, root / rel if rel else root)
    # Guard: a path left on (or under) the real data folder would let a test damage user data.
    for module, name, _ in _PATHS:
        path = Path(getattr(module, name)).resolve()
        assert REAL_DATA not in (path, *path.parents), f"{module.__name__}.{name} points at real data"


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Point every data path at a throwaway folder and return it."""
    root = tmp_path / "data"
    root.mkdir()
    _patch(monkeypatch, root)
    return root


@pytest.fixture(scope="session")
def _template(tmp_path_factory):
    """One vault created once (scrypt is slow), copied into each test that needs a key."""
    root = tmp_path_factory.mktemp("template")
    mp = pytest.MonkeyPatch()
    _patch(mp, root)
    try:
        v = vault.Vault()
        code = v.create(PASSWORD)
        files = {p.name: p.read_bytes() for p in vault.VAULT_DIR.iterdir() if p.is_file()}
        return files, v._identity, code
    finally:
        mp.undo()


@pytest.fixture(name="vault")
def _empty_vault(isolated_data):
    """A fresh, empty vault object (no key yet)."""
    return vault.Vault()


@pytest.fixture
def unlocked_vault(isolated_data, _template):
    """A vault with a key already on disk and unlocked; ``.code`` and ``.password`` are attached."""
    files, identity, code = _template
    vault.VAULT_DIR.mkdir(parents=True)
    for name, data in files.items():
        (vault.VAULT_DIR / name).write_bytes(data)
    v = vault.Vault()
    v._identity = identity
    v.code, v.password = code, PASSWORD
    return v


@pytest.fixture
def fake_audio():
    """Half a second of a 440 Hz sine at the app's sample rate."""
    t = np.arange(RATE // 2) / RATE
    return (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole run, torn down before Python exits.

    Left to the interpreter's shutdown, Qt objects can be freed after the application
    and crash the process (exit code 0xC0000005) even though every test passed.
    """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    app.shutdown()
