# Preguntas y decisiones

Registro de lo que se preguntó durante el diseño y lo que se eligió.

| Pregunta | Decisión |
|---|---|
| Motor de inferencia | ONNX Runtime para usar; NeMo solo para entrenar LoRA y re-exportar. |
| Interfaz | PySide6 (Qt, LGPL). |
| Plataformas | Solo Windows. |
| Cómo escribir el texto | Teclear con `SendInput` (Unicode), sin tocar el portapapeles. |
| Ruido y eco | WebRTC APM. |
| VAD | Silero VAD ONNX. |
| Activación | Por voz o por palabra clave, configurable. |
| Detección de palabra clave | Con el propio Parakeet (openWakeWord trae modelos no comerciales). |
| Palabra clave por defecto | «oye cotorro». |
| Atajo | `Ctrl+Win`. |
| Repositorio | `github.com/alfiq/cotorreando`, privado al principio. |
| Licencia | MIT. |
| Origen del modelo | ONNX de istupakov; si falla, exportar el original de NVIDIA. |
| Tamaño del conjunto de frases | Tres: 30, 60 y 150 frases; el usuario elige. |
| Idioma de la interfaz | Español e inglés. |
| Distribución | Ejecutable con Nuitka (Apache-2.0, salida sin restricciones) y opción de iniciar con Windows. |

## Cambios sobre la marcha

- **SoundCard → PyAudioWPatch.** SoundCard falló con la webcam Logitech C270
  (exige formato `WAVE_FORMAT_EXTENSIBLE`). PyAudioWPatch (Apache-2.0) cubre micrófono
  y loopback con una sola dependencia.
- **sounddevice descartado.** Su PortAudio no expone dispositivos de loopback WASAPI.

## Pendientes de confirmar

- Crear el repositorio privado en GitHub y subir el código (falta tu visto bueno).
- Probar el entrenamiento LoRA de punta a punta: requiere instalar ~6 GB.
