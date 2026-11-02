"""Microphone capture with WebRTC noise suppression, echo cancellation and AGC.

Audio is read in 10 ms frames at 16 kHz, which is what the WebRTC audio
processing module expects. For echo cancellation the system output is
captured through WASAPI loopback (PyAudioWPatch) and fed as the "reverse"
(far-end) stream. Devices are opened at their native format and resampled.
"""

from __future__ import annotations

import collections
import logging
import threading

import numpy as np
import pyaudiowpatch as pyaudio

try:
    from livekit import rtc
except ImportError:  # processing is optional; capture still works without it
    rtc = None

log = logging.getLogger(__name__)

RATE = 16000
FRAME = RATE // 100  # 10 ms


def _wasapi_devices(pa) -> list[dict]:
    api = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    return list(pa.get_device_info_generator_by_host_api(host_api_index=api))


def list_microphones() -> list[str]:
    pa = pyaudio.PyAudio()
    try:
        return [d["name"] for d in _wasapi_devices(pa)
                if d["maxInputChannels"] and not d.get("isLoopbackDevice")]
    finally:
        pa.terminate()


class Resampler:
    """Streaming mono downmix + windowed-sinc low-pass + resampling to 16 kHz."""

    TAPS = 64

    def __init__(self, rate: int, channels: int):
        self.channels, self.step = channels, rate / RATE
        cutoff = 0.45 / self.step  # just under the new Nyquist, relative to the source rate
        n = np.arange(self.TAPS) - (self.TAPS - 1) / 2
        taps = np.sinc(2 * cutoff * n) * np.hamming(self.TAPS)
        self.taps = (taps / taps.sum()).astype(np.float32)
        self.history = np.zeros(self.TAPS - 1, np.float32)
        self.phase = 0.0

    def __call__(self, data: bytes) -> np.ndarray:
        x = np.frombuffer(data, np.float32).reshape(-1, self.channels).mean(axis=1)
        if self.step == 1:
            return x
        x = np.concatenate([self.history, x])
        self.history = x[-(self.TAPS - 1):]
        y = np.convolve(x, self.taps, mode="valid")
        positions = np.arange(self.phase, len(y) - 1, self.step)
        self.phase = positions[-1] + self.step - len(y) if len(positions) else self.phase - len(y)
        return np.interp(positions, np.arange(len(y)), y).astype(np.float32)


class _Stream:
    """A WASAPI input stream at the device's native format, converted to 16 kHz mono."""

    def __init__(self, pa, device: dict):
        rate, channels = int(device["defaultSampleRate"]), int(device["maxInputChannels"])
        self.resample = Resampler(rate, channels)
        self.block = rate // 100
        self.stream = pa.open(format=pyaudio.paFloat32, channels=channels, rate=rate, input=True,
                              input_device_index=device["index"], frames_per_buffer=self.block)
        self.buffer = np.zeros(0, np.float32)

    def frames(self):
        """Yield successive 10 ms frames at 16 kHz."""
        while True:
            data = self.stream.read(self.block, exception_on_overflow=False)
            self.buffer = np.concatenate([self.buffer, self.resample(data)])
            while self.buffer.size >= FRAME:
                frame, self.buffer = self.buffer[:FRAME], self.buffer[FRAME:]
                yield frame

    def close(self):
        self.stream.stop_stream()
        self.stream.close()


class AudioInput:
    """Delivers processed float32 frames to ``on_frame`` from a worker thread."""

    def __init__(self, on_frame, microphone: str = "", noise_suppression=True,
                 echo_cancellation=True, auto_gain=True):
        self.on_frame = on_frame
        self.microphone = microphone
        self.use_aec = echo_cancellation and rtc is not None
        self.apm = None
        if rtc is not None and (noise_suppression or echo_cancellation or auto_gain):
            try:
                self.apm = rtc.AudioProcessingModule(
                    echo_cancellation=echo_cancellation, noise_suppression=noise_suppression,
                    high_pass_filter=True, auto_gain_control=auto_gain)
            except Exception:
                log.exception("Audio processing unavailable; capturing raw audio")
                self.use_aec = False
        self._far_end: collections.deque[np.ndarray] = collections.deque(maxlen=50)
        self._running = False
        self._threads: list[threading.Thread] = []
        self._pa = pyaudio.PyAudio()

    def start(self) -> None:
        self._running = True
        self._threads = [threading.Thread(target=self._capture, daemon=True, name="mic")]
        if self.use_aec:
            self._threads.append(threading.Thread(target=self._loopback, daemon=True, name="loopback"))
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=1)
        # A silent loopback stream can block in read(); only tear PortAudio down when idle.
        if not any(t.is_alive() for t in self._threads):
            self._pa.terminate()

    def _mic(self) -> dict:
        devices = _wasapi_devices(self._pa)
        for d in devices:
            if self.microphone and d["name"] == self.microphone and d["maxInputChannels"]:
                return d
        default = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)["defaultInputDevice"]
        return self._pa.get_device_info_by_index(default)

    def _run(self, device: dict, sink) -> None:
        stream = _Stream(self._pa, device)
        try:
            for frame in stream.frames():
                if not self._running:
                    break
                sink(frame)
        finally:
            stream.close()

    def _capture(self) -> None:
        try:
            self._run(self._mic(), lambda f: self.on_frame(self._process(f)))
        except Exception:
            log.exception("Microphone capture stopped")

    def _loopback(self) -> None:
        try:
            self._run(self._pa.get_default_wasapi_loopback(), self._far_end.append)
        except Exception:
            log.warning("Loopback unavailable; echo cancellation disabled", exc_info=True)

    def _process(self, frame: np.ndarray) -> np.ndarray:
        if self.apm is None:
            return frame
        if self._far_end:
            self.apm.process_reverse_stream(_to_frame(self._far_end.popleft()))
        near = _to_frame(frame)
        self.apm.process_stream(near)
        return np.frombuffer(near.data, np.int16).astype(np.float32) / 32768.0


class Player:
    """Plays one recording at a time on the default output, without blocking the interface."""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None

    def play(self, samples: np.ndarray, on_end) -> None:
        self.stop()
        self._running = True
        pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
        self._thread = threading.Thread(target=self._run, args=(pcm, on_end), daemon=True, name="playback")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def _run(self, pcm: bytes, on_end) -> None:
        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, output=True)
            try:
                for start in range(0, len(pcm), FRAME * 10):
                    if not self._running:
                        break
                    stream.write(pcm[start:start + FRAME * 10])
            finally:
                stream.close()
        except Exception:
            log.exception("Could not play the recording")
        finally:
            pa.terminate()
            on_end()


def _to_frame(x: np.ndarray):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    return rtc.AudioFrame(pcm.tobytes(), RATE, 1, FRAME)
