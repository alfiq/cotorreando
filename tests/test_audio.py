"""Capture, resampling and playback, without a sound device: PyAudio and the streams are fakes."""

import threading

import numpy as np
import pytest

from cotorreando import audio
from cotorreando.audio import FRAME, RATE, AudioInput, Player, Resampler


def sine(freq, rate, seconds=1.0, amplitude=1.0):
    t = np.arange(int(rate * seconds)) / rate
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def run_in_blocks(resampler, x, block):
    return np.concatenate([resampler(x[i : i + block].tobytes()) for i in range(0, len(x), block)])


# -- Resampler ------------------------------------------------------------------------


def test_16khz_mono_passes_through_unchanged():
    x = sine(440, RATE, 0.1)
    np.testing.assert_array_equal(Resampler(RATE, 1)(x.tobytes()), x)


def test_stereo_is_downmixed_to_the_channel_mean():
    stereo = np.stack([np.full(160, 0.2), np.full(160, -0.6)], axis=1).astype(np.float32).reshape(-1)
    out = Resampler(RATE, 2)(stereo.tobytes())
    np.testing.assert_allclose(out, np.full(160, -0.2), atol=1e-6)


@pytest.mark.parametrize("rate", [48000, 44100, 32000])
def test_one_second_becomes_sixteen_thousand_samples(rate):
    out = Resampler(rate, 1)(sine(440, rate).tobytes())
    assert abs(len(out) - RATE) <= 1


@pytest.mark.parametrize("rate", [48000, 44100])
def test_resampled_tone_keeps_its_pitch(rate):
    out = Resampler(rate, 1)(sine(440, rate).tobytes())[500:-500]
    peak = np.argmax(np.abs(np.fft.rfft(out))) * RATE / len(out)
    assert abs(peak - 440) < 3


def test_frequencies_above_the_new_nyquist_are_removed():
    # 10 kHz is above the 8 kHz that 16 kHz can carry; it must not fold back into the band
    out = Resampler(48000, 1)(sine(10000, 48000).tobytes())[200:-200]
    assert np.sqrt(np.mean(out * out)) < 0.01


@pytest.mark.parametrize("rate", [48000, 44100])
def test_ten_millisecond_blocks_give_the_same_samples_as_one_pass(rate):
    # the capture thread reads 10 ms at a time; streaming must not change the audio
    x = sine(440, rate, 1.0, 0.8)
    whole = Resampler(rate, 1)(x.tobytes())
    chunked = run_in_blocks(Resampler(rate, 1), x, rate // 100)
    assert len(chunked) == len(whole)
    np.testing.assert_allclose(chunked, whole, atol=1e-6)


def test_ten_millisecond_blocks_at_22050_match_one_pass():
    x = sine(440, 22050, 1.0, 0.8)
    whole = Resampler(22050, 1)(x.tobytes())
    chunked = run_in_blocks(Resampler(22050, 1), x, 220)
    np.testing.assert_allclose(chunked, whole, atol=1e-6)


def test_odd_sized_blocks_lose_no_samples():
    r = Resampler(48000, 1)
    sizes = [137, 480, 13, 1000, 480]
    total = sum(len(r(np.zeros(n, np.float32).tobytes())) for n in sizes)
    assert abs(total - sum(sizes) / 3) <= 1


# -- frames and devices ---------------------------------------------------------------


def test_to_frame_is_ten_milliseconds_of_clipped_int16():
    x = np.array([0.0, 0.5, -0.5, 2.0, -2.0] + [0.0] * (FRAME - 5), np.float32)
    frame = audio._to_frame(x)
    assert frame.samples_per_channel == FRAME and frame.sample_rate == RATE
    pcm = np.frombuffer(bytes(frame.data), np.int16)
    assert pcm[:5].tolist() == [0, 16383, -16383, 32767, -32767]


class FakeStream:
    """A PyAudio stream that accepts everything and records how it was opened."""

    def __init__(self):
        self.opened_with = None
        self.closed = False

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class FakePyAudio:
    """Devices are dictionaries shaped like the ones PyAudioWPatch returns."""

    devices = [
        {"index": 0, "name": "Mic A", "maxInputChannels": 1, "defaultSampleRate": 16000, "isLoopbackDevice": False},
        {"index": 1, "name": "Speakers", "maxInputChannels": 0, "defaultSampleRate": 48000, "isLoopbackDevice": False},
        {"index": 2, "name": "Mic B", "maxInputChannels": 2, "defaultSampleRate": 48000, "isLoopbackDevice": False},
        {"index": 3, "name": "Loop", "maxInputChannels": 2, "defaultSampleRate": 48000, "isLoopbackDevice": True},
    ]
    default_input = 2
    next_stream = None  # a test may set it to receive the playback stream
    instances: list = []

    def __init__(self):
        self.terminated = False
        FakePyAudio.instances.append(self)

    def get_host_api_info_by_type(self, _kind):
        return {"index": 0, "defaultInputDevice": self.default_input}

    def get_device_info_by_index(self, index):
        return next(d for d in self.devices if d["index"] == index)

    def open(self, **kwargs):
        stream = self.next_stream or FakeStream()
        stream.opened_with = kwargs
        return stream

    def terminate(self):
        self.terminated = True


@pytest.fixture
def fake_pa(monkeypatch):
    FakePyAudio.instances = []
    FakePyAudio.next_stream = None
    monkeypatch.setattr(audio.pyaudio, "PyAudio", FakePyAudio)
    monkeypatch.setattr(audio, "_wasapi_devices", lambda pa: list(FakePyAudio.devices))
    return FakePyAudio


def plain_input(on_frame=lambda f: None):
    return AudioInput(on_frame, noise_suppression=False, echo_cancellation=False, auto_gain=False)


def test_list_microphones_keeps_inputs_and_drops_loopbacks(fake_pa):
    assert audio.list_microphones() == ["Mic A", "Mic B"]
    assert fake_pa.instances[0].terminated


def test_named_microphone_is_chosen(fake_pa):
    inp = plain_input()
    inp.microphone = "Mic A"
    assert inp._mic()["index"] == 0
    inp._pa.terminate()


def test_unknown_microphone_falls_back_to_the_default_input(fake_pa):
    inp = plain_input()
    inp.microphone = "Unplugged"
    assert inp._mic()["index"] == 2
    inp._pa.terminate()


def test_output_only_device_is_never_used_as_microphone(fake_pa):
    inp = plain_input()
    inp.microphone = "Speakers"
    assert inp._mic()["index"] == 2
    inp._pa.terminate()


# -- capture --------------------------------------------------------------------------


class FakeCapture:
    """Stands in for _Stream: yields the given frames, then fails with ``error`` if one is set."""

    def __init__(self, frames=(), error=None):
        self._frames, self._error = list(frames), error
        self.closed = False

    def frames(self):
        yield from self._frames
        if self._error:
            raise self._error

    def close(self):
        self.closed = True


@pytest.fixture
def capture(monkeypatch, fake_pa):
    def use(frames=(), error=None):
        stream = FakeCapture(frames, error)
        monkeypatch.setattr(audio, "_Stream", lambda pa, device: stream)
        return stream

    return use


def test_capture_delivers_frames_in_order_and_closes_the_stream(capture):
    stream = capture([np.full(FRAME, v, np.float32) for v in (0.1, 0.2, 0.3)])
    inp = plain_input()
    inp._running = True
    got = []
    inp._run(inp._mic(), lambda f: got.append(float(f[0])))
    assert [round(v, 1) for v in got] == [0.1, 0.2, 0.3]
    assert stream.closed
    inp._pa.terminate()


def test_capture_stops_once_switched_off(capture):
    capture([np.zeros(FRAME, np.float32)] * 5)
    inp = plain_input()
    inp._running = True
    seen = []

    def sink(frame):
        seen.append(frame)
        inp._running = len(seen) < 2  # stop requested after the second frame

    inp._run(inp._mic(), sink)
    assert len(seen) == 2
    inp._pa.terminate()


def test_capture_error_is_logged_and_the_stream_still_closed(capture, caplog):
    stream = capture(error=OSError("device unplugged"))
    inp = plain_input()
    inp._running = True
    inp._capture()  # must not raise
    assert stream.closed
    assert "Microphone capture stopped" in caplog.text
    inp._pa.terminate()


def test_without_an_apm_frames_pass_through_untouched(fake_pa):
    inp = plain_input()
    frame = sine(300, RATE, 0.01, 0.5)
    assert inp._process(frame) is frame
    inp._pa.terminate()


class FakeApm:
    def __init__(self):
        self.reverse, self.near = [], 0

    def process_reverse_stream(self, frame):
        self.reverse.append(frame)

    def process_stream(self, frame):
        self.near += 1


def test_one_far_end_frame_is_fed_to_echo_cancellation_per_near_frame(fake_pa):
    inp = plain_input()
    inp.apm = FakeApm()
    inp._far_end.extend([np.zeros(FRAME, np.float32), np.ones(FRAME, np.float32)])
    out = inp._process(np.full(FRAME, 0.25, np.float32))
    assert len(inp.apm.reverse) == 1 and len(inp._far_end) == 1
    assert inp.apm.near == 1
    np.testing.assert_allclose(out, 0.25, atol=1 / 32768)  # int16 quantisation only
    inp._pa.terminate()


def test_start_and_stop_release_portaudio_when_the_thread_is_done(capture):
    capture([])
    inp = plain_input()
    inp.start()
    assert [t.name for t in inp._threads] == ["mic"]  # no loopback without echo cancellation
    inp.stop()
    assert not any(t.is_alive() for t in inp._threads)
    assert inp._pa.terminated


def test_stop_keeps_portaudio_while_a_thread_is_stuck(fake_pa):
    inp = plain_input()
    blocker = threading.Event()
    stuck = threading.Thread(target=blocker.wait, daemon=True)
    stuck.start()
    inp._threads = [stuck]
    inp.stop()  # gives up joining after a second, like a loopback stuck in read()
    assert not inp._pa.terminated
    blocker.set()


# -- playback -------------------------------------------------------------------------


class FakePlayback(FakeStream):
    """Records what is written; the first write can be held on a gate to interrupt playback."""

    def __init__(self, gate=None):
        super().__init__()
        self.writes = []
        self.gate = gate

    def write(self, data):
        self.writes.append(data)
        if self.gate is not None and len(self.writes) == 1:
            self.gate.wait(2)


def test_playback_writes_clipped_int16_and_reports_the_end(fake_pa):
    stream = FakePlayback()
    fake_pa.next_stream = stream
    done = threading.Event()
    player = Player()
    player.play(np.array([0.0, 1.5, -1.5, 0.5], np.float32), done.set)
    player._thread.join(2)
    assert done.is_set()
    pcm = np.frombuffer(b"".join(stream.writes), np.int16)
    assert pcm.tolist() == [0, 32767, -32767, 16383]
    assert stream.opened_with["rate"] == RATE and stream.opened_with["channels"] == 1
    assert stream.closed


def test_stop_ends_playback_early_and_still_reports_the_end(fake_pa):
    gate = threading.Event()
    stream = FakePlayback(gate)
    fake_pa.next_stream = stream
    done = threading.Event()
    player = Player()
    player.play(np.zeros(RATE * 2, np.float32), done.set)  # two seconds: many blocks
    while not stream.writes:
        threading.Event().wait(0.01)
    player.stop()  # gives up joining after a second; the held write is released below
    gate.set()
    assert done.wait(2)
    assert len(stream.writes) == 1
