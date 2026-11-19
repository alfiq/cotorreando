"""Decoding and streaming with fake ONNX sessions: the TDT greedy loop, blocks, state and vocabulary.

The fake encoder writes each frame's answer into the audio itself: the first sample of frame ``f`` is
the token the fake decoder must emit, and the second is its duration (skip). Frames therefore reach the
real ``Parakeet.decode`` and ``Stream`` code exactly as the encoder output would, and the expected text
can be worked out by hand. The one test with the real model is skipped when it is not downloaded.
"""

import random
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cotorreando import asr
from cotorreando.asr import SAMPLE_RATE, DecoderState, Parakeet, Stream
from cotorreando.boosting import BoostingTree

FRAME = Stream.FRAME  # 80 ms of audio per encoder frame
VOCAB = {0: " hola", 1: " mundo", 2: " que", 3: " tal", 4: ".", 5: "<blk>"}
BLANK = 5
NUM_DURATIONS = 5


class FakePreprocessor:
    def run(self, _outputs, feeds):
        wave_ = feeds["waveforms"]
        return [wave_.copy(), np.array([wave_.shape[1]], np.int64)]


class FakeEncoder:
    """One frame per FRAME samples; frame f carries (token, skip) in its first two samples."""

    def __init__(self):
        self.calls = 0

    def run(self, _outputs, feeds):
        self.calls += 1
        audio = feeds["audio_signal"][0]
        frames = audio.size // FRAME
        encoded = np.zeros((1024, frames), np.float32)
        encoded[0] = audio[: frames * FRAME : FRAME]
        encoded[1] = audio[1 : frames * FRAME : FRAME]
        return [encoded[None], np.array([frames], np.int64)]


class FakeDecoder:
    """Predicts the token and the duration written in the frame it is asked about."""

    def run(self, _outputs, feeds):
        frame = feeds["encoder_outputs"][0, :, 0]
        token, skip = int(frame[0]), int(frame[1])
        logits = np.zeros(BLANK + 1 + NUM_DURATIONS, np.float32)
        logits[token] = 10.0
        logits[BLANK + 1 + skip] = 10.0
        # the state changes on every call, so a reset is visible
        return [logits.reshape(1, 1, -1), np.array([1]), feeds["input_states_1"] + 1, feeds["input_states_2"] + 1]

    def get_inputs(self):
        return [SimpleNamespace(shape=(2, 1, 4))] * 4


def make_model():
    m = object.__new__(Parakeet)
    m.preprocessor, m.encoder, m.decoder = FakePreprocessor(), FakeEncoder(), FakeDecoder()
    m.vocab, m.blank, m.state_shape, m.on_gpu = dict(VOCAB), BLANK, (2, 1, 4), False
    m.boost, m.boost_alpha, m._boost_key, m._tokenizer = None, 1.0, None, None
    m._tokenizer_failed = None
    m.tokenizer_dir, m.fetch_tokenizer, m.closed = Path("unused"), False, False
    return m


def audio_for(frames):
    """Audio whose frame ``f`` asks the fake decoder for ``frames[f] = (token, skip)``."""
    x = np.zeros(len(frames) * FRAME, np.float32)
    for f, (token, skip) in enumerate(frames):
        x[f * FRAME], x[f * FRAME + 1] = token, skip
    return x


def reference(frames):
    """Greedy TDT by hand: emit the token of each visited frame, then jump by its duration."""
    out, t = [], 0
    while t < len(frames):
        token, skip = frames[t]
        if token != BLANK:
            out.append(VOCAB[token])
        t += max(skip, 1)
    return "".join(out).strip()


def random_frames(seed, n=80):
    rng = random.Random(seed)
    return [(rng.choice([0, 1, 2, 3, 4, BLANK]), rng.choice([1, 1, 2, 3])) for _ in range(n)]


@pytest.fixture
def model():
    return make_model()


# -- greedy decoding ------------------------------------------------------------------


def test_each_frame_emits_its_token_and_the_duration_moves_on(model):
    frames = [(0, 1), (1, 1), (BLANK, 1), (2, 1)]
    assert model.transcribe(audio_for(frames)) == "hola mundo que"


def test_a_long_duration_skips_the_frames_it_covers(model):
    frames = [(0, 3), (1, 1), (4, 1), (3, 1)]  # "hola" covers three frames; the next visited is frame 3
    assert model.transcribe(audio_for(frames)) == "hola tal"


def test_a_blank_with_no_duration_still_moves_one_frame(model):
    frames = [(BLANK, 0), (0, 1)]
    assert model.transcribe(audio_for(frames)) == "hola"


def test_no_more_than_ten_tokens_come_out_of_one_frame(model):
    state = DecoderState(model)
    encoded = np.zeros((1024, 1), np.float32)  # token 0 with duration 0, forever on frame 0
    text = model.decode(encoded, 0, 1, state)
    assert text == " hola" * 10


def test_a_duration_past_the_end_of_a_block_is_carried_into_the_next_one(model):
    encoded = np.zeros((1024, 2), np.float32)
    encoded[0, 0] = BLANK  # frame 0: blank
    encoded[0, 1] = 0  # frame 1: "hola"
    encoded[1, 1] = 4  # frame 1: skip four frames
    state = DecoderState(model)
    assert model.decode(encoded, 0, 2, state) == " hola"
    assert state.carry == 3  # the jump lands at frame 5, three frames past this block of two
    assert model.decode(encoded, 2, 4, state) == ""  # the next block starts inside the skipped span
    assert state.carry == 1


def test_decoder_state_starts_clean(model):
    state = DecoderState(model)
    assert state.last == BLANK and state.carry == 0 and state.context == 0
    assert state.h.shape == (2, 1, 4) and not state.h.any() and not state.c.any()


def test_trace_records_each_token_with_its_time_and_a_confident_probability(model):
    frames = [(0, 1), (BLANK, 1), (1, 1), (4, 1)]
    stream = Stream(model)
    stream.feed(audio_for(frames))
    stream.finish()
    times = [round(t / 0.08) for _, t, _, _ in stream.trace]
    assert times == [0, 2, 3]  # frames 0, 2 and 3 emitted; frame 1 is blank
    assert [piece for piece, *_ in stream.trace] == [" hola", " mundo", "."]
    assert all(p > 0.99 and margin > 0.99 for _, _, p, margin in stream.trace)


# -- streaming in blocks --------------------------------------------------------------


def test_one_pass_matches_the_reference_on_random_speech(model):
    frames = random_frames(1)
    assert model.transcribe(audio_for(frames)) == reference(frames)


@pytest.mark.parametrize("seed", [2, 3, 4])
def test_blocks_of_any_size_give_the_same_text_as_one_pass(model, seed):
    frames = random_frames(seed, n=120)
    audio = audio_for(frames)
    rng = np.random.default_rng(seed)
    stream = Stream(model)
    pieces, i = [], 0
    while i < audio.size:
        n = int(rng.integers(300, 4000))  # blocks much shorter and longer than the decoder's step
        pieces.append(stream.feed(audio[i : i + n]))
        i += n
    pieces.append(stream.finish())
    assert "".join(pieces).strip() == reference(frames)


def test_text_is_final_only_once_the_look_ahead_has_arrived(model):
    frames = random_frames(9, n=120)
    audio = audio_for(frames)
    stream = Stream(model)
    early = stream.feed(audio[: Stream.CPU_CHUNK + Stream.RIGHT // 2])  # not enough audio for a step
    assert early == "" and stream.done == 0
    stream.feed(audio[Stream.CPU_CHUNK + Stream.RIGHT // 2 :])
    assert stream.done > 0 and isinstance(stream.tail, str)


def test_audio_is_trimmed_to_the_left_context_as_it_goes(model):
    audio = audio_for(random_frames(5, n=300))
    stream = Stream(model)
    stream.feed(audio)
    assert stream.audio.size <= Stream.LEFT + Stream.CPU_CHUNK + Stream.RIGHT
    assert stream.offset > 0


def test_a_full_stop_resets_the_prediction_state_but_keeps_the_duration_carry(model):
    frames = [(0, 1), (1, 1), (4, 1)]  # "hola mundo." ends the utterance
    stream = Stream(model)
    stream.feed(audio_for(frames))
    stream.finish()
    assert stream.state.last == BLANK and not stream.state.h.any()


def test_without_a_full_stop_the_prediction_state_is_kept(model):
    stream = Stream(model)
    stream.feed(audio_for([(0, 1), (1, 1)]))
    stream.finish()
    assert stream.state.last == 1


def test_leading_spaces_are_dropped_from_the_first_words(model):
    stream = Stream(model)
    first = stream.feed(audio_for([(0, 1), (1, 1)] + [(BLANK, 1)] * 20))
    assert not first.startswith(" ")
    rest = stream.finish()
    assert (first + rest).lstrip() == "hola mundo"


def test_very_short_audio_is_not_transcribed(model):
    assert model.transcribe(np.zeros(SAMPLE_RATE // 20, np.float32)) == ""
    assert model.encoder.calls == 0


# -- helpers --------------------------------------------------------------------------


def test_mirror_continues_the_audio_by_reflection():
    x = np.array([1, 2, 3], np.float32)
    assert asr._mirror(x, 5).tolist() == [3, 2, 1, 1, 2]
    assert asr._mirror(x, 0).size == 0
    assert asr._mirror(np.zeros(0, np.float32), 3).tolist() == [0, 0, 0]


def test_softmax_is_a_distribution_in_the_same_order():
    p = asr._softmax(np.array([1.0, 3.0, 2.0]))
    assert p.sum() == pytest.approx(1.0) and p.argmax() == 1 and p[2] > p[0]


# -- the vocabulary and the model folder ----------------------------------------------


def write_model_folder(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("nemo128.onnx", "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx"):
        (folder / name).write_bytes(b"")
    (folder / "vocab.txt").write_text("▁hola 0\n▁mundo 1\n▁que 2\n. 3\n<blk> 4\n", encoding="utf-8")


@pytest.fixture
def sessions(monkeypatch):
    """Every ONNX session is a fake chosen by its file name; nothing is loaded from disk."""
    made = {}

    def factory(path, _opts, providers=None):
        name = Path(path).name
        made[name] = (
            FakePreprocessor()
            if name.startswith("nemo")
            else FakeEncoder()
            if name.startswith("encoder")
            else FakeDecoder()
        )
        return made[name]

    monkeypatch.setattr(asr.ort, "InferenceSession", factory)
    monkeypatch.setattr(asr.ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    return made


def test_vocabulary_and_blank_come_from_the_folder(tmp_path, sessions):
    write_model_folder(tmp_path)
    m = Parakeet(tmp_path, use_gpu=False, custom=True)
    assert m.vocab == {0: " hola", 1: " mundo", 2: " que", 3: ".", 4: "<blk>"}
    assert m.blank == 4 and m.state_shape == (2, 1, 4) and not m.on_gpu
    assert not (tmp_path / "NOTICE.txt").exists()  # a custom model is the user's own: nothing is written


def test_a_custom_model_without_tokenizer_has_no_phrase_boosting(tmp_path, sessions):
    write_model_folder(tmp_path)
    m = Parakeet(tmp_path, use_gpu=False, custom=True)
    m.set_phrases({"hola mundo": 1.0})
    assert m.boost is None


def test_close_frees_the_sessions(tmp_path, sessions):
    write_model_folder(tmp_path)
    m = Parakeet(tmp_path, use_gpu=False, custom=True)
    m.close()
    assert m.closed and m.preprocessor is None and m.encoder is None and m.decoder is None


def test_phrase_boosting_is_built_once_per_set_of_phrases(model, monkeypatch):
    calls = []

    def tokenizer(directory=None, fetch=True):
        calls.append(fetch)
        return lambda phrase: [0, 1] if phrase else []

    monkeypatch.setattr(asr, "phrase_tokenizer", tokenizer)
    model.set_phrases({"hola mundo": 1.0})
    first = model.boost
    assert isinstance(first, BoostingTree)
    model.set_phrases({"hola mundo": 1.0})
    assert model.boost is first  # same phrases: nothing rebuilt
    model.set_phrases({"que tal": 0.5})
    assert model.boost is not first
    model.set_phrases(None)
    assert model.boost is None and model._boost_key is None
    assert len(calls) == 1  # the tokenizer is fetched once, then kept


def test_tokenizer_download_failure_means_no_boosting_and_no_file(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(asr.urllib.request, "urlopen", offline)
    assert asr.phrase_tokenizer(tmp_path, fetch=True) is None
    assert not (tmp_path / "tokenizer.json").exists()


def test_tokenizer_with_the_wrong_checksum_is_refused(tmp_path, monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"not the tokenizer"

    monkeypatch.setattr(asr.urllib.request, "urlopen", lambda url, timeout=30: Reply())
    assert asr.phrase_tokenizer(tmp_path, fetch=True) is None
    assert not (tmp_path / "tokenizer.json").exists()
    assert not (tmp_path / "tokenizer.part").exists()


def test_without_fetching_no_tokenizer_is_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(asr.urllib.request, "urlopen", lambda *a, **k: pytest.fail("no download expected"))
    assert asr.phrase_tokenizer(tmp_path, fetch=False) is None


def test_model_is_not_downloaded_in_an_empty_folder(tmp_path):
    assert asr.is_downloaded(tmp_path) is False


# -- the real model -------------------------------------------------------------------


def test_real_model_transcribes_a_wav_end_to_end(tmp_path):
    """Read-only check with the user's downloaded model; skipped when it is not there."""
    if not asr.is_downloaded():
        pytest.skip("the Parakeet model is not downloaded in this machine")
    path = tmp_path / "tone.wav"
    t = np.arange(SAMPLE_RATE * 2) / SAMPLE_RATE
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    with wave.open(str(path), "rb") as r:
        audio = np.frombuffer(r.readframes(r.getnframes()), "<i2").astype(np.float32) / 32768
    model = Parakeet(asr.model_dir(), use_gpu=False, custom=True)  # custom: reads only, writes nothing
    try:
        text = model.transcribe(audio)
        silence = model.transcribe(np.zeros(SAMPLE_RATE * 2, np.float32))
    finally:
        model.close()
    assert isinstance(text, str) and isinstance(silence, str)


def test_a_failed_tokenizer_fetch_is_not_retried_until_the_wait_passes(model, monkeypatch):
    calls = []
    now = [1000.0]
    monkeypatch.setattr(asr.time, "monotonic", lambda: now[0])

    def tokenizer(directory=None, fetch=True):
        calls.append(fetch)
        return None if len(calls) == 1 else (lambda phrase: [0, 1] if phrase else [])

    monkeypatch.setattr(asr, "phrase_tokenizer", tokenizer)
    model.set_phrases({"hola": 1.0})
    model.set_phrases({"que tal": 1.0})  # different phrases, but the fetch just failed
    assert model.boost is None and len(calls) == 1
    now[0] += asr.TOKENIZER_RETRY_SECONDS + 1
    model.set_phrases({"adios": 1.0})
    assert isinstance(model.boost, BoostingTree) and len(calls) == 2
