"""Third-party components, their licenses and the attribution they ask for.

This list feeds the About dialog; THIRD_PARTY_NOTICES.md mirrors it.
"""

# (name, purpose, license, project url, license url, attribution note)
CREDITS = [
    ("Parakeet TDT 0.6B v3", "Speech recognition model", "CC BY 4.0",
     "https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3",
     "https://creativecommons.org/licenses/by/4.0/",
     "© NVIDIA Corporation. Used as converted to ONNX (int8) by Ilya Stupakov; "
     "optionally fine-tuned locally with a LoRA adapter."),
    ("parakeet-tdt-0.6b-v3-onnx", "ONNX export of the model", "CC BY 4.0",
     "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx",
     "https://creativecommons.org/licenses/by/4.0/", "© Ilya Stupakov"),
    ("Silero VAD", "Voice activity detection", "MIT",
     "https://github.com/snakers4/silero-vad",
     "https://github.com/snakers4/silero-vad/blob/master/LICENSE", "© Silero Team"),
    ("ONNX Runtime", "Neural network inference", "MIT",
     "https://github.com/microsoft/onnxruntime",
     "https://github.com/microsoft/onnxruntime/blob/main/LICENSE", "© Microsoft Corporation"),
    ("WebRTC Audio Processing", "Noise suppression, echo cancellation, AGC", "BSD-3-Clause",
     "https://webrtc.googlesource.com/src",
     "https://webrtc.googlesource.com/src/+/main/LICENSE", "© The WebRTC project authors"),
    ("LiveKit Python SDK", "Python bindings to WebRTC audio processing", "Apache-2.0",
     "https://github.com/livekit/python-sdks",
     "https://github.com/livekit/python-sdks/blob/main/LICENSE", "© LiveKit, Inc."),
    ("Qt / PySide6", "User interface", "LGPL-3.0",
     "https://www.qt.io/qt-for-python", "https://www.gnu.org/licenses/lgpl-3.0.html",
     "© The Qt Company Ltd. Linked dynamically; you may replace the Qt libraries."),
    ("PyAudioWPatch", "Microphone and WASAPI loopback capture", "Apache-2.0",
     "https://github.com/s0d3s/PyAudioWPatch",
     "https://github.com/s0d3s/PyAudioWPatch/blob/master/LICENSE.txt", "© s0d3s; based on PyAudio by Hubert Pham"),
    ("PortAudio", "Audio I/O library bundled with PyAudioWPatch", "MIT",
     "https://www.portaudio.com", "https://www.portaudio.com/license.html",
     "© Ross Bencina, Phil Burk"),
    ("NumPy", "Numerical arrays", "BSD-3-Clause", "https://numpy.org",
     "https://github.com/numpy/numpy/blob/main/LICENSE.txt", "© NumPy Developers"),
    ("Protocol Buffers", "Dependency of the LiveKit SDK", "BSD-3-Clause",
     "https://github.com/protocolbuffers/protobuf",
     "https://github.com/protocolbuffers/protobuf/blob/main/LICENSE", "© Google Inc."),
    ("FlatBuffers", "Dependency of ONNX Runtime", "Apache-2.0",
     "https://github.com/google/flatbuffers",
     "https://github.com/google/flatbuffers/blob/master/LICENSE", "© Google Inc."),
    ("aiofiles", "Dependency of the LiveKit SDK", "Apache-2.0",
     "https://github.com/Tinche/aiofiles", "https://github.com/Tinche/aiofiles/blob/main/LICENSE",
     "© Tin Tvrtković"),
    ("Python", "Runtime", "PSF-2.0", "https://www.python.org",
     "https://docs.python.org/3/license.html", "© Python Software Foundation"),
    ("Nuitka", "Executable build", "Apache-2.0", "https://nuitka.net",
     "https://github.com/Nuitka/Nuitka/blob/develop/LICENSE.txt", "© Kay Hayen"),
    ("Handy", "Inspiration for the overall idea", "MIT", "https://github.com/cjpais/handy",
     "https://github.com/cjpais/handy/blob/main/LICENSE", "© CJ Pais. No code was copied."),
]

# Installed only when the user chooses to train a voice adapter.
TRAINING_CREDITS = [
    ("NVIDIA NeMo", "Fine-tuning and ONNX export", "Apache-2.0",
     "https://github.com/NVIDIA/NeMo", "https://github.com/NVIDIA/NeMo/blob/main/LICENSE",
     "© NVIDIA Corporation"),
    ("PyTorch", "Training backend", "BSD-3-Clause", "https://pytorch.org",
     "https://github.com/pytorch/pytorch/blob/main/LICENSE", "© Meta Platforms, Inc. and contributors"),
    ("uv", "Creates the training environment", "MIT / Apache-2.0",
     "https://github.com/astral-sh/uv", "https://github.com/astral-sh/uv/blob/main/LICENSE-MIT",
     "© Astral Software Inc."),
]
