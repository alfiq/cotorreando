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
| Calibración | Obligatoria salvo omisión explícita: 12 paneles por idioma; solo se activa si mejora el WER. |
| Logo | La cotorra dibujada a mano, azulejada, sin fondo; el icono actual sigue como mascota. |
| Idioma de la interfaz | Español e inglés. |
| Distribución | Ejecutable con Nuitka (Apache-2.0, salida sin restricciones) y opción de iniciar con Windows. |

## Cambios sobre la marcha

- **SoundCard → PyAudioWPatch.** SoundCard falló con la webcam Logitech C270
  (exige formato `WAVE_FORMAT_EXTENSIBLE`). PyAudioWPatch (Apache-2.0) cubre micrófono
  y loopback con una sola dependencia.
- **Streaming.** Primero se simuló re-transcribiendo la frase cada 0,8 s y corrigiendo con
  retroceso; borraba demasiado y se atascaba en frases largas. Se cambió por streaming real
  por bloques con estado del decodificador: nunca reescribe y no tiene límite de duración.
- **ONNX Runtime → onnxruntime-directml.** Incluye CPU y usa cualquier GPU vía DirectML.
  Con ventana de tamaño fijo, el paso de streaming baja de ~250 ms (CPU) a ~55 ms (GPU).
- **Sin CUDA.** Las librerías de CUDA/cuDNN tienen licencia propietaria de NVIDIA, no permisiva.
- **Sin modelo fp32.** Pesa 2,4 GB y no aporta velocidad frente al int8 con forma fija.
- **Tamaño del blob** configurable: pequeño, mediano o grande.
- **sounddevice descartado.** Su PortAudio no expone dispositivos de loopback WASAPI.

- **Pérdida TDT propia.** La de NeMo exige numba CUDA (`nvvm.dll`), que pip no instala en Windows.

## Pendientes de confirmar

- Crear el repositorio privado en GitHub y subir el código (falta tu visto bueno).
- Medir la mejora del LoRA con voces y micrófonos reales: con voz sintética no hubo ganancia.
