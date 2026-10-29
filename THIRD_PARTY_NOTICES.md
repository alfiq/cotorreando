# Avisos de terceros / Third-party notices

Cotorreando se distribuye bajo la licencia MIT (ver `LICENSE`). Incluye o descarga
los siguientes componentes, todos con licencias permisivas que permiten uso comercial.
La misma lista aparece en la ventana **Acerca de** de la aplicación (`cotorreando/credits.py`).

Cotorreando is MIT-licensed. It bundles or downloads the components below, all
under permissive, commercially usable licenses.

| Componente | Uso | Licencia | Atribución |
|---|---|---|---|
| [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | Speech recognition model | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | © NVIDIA Corporation. Used as converted to ONNX (int8) by Ilya Stupakov; optionally fine-tuned locally with a LoRA adapter. |
| [parakeet-tdt-0.6b-v3-onnx](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) | ONNX export of the model | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | © Ilya Stupakov |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Voice activity detection | [MIT](https://github.com/snakers4/silero-vad/blob/master/LICENSE) | © Silero Team |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | Neural network inference | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) | © Microsoft Corporation |
| [WebRTC Audio Processing](https://webrtc.googlesource.com/src) | Noise suppression, echo cancellation, AGC | [BSD-3-Clause](https://webrtc.googlesource.com/src/+/main/LICENSE) | © The WebRTC project authors |
| [LiveKit Python SDK](https://github.com/livekit/python-sdks) | Python bindings to WebRTC audio processing | [Apache-2.0](https://github.com/livekit/python-sdks/blob/main/LICENSE) | © LiveKit, Inc. |
| [Qt / PySide6](https://www.qt.io/qt-for-python) | User interface | [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) | © The Qt Company Ltd. Linked dynamically; you may replace the Qt libraries. |
| [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | Microphone and WASAPI loopback capture | [Apache-2.0](https://github.com/s0d3s/PyAudioWPatch/blob/master/LICENSE.txt) | © s0d3s; based on PyAudio by Hubert Pham |
| [PortAudio](https://www.portaudio.com) | Audio I/O library bundled with PyAudioWPatch | [MIT](https://www.portaudio.com/license.html) | © Ross Bencina, Phil Burk |
| [NumPy](https://numpy.org) | Numerical arrays | [BSD-3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt) | © NumPy Developers |
| [Protocol Buffers](https://github.com/protocolbuffers/protobuf) | Dependency of the LiveKit SDK | [BSD-3-Clause](https://github.com/protocolbuffers/protobuf/blob/main/LICENSE) | © Google Inc. |
| [FlatBuffers](https://github.com/google/flatbuffers) | Dependency of ONNX Runtime | [Apache-2.0](https://github.com/google/flatbuffers/blob/master/LICENSE) | © Google Inc. |
| [aiofiles](https://github.com/Tinche/aiofiles) | Dependency of the LiveKit SDK | [Apache-2.0](https://github.com/Tinche/aiofiles/blob/main/LICENSE) | © Tin Tvrtković |
| [Python](https://www.python.org) | Runtime | [PSF-2.0](https://docs.python.org/3/license.html) | © Python Software Foundation |
| [Nuitka](https://nuitka.net) | Executable build | [Apache-2.0](https://github.com/Nuitka/Nuitka/blob/develop/LICENSE.txt) | © Kay Hayen |
| [Handy](https://github.com/cjpais/handy) | Inspiration for the overall idea | [MIT](https://github.com/cjpais/handy/blob/main/LICENSE) | © CJ Pais. No code was copied. |

## Solo para entrenar (se instalan bajo demanda)

| Componente | Uso | Licencia | Atribución |
|---|---|---|---|
| [NVIDIA NeMo](https://github.com/NVIDIA/NeMo) | Fine-tuning and ONNX export | [Apache-2.0](https://github.com/NVIDIA/NeMo/blob/main/LICENSE) | © NVIDIA Corporation |
| [PyTorch](https://pytorch.org) | Training backend | [BSD-3-Clause](https://github.com/pytorch/pytorch/blob/main/LICENSE) | © Meta Platforms, Inc. and contributors |
| [uv](https://github.com/astral-sh/uv) | Creates the training environment | [MIT / Apache-2.0](https://github.com/astral-sh/uv/blob/main/LICENSE-MIT) | © Astral Software Inc. |

## Notas

- **Parakeet TDT 0.6B v3 (CC BY 4.0).** Modelo de NVIDIA. Se usa la conversión a ONNX
  cuantizada a int8 de Ilya Stupakov. Si el usuario entrena un adaptador LoRA, se genera
  localmente un modelo derivado que conserva la misma licencia y atribución.
  *Parakeet TDT 0.6B v3 by NVIDIA, licensed under CC BY 4.0. Modified: converted to ONNX
  and quantized to int8; optionally fine-tuned with LoRA.*
- **Qt / PySide6 (LGPL-3.0).** Se enlaza dinámicamente. El ejecutable se construye en modo
  *standalone* (no *onefile*), así que las DLL de Qt quedan como archivos separados que el
  usuario puede reemplazar, como exige la LGPL. Código fuente de Qt:
  https://download.qt.io/official_releases/qt/ y de PySide6: https://code.qt.io/cgit/pyside/pyside-setup.git/
- **Handy (MIT).** Sirvió de inspiración para la idea general. No se copió código.
