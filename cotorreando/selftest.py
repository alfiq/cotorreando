"""`--self-test`: checks that a build can load everything it needs, without opening anything.

Run as `Cotorreando.exe --self-test [--self-test-log <path>]` (or `python -m cotorreando
--self-test`). It imports every module, runs a tiny ONNX model, loads the native libraries of
livekit, PortAudio, tokenizers, cryptography, pyrage and comtypes, and creates a QApplication
without showing any window. It never writes to the user's data folder. One line per check; the
exit code is 0 when everything passed. The windowed build has no console, so the lines also go
to the file given with `--self-test-log`.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from collections.abc import Callable

# Only the training environment has these; the app runs train.py in a separate process.
HEAVY = {"torch", "torchaudio", "nemo", "huggingface_hub", "lightning", "omegaconf"}
# __main__ would start the app; train.py runs inside the training environment.
EXCLUDED = {"cotorreando.__main__", "cotorreando.lora.train"}
# A walk that finds fewer than these means the build lost modules, not that they are fine.
REQUIRED = {"cotorreando.app", "cotorreando.asr", "cotorreando.audio", "cotorreando.dialogs", "cotorreando.vault"}


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number: int, payload: bytes | str | int) -> bytes:
    """One protobuf field: varint for ints, length-delimited for bytes and strings."""
    if isinstance(payload, int):
        return _varint(number << 3) + _varint(payload)
    if isinstance(payload, str):
        payload = payload.encode()
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def tiny_onnx_model() -> bytes:
    """An ONNX model with one Add node, y = x + x, on a float tensor of 3 values.

    Serialized by hand so the check needs neither the real model nor the `onnx` package.
    """

    def tensor_info(name: str) -> bytes:
        dim = _field(1, _field(1, 3))  # TensorShapeProto.dim { dim_value: 3 }
        tensor = _field(1, 1) + _field(2, dim)  # elem_type FLOAT, shape
        return _field(1, name) + _field(2, _field(1, tensor))  # ValueInfoProto: name, TypeProto

    node = _field(1, "x") + _field(1, "x") + _field(2, "y") + _field(3, "add") + _field(4, "Add")
    graph = _field(1, node) + _field(2, "selftest") + _field(11, tensor_info("x")) + _field(12, tensor_info("y"))
    opset = _field(1, "") + _field(2, 13)
    return _field(1, 8) + _field(7, graph) + _field(8, opset)  # ir_version 8, graph, opset 13


def check_modules() -> str:
    import cotorreando

    names = {info.name for info in pkgutil.walk_packages(cotorreando.__path__, "cotorreando.")}
    names |= REQUIRED
    skipped = []
    for name in sorted(names - EXCLUDED):
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as err:
            if (err.name or "").split(".")[0] not in HEAVY:
                raise
            skipped.append(name)
    note = f", {len(skipped)} need the training environment" if skipped else ""
    return f"{len(names - EXCLUDED)} modules{note}"


def check_onnxruntime() -> str:
    import numpy as np
    import onnxruntime as ort

    model = tiny_onnx_model()
    x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    errors = []
    for provider in ("DmlExecutionProvider", "CPUExecutionProvider"):
        if provider not in ort.get_available_providers():
            errors.append(f"{provider} not available")
            continue
        try:
            session = ort.InferenceSession(model, providers=[provider])
            (y,) = session.run(None, {"x": x})
        except Exception as err:  # noqa: BLE001 - DirectML may be missing on the machine; try the CPU
            errors.append(f"{provider}: {err}")
            continue
        if not np.allclose(y, x + x):
            raise RuntimeError(f"{provider} computed {y}, expected {x + x}")
        note = f" ({'; '.join(errors)})" if errors else ""
        return f"onnxruntime {ort.__version__}, {provider}{note}"
    raise RuntimeError("; ".join(errors))


def check_livekit() -> str:
    from livekit import rtc  # noqa: F401
    from livekit.rtc._ffi_client import get_ffi_lib

    # Loading the library is the point: a build once shipped without livekit_ffi.dll.
    lib = get_ffi_lib()
    lib.livekit_ffi_initialize  # noqa: B018 - raises AttributeError if the symbol is missing
    return f"livekit_ffi loaded from {lib._name}"  # noqa: SLF001


def check_portaudio() -> str:
    import pyaudiowpatch as pyaudio  # a missing PortAudio DLL fails here

    try:
        audio = pyaudio.PyAudio()
    except Exception as err:  # noqa: BLE001 - a machine without audio devices is not a broken build
        return f"PortAudio loaded, no audio devices ({err})"
    try:
        count = audio.get_device_count()
    finally:
        audio.terminate()
    return f"PortAudio {pyaudio.get_portaudio_version_text()}, {count} devices"


def check_tokenizers() -> str:
    import tokenizers
    from tokenizers.models import WordLevel

    tokenizer = tokenizers.Tokenizer(WordLevel({"hola": 0, "[UNK]": 1}, unk_token="[UNK]"))
    if tokenizer.encode("hola").ids != [0]:
        raise RuntimeError("unexpected encoding")
    return f"tokenizers {tokenizers.__version__}"


def check_cryptography() -> str:
    import cryptography
    from cryptography.hazmat.primitives import hashes

    digest = hashes.Hash(hashes.SHA256())
    digest.update(b"cotorreando")
    digest.finalize()
    return f"cryptography {cryptography.__version__}"


def check_pyrage() -> str:
    import pyrage
    from pyrage import x25519

    identity = x25519.Identity.generate()
    secret = pyrage.encrypt(b"cotorreando", [identity.to_public()])
    if pyrage.decrypt(secret, [identity]) != b"cotorreando":
        raise RuntimeError("round trip failed")
    return "pyrage encrypt and decrypt"


def check_comtypes() -> str:
    import comtypes
    import comtypes.client  # noqa: F401

    return f"comtypes {comtypes.__version__}"


def check_qt() -> str:
    # Without a platform given, Qt uses the one the app uses (windows); no window is shown.
    from PySide6 import __version__ as pyside_version
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    return f"PySide6 {pyside_version}, platform {app.platformName()}"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("modules", check_modules),
    ("onnxruntime", check_onnxruntime),
    ("livekit", check_livekit),
    ("portaudio", check_portaudio),
    ("tokenizers", check_tokenizers),
    ("cryptography", check_cryptography),
    ("pyrage", check_pyrage),
    ("comtypes", check_comtypes),
    ("qt", check_qt),
]


def run(argv: list[str]) -> int:
    log_path = None
    if "--self-test-log" in argv:
        index = argv.index("--self-test-log")
        if index + 1 >= len(argv):
            print("--self-test-log needs a path", file=sys.stderr if sys.stderr else None)
            return 2
        log_path = argv[index + 1]
    log = open(log_path, "w", encoding="utf-8") if log_path else None  # noqa: SIM115

    def say(line: str) -> None:
        if sys.stdout is not None:  # the windowed build has no console
            print(line, flush=True)
        if log is not None:
            log.write(line + "\n")
            log.flush()

    failed = 0
    try:
        say(f"Cotorreando self-test, Python {sys.version.split()[0]}, frozen={_frozen()}")
        for name, check in CHECKS:
            try:
                say(f"ok    {name}: {check()}")
            except BaseException as err:  # noqa: BLE001 - report every check, whatever it raised
                failed += 1
                say(f"FAIL  {name}: {type(err).__name__}: {err}")
                for line in traceback.format_exc().rstrip().splitlines():
                    say(f"      {line}")
        say("self-test passed" if not failed else f"self-test failed: {failed} of {len(CHECKS)} checks")
    finally:
        if log is not None:
            log.close()
    return 1 if failed else 0


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())
