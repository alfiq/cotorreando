"""Every module imports, which catches broken imports and import-time side effects early."""

import importlib
import pkgutil

import pytest

import cotorreando

# __main__ would start the app; train.py runs inside the separate training environment (torch, NeMo).
EXCLUDED = {"cotorreando.__main__", "cotorreando.lora.train"}
HEAVY = {"torch", "torchaudio", "nemo", "huggingface_hub", "lightning", "omegaconf"}

MODULES = sorted(
    info.name for info in pkgutil.walk_packages(cotorreando.__path__, "cotorreando.") if info.name not in EXCLUDED
)


def test_modules_were_found():
    assert "cotorreando.vault" in MODULES and "cotorreando.dialogs" in MODULES
    assert len(MODULES) >= 20


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as err:
        if (err.name or "").split(".")[0] in HEAVY:
            pytest.skip(f"needs {err.name}, which only the training environment has")
        raise
