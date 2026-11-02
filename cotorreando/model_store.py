"""Getting the speech model onto disk safely, and checking a folder holds one we can run.

Downloads go to ``<name>.part`` and are renamed only once their size (and, when
Hugging Face publishes it, their SHA-256) matches, so a cut download is never
mistaken for a model. A ``.part`` left behind is resumed with an HTTP Range request.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import os
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

ONNX_REPO = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/"
FILES = ("config.json", "vocab.txt", "nemo128.onnx",
         "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx")
MANIFEST = "download.json"     # sizes of the files as verified after download
EXPECTED_BYTES = 700 * 1024 ** 2   # used for the space check when the server gives no sizes
SPACE_MARGIN = 50 * 1024 ** 2
TIMEOUT_S = 30
CHUNK = 1 << 20

# What asr.Parakeet runs: the onnx-asr layout of a NeMo FastConformer TDT model.
PREPROCESSOR = "nemo128.onnx"
ENCODER, DECODER = "encoder-model", "decoder_joint-model"
INPUTS = {
    PREPROCESSOR: {"waveforms", "waveforms_lens"},
    ENCODER: {"audio_signal", "length"},
    DECODER: {"encoder_outputs", "targets", "target_length", "input_states_1", "input_states_2"},
}
OUTPUTS = {PREPROCESSOR: 2, ENCODER: 2, DECODER: 4}


class ModelError(Exception):
    """A problem to show the user: an i18n key plus its arguments."""

    def __init__(self, key: str, **kw):
        super().__init__(key, kw)
        self.key, self.kw = key, kw


class NoConnection(ModelError):
    def __init__(self, detail=""):
        super().__init__("dl_offline", detail=detail)


class DownloadFailed(ModelError):
    def __init__(self, detail=""):
        super().__init__("dl_interrupted", detail=detail)


class NotEnoughSpace(ModelError):
    def __init__(self, needed: int, free: int):
        super().__init__("dl_no_space", needed=_mb(needed), free=_mb(free))
        self.needed, self.free = needed, free


class Cancelled(ModelError):
    def __init__(self):
        super().__init__("dl_cancelled")


class InvalidModel(ModelError):
    pass


def _mb(n: int) -> str:
    return f"{n / 1024 ** 2:,.0f} MB"


# -- downloading ---------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _head(url: str) -> dict:
    """Headers of ``url`` before the redirect to the CDN: that is where Hugging Face
    puts the real size and SHA-256 of large files (X-Linked-Size, X-Linked-Etag)."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, method="HEAD"), timeout=TIMEOUT_S) as r:
            return dict(r.headers)
    except urllib.error.HTTPError as err:
        if 300 <= err.code < 400:
            return dict(err.headers)
        raise


def _open(url: str, start: int):
    """The response for ``url`` from byte ``start`` on (status 206 if the server honoured it)."""
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    return urllib.request.urlopen(request, timeout=TIMEOUT_S)


def _remote(url: str) -> tuple[int | None, str | None]:
    headers = {k.lower(): v for k, v in _head(url).items()}
    size = headers.get("x-linked-size") or headers.get("content-length")
    digest = (headers.get("x-linked-etag") or "").strip('"').lower()
    is_sha = len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
    return (int(size) if size and size.isdigit() else None), (digest if is_sha else None)


def _network_error(err: Exception) -> ModelError:
    if isinstance(err, urllib.error.HTTPError):
        return DownloadFailed(f"HTTP {err.code}")
    if isinstance(err, urllib.error.URLError) and not isinstance(err.reason, socket.timeout):
        return NoConnection(str(err.reason))
    return DownloadFailed(str(err))


def is_complete(directory: Path, files=FILES) -> bool:
    """Every file is there, and as big as it was when its download was verified."""
    return all(_verified(directory, f, _manifest(directory)) for f in files)


def _manifest(directory: Path) -> dict:
    try:
        sizes = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}      # downloaded by an older version, before there was a manifest
    return sizes if isinstance(sizes, dict) else {}


def _verified(directory: Path, name: str, sizes: dict) -> bool:
    path = directory / name
    return path.is_file() and sizes.get(name, path.stat().st_size) == path.stat().st_size


def remove(directory: Path, files=FILES) -> None:
    """Delete the downloaded files (and partial ones) so the next download starts clean."""
    for name in (*files, *(f + ".part" for f in files), MANIFEST):
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError as err:
            log.warning("Could not delete %s: %s", name, err)


def download(target: Path, progress=lambda done, total: None, cancelled=lambda: False,
             base: str = ONNX_REPO, files=FILES) -> Path:
    """Fetch every missing file into ``target``. Raises a ModelError on any problem."""
    target.mkdir(parents=True, exist_ok=True)
    sizes = _manifest(target)
    missing = [f for f in files if not _verified(target, f, sizes)]
    for name in missing:            # a file that changed since it was verified is fetched again
        (target / name).unlink(missing_ok=True)
    try:
        remote = {name: _remote(base + name) for name in missing}
    except (OSError, http.client.HTTPException) as err:
        raise _network_error(err) from err

    lengths = [remote[n][0] for n in missing]
    have = {n: _part(target, n).stat().st_size if _part(target, n).exists() else 0 for n in missing}
    if all(s is not None for s in lengths):
        needed = sum(s - min(have[n], s) for n, s in zip(missing, lengths))
        total = sum(lengths)
    else:
        needed, total = max(EXPECTED_BYTES - sum(have.values()), 0), 0
    free = shutil.disk_usage(target).free
    if free < needed + SPACE_MARGIN:
        raise NotEnoughSpace(needed + SPACE_MARGIN, free)

    done = sum(have.values())
    for name in missing:
        size, digest = remote[name]
        try:
            done = _fetch(base + name, target / name, size, digest, done, total, progress, cancelled)
        except OSError as err:
            if getattr(err, "errno", None) == 28:   # ENOSPC
                raise NotEnoughSpace(needed + SPACE_MARGIN, shutil.disk_usage(target).free) from err
            raise _network_error(err) from err
        except http.client.HTTPException as err:
            raise DownloadFailed(str(err)) from err

    manifest = {f: (target / f).stat().st_size for f in files}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return target


def _part(target: Path, name: str) -> Path:
    return target / (name + ".part")


def _fetch(url, dest: Path, size, digest, done, total, progress, cancelled) -> int:
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    if size is not None and start > size:
        part.unlink()
        done, start = done - start, 0
    if size is None or start < size or not part.exists():
        with _open(url, start) as r:
            if start and getattr(r, "status", 200) != 206:   # no resume: start over
                done, start = done - start, 0
            with open(part, "ab" if start else "wb") as f:
                while chunk := r.read(CHUNK):
                    if cancelled():
                        raise Cancelled()
                    f.write(chunk)
                    done += len(chunk)
                    progress(done, total)
    got = part.stat().st_size
    if size is not None and got != size:
        if got > size:
            part.unlink()
        raise DownloadFailed(f"{dest.name}: {got} of {size} bytes")
    if digest and _sha256(part) != digest:
        part.unlink()   # resumed onto bad bytes or corrupted: never resume from this
        raise DownloadFailed(f"{dest.name}: checksum mismatch")
    os.replace(part, dest)
    return done


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


class Rate:
    """Smoothed download speed and time left, for the progress label."""

    def __init__(self):
        self.t0, self.d0, self.speed = None, 0, 0.0

    def update(self, done: int, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        if self.t0 is None:
            self.t0, self.d0 = now, done
        elif now - self.t0 >= 0.5:
            current = (done - self.d0) / (now - self.t0)
            self.speed = current if not self.speed else 0.7 * self.speed + 0.3 * current
            self.t0, self.d0 = now, done
        return self.speed


# -- checking a user's own model ------------------------------------------------

def _session(path: Path):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def pick(directory: Path, stem: str) -> str | None:
    """The int8 graph if there is one, else the full-precision one."""
    for name in (f"{stem}.int8.onnx", f"{stem}.onnx"):
        if (directory / name).is_file():
            return name
    return None


def read_vocab(path: Path) -> dict[int, str]:
    """``vocab.txt``: one ``<token> <id>`` per line, ``▁`` marking a word start."""
    vocab = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        token, _, index = line.rpartition(" ")
        if not token or not index.isdigit():
            raise InvalidModel("model_bad_vocab", line=n)
        vocab[int(index)] = token
    if len(vocab) < 2:
        raise InvalidModel("model_bad_vocab", line=0)
    return vocab


def validate(directory: Path | str) -> None:
    """Raise InvalidModel unless ``directory`` holds a model asr.Parakeet can run.

    Loads each graph in ONNX Runtime (CPU) and checks its input and output names.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise InvalidModel("model_no_folder", path=str(directory))
    graphs = {PREPROCESSOR: PREPROCESSOR if (directory / PREPROCESSOR).is_file() else None,
              ENCODER: pick(directory, ENCODER), DECODER: pick(directory, DECODER)}
    missing = [] if (directory / "vocab.txt").is_file() else ["vocab.txt"]
    missing += [stem if stem.endswith(".onnx") else f"{stem}(.int8).onnx"
                for stem, name in graphs.items() if name is None]
    if missing:
        raise InvalidModel("model_missing", files=", ".join(missing))
    vocab = read_vocab(directory / "vocab.txt")
    sessions = {}
    for stem, name in graphs.items():
        try:
            sessions[stem] = _session(directory / name)
        except Exception as err:   # onnxruntime raises its own exception types
            raise InvalidModel("model_bad_onnx", file=name, detail=str(err).splitlines()[0][:200]) from err
        inputs = {i.name for i in sessions[stem].get_inputs()}
        outputs = sessions[stem].get_outputs()
        if not INPUTS[stem] <= inputs or len(outputs) != OUTPUTS[stem]:
            raise InvalidModel("model_bad_names", file=name,
                               expected=", ".join(sorted(INPUTS[stem])), found=", ".join(sorted(inputs)))
    decoder = sessions[DECODER]
    states = {i.name: i.shape for i in decoder.get_inputs()}
    if len(states["input_states_1"]) != 3:
        raise InvalidModel("model_bad_names", file=graphs[DECODER], expected="input_states_1 [layers, batch, hidden]",
                           found=str(states["input_states_1"]))
    # TDT: the joint outputs every token, the blank, then the durations. RNN-T or CTC stop at the blank.
    width = decoder.get_outputs()[0].shape[-1]
    if isinstance(width, int) and width <= max(vocab) + 1:
        raise InvalidModel("model_not_tdt", width=width, vocab=max(vocab) + 1)
