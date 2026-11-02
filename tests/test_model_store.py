"""Model download and custom-model checks. No network, no real disk-full, never the real model."""

import hashlib
import json
import shutil
import urllib.error
from collections import namedtuple
from types import SimpleNamespace

import pytest

from cotorreando import asr, model_store
from cotorreando.model_store import (Cancelled, DownloadFailed, InvalidModel, NoConnection,
                                     NotEnoughSpace)

BASE = "https://example.invalid/"
FILES = {name: bytes([i + 1]) * (1000 * (i + 1)) for i, name in enumerate(model_store.FILES)}
Usage = namedtuple("Usage", "total used free")


class Response:
    """A fake HTTP response; ``cut`` makes the connection drop after that many bytes."""

    def __init__(self, data: bytes, status=200, cut=None):
        self.data, self.status, self.cut, self.pos = data, status, cut, 0

    def read(self, n):
        if self.cut is not None and self.pos >= self.cut:
            raise ConnectionResetError("connection reset")
        end = self.pos + min(n, 300) if self.cut is None else min(self.pos + min(n, 300), self.cut)
        chunk, self.pos = self.data[self.pos:end], end
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Server:
    """Serves FILES; ``honour_range`` and ``cut`` per file shape the replies."""

    def __init__(self, files=FILES, honour_range=True, digests=True):
        self.files, self.honour_range, self.digests = dict(files), honour_range, digests
        self.cut, self.opened = {}, []

    def head(self, url):
        data = self.files[url[len(BASE):]]
        headers = {"X-Linked-Size": str(len(data))}
        if self.digests:
            headers["X-Linked-Etag"] = '"%s"' % hashlib.sha256(data).hexdigest()
        return headers

    def open(self, url, start):
        name = url[len(BASE):]
        self.opened.append((name, start))
        data = self.files[name]
        if start and self.honour_range:
            return Response(data[start:], 206, self.cut.pop(name, None))
        return Response(data, 200, self.cut.pop(name, None))


@pytest.fixture
def server(monkeypatch):
    s = Server()
    monkeypatch.setattr(model_store, "_head", s.head)
    monkeypatch.setattr(model_store, "_open", s.open)
    monkeypatch.setattr(model_store, "CHUNK", 300)
    return s


@pytest.fixture
def target(isolated_data):
    return isolated_data / "models" / "parakeet"


def fetch(target, **kw):
    return model_store.download(target, base=BASE, **kw)


def assert_no_model(target):
    assert not model_store.is_complete(target)
    for name in FILES:
        assert not (target / name).exists(), name


def test_downloads_every_file_and_writes_a_manifest(server, target):
    seen = []
    fetch(target, progress=lambda done, total: seen.append((done, total)))
    assert model_store.is_complete(target)
    for name, data in FILES.items():
        assert (target / name).read_bytes() == data
        assert not (target / (name + ".part")).exists()
    total = sum(map(len, FILES.values()))
    assert seen[-1] == (total, total)
    assert json.loads((target / model_store.MANIFEST).read_text())["vocab.txt"] == len(FILES["vocab.txt"])


def test_no_connection_is_a_clear_error(monkeypatch, target):
    def offline(url):
        raise urllib.error.URLError(OSError(11001, "getaddrinfo failed"))
    monkeypatch.setattr(model_store, "_head", offline)
    with pytest.raises(NoConnection) as err:
        fetch(target)
    assert err.value.key == "dl_offline"
    assert_no_model(target)


def test_http_error_is_not_mistaken_for_offline(monkeypatch, target):
    def missing(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(model_store, "_head", missing)
    with pytest.raises(DownloadFailed):
        fetch(target)


def test_not_enough_space_is_checked_before_downloading(server, target, monkeypatch):
    monkeypatch.setattr(model_store.shutil, "disk_usage", lambda path: Usage(10 ** 9, 10 ** 9, 1234))
    with pytest.raises(NotEnoughSpace) as err:
        fetch(target)
    assert err.value.free == 1234
    assert err.value.needed >= sum(map(len, FILES.values()))
    assert "MB" in err.value.kw["needed"]
    assert server.opened == []
    assert_no_model(target)


def test_space_check_without_sizes_uses_the_estimate(server, target, monkeypatch):
    server.head = lambda url: {}
    monkeypatch.setattr(model_store, "_head", server.head)
    monkeypatch.setattr(model_store.shutil, "disk_usage",
                        lambda path: Usage(10 ** 9, 0, model_store.EXPECTED_BYTES - 1))
    with pytest.raises(NotEnoughSpace):
        fetch(target)


def test_interrupted_download_leaves_no_model_and_resumes(server, target):
    big = "encoder-model.int8.onnx"
    server.cut[big] = 1000
    with pytest.raises(DownloadFailed):
        fetch(target)
    assert not model_store.is_complete(target)
    assert not (target / big).exists()
    assert (target / (big + ".part")).stat().st_size == 1000
    assert not asr.is_downloaded(target)

    fetch(target)
    assert (big, 1000) in server.opened            # resumed with a Range request
    assert (target / big).read_bytes() == FILES[big]
    assert model_store.is_complete(target)


def test_retry_restarts_cleanly_when_the_server_ignores_range(server, target):
    big = "encoder-model.int8.onnx"
    server.cut[big] = 900
    with pytest.raises(DownloadFailed):
        fetch(target)
    server.honour_range = False
    fetch(target)
    assert (target / big).read_bytes() == FILES[big]


def test_checksum_mismatch_discards_the_file(server, target, monkeypatch):
    name = "decoder_joint-model.int8.onnx"
    real = FILES[name]
    server.files[name] = b"x" * len(real)          # right size, wrong bytes
    honest = server.head
    monkeypatch.setattr(model_store, "_head", lambda url: honest(url) if not url.endswith(name) else
                        {"X-Linked-Size": str(len(real)), "X-Linked-Etag": hashlib.sha256(real).hexdigest()})
    with pytest.raises(DownloadFailed, match="checksum"):
        fetch(target)
    assert not (target / name).exists()
    assert not (target / (name + ".part")).exists()
    assert not model_store.is_complete(target)


def test_short_file_without_digest_is_rejected(server, target):
    server.digests = False
    name = "nemo128.onnx"
    server.cut[name] = 10
    with pytest.raises(DownloadFailed):
        fetch(target)
    assert not (target / name).exists()


def test_cancel_keeps_no_model(server, target):
    with pytest.raises(Cancelled):
        fetch(target, cancelled=lambda: True)
    assert_no_model(target)


def test_disk_full_while_writing(server, target, monkeypatch):
    real_open = open

    class Full:
        def __init__(self, f):
            self.f = f

        def write(self, data):
            raise OSError(28, "No space left on device")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.f.close()

    monkeypatch.setattr(model_store, "open", lambda *a, **k: Full(real_open(*a, **k)), raising=False)
    with pytest.raises(NotEnoughSpace):
        fetch(target)
    assert_no_model(target)


def test_truncated_file_after_download_is_not_a_model(server, target):
    fetch(target)
    name = "encoder-model.int8.onnx"
    (target / name).write_bytes(FILES[name][:10])
    assert not model_store.is_complete(target)
    fetch(target)                                  # fetched again, not trusted
    assert (target / name).read_bytes() == FILES[name]


def test_files_without_manifest_count_as_downloaded(target):
    target.mkdir(parents=True)
    for name, data in FILES.items():
        (target / name).write_bytes(data)
    assert model_store.is_complete(target)


def test_remove_clears_files_and_parts(server, target):
    fetch(target)
    (target / "vocab.txt.part").write_bytes(b"x")
    model_store.remove(target)
    assert not any(target.iterdir())


def test_rate_reports_speed():
    rate = model_store.Rate()
    rate.update(0, now=0.0)
    assert rate.update(10_000_000, now=1.0) == pytest.approx(10_000_000)


# -- custom model folders --------------------------------------------------------

Arg = namedtuple("Arg", "name shape")


def fake_session(inputs, outputs):
    return SimpleNamespace(get_inputs=lambda: [Arg(n, s) for n, s in inputs],
                           get_outputs=lambda: [Arg(n, s) for n, s in outputs])


VOCAB = 8   # ids 0..7, 7 is the blank
GOOD = {
    "nemo128.onnx": fake_session([("waveforms", [1, "n"]), ("waveforms_lens", [1])],
                                 [("features", [1, 128, "t"]), ("features_lens", [1])]),
    "encoder-model.onnx": fake_session([("audio_signal", [1, 128, "t"]), ("length", [1])],
                                       [("outputs", [1, 1024, "t"]), ("encoded_lengths", [1])]),
    "decoder_joint-model.onnx": fake_session(
        [("encoder_outputs", [1, 1024, 1]), ("targets", [1, 1]), ("target_length", [1]),
         ("input_states_1", [2, 1, 640]), ("input_states_2", [2, 1, 640])],
        [("outputs", [1, 1, 1, VOCAB + 5]), ("prednet_lengths", [1]), ("output_states_1", [2, 1, 640]),
         ("output_states_2", [2, 1, 640])]),
}


@pytest.fixture
def sessions(monkeypatch):
    """What each graph 'loads' as; tests swap entries for broken ones."""
    loaded = dict(GOOD)
    monkeypatch.setattr(model_store, "_session", lambda path: loaded[path.name.replace(".int8", "")])
    return loaded


@pytest.fixture
def folder(tmp_path, sessions):
    """A folder with tiny stand-in files."""
    root = tmp_path / "mine"
    root.mkdir()
    (root / "vocab.txt").write_text("".join(f"▁t{i} {i}\n" for i in range(VOCAB - 1)) + f"<blk> {VOCAB - 1}\n",
                                    encoding="utf-8")
    for name in GOOD:
        (root / name).write_bytes(b"stand-in")
    return root


def reason(folder):
    with pytest.raises(InvalidModel) as err:
        model_store.validate(folder)
    return err.value


def test_valid_custom_folder_passes(folder):
    model_store.validate(folder)


def test_int8_variants_are_accepted(folder):
    (folder / "encoder-model.onnx").rename(folder / "encoder-model.int8.onnx")
    model_store.validate(folder)


def test_missing_folder(tmp_path):
    assert reason(tmp_path / "nope").key == "model_no_folder"


def test_missing_files_are_named(folder):
    (folder / "vocab.txt").unlink()
    (folder / "decoder_joint-model.onnx").unlink()
    err = reason(folder)
    assert err.key == "model_missing"
    assert "vocab.txt" in err.kw["files"] and "decoder_joint-model" in err.kw["files"]


def test_empty_folder_lists_everything(tmp_path):
    err = reason(tmp_path)
    assert err.key == "model_missing"
    for name in ("vocab.txt", "nemo128.onnx", "encoder-model", "decoder_joint-model"):
        assert name in err.kw["files"]


def test_bad_vocab(folder):
    (folder / "vocab.txt").write_text("just words\nno ids\n", encoding="utf-8")
    assert reason(folder).key == "model_bad_vocab"


def test_garbage_onnx_is_rejected_by_onnxruntime(folder, monkeypatch):
    monkeypatch.undo()                             # use the real loader on a few bytes of junk
    err = reason(folder)
    assert err.key == "model_bad_onnx" and err.kw["file"] == "nemo128.onnx"


def test_wrong_input_names(folder, sessions):
    sessions["encoder-model.onnx"] = fake_session([("input_features", [1, 80, "t"])],
                                                         [("a", [1]), ("b", [1])])
    err = reason(folder)
    assert err.key == "model_bad_names" and "audio_signal" in err.kw["expected"]


def test_wrong_number_of_outputs(folder, sessions):
    good = GOOD["decoder_joint-model.onnx"]
    sessions["decoder_joint-model.onnx"] = fake_session(
        [(a.name, a.shape) for a in good.get_inputs()], [("logits", [1, 1, 1, VOCAB])])
    assert reason(folder).key == "model_bad_names"


def test_rnnt_or_ctc_joint_is_not_tdt(folder, sessions):
    good = GOOD["decoder_joint-model.onnx"]
    outputs = [(a.name, a.shape) for a in good.get_outputs()]
    outputs[0] = ("outputs", [1, 1, 1, VOCAB])     # tokens + blank, no durations
    sessions["decoder_joint-model.onnx"] = fake_session([(a.name, a.shape) for a in good.get_inputs()],
                                                               outputs)
    assert reason(folder).key == "model_not_tdt"


def test_custom_model_is_a_machine_setting():
    from cotorreando import transfer
    from cotorreando.config import Settings
    assert "custom_model" in transfer.MACHINE_FIELDS
    assert "custom_model" in {f for f in Settings.__dataclass_fields__}


def test_custom_model_without_tokenizer_never_fetches(tmp_path, monkeypatch):
    monkeypatch.setattr(asr.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    assert asr.phrase_tokenizer(tmp_path, fetch=False) is None
