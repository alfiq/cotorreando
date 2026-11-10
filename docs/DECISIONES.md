# Decisiones

> Qué se eligió durante el diseño y por qué. El código cuenta *qué* hace; esto cuenta *por qué*,
> para no deshacer sin querer algo que ya se probó.

## Punto de partida

### Reconocimiento

| Tema | Decisión |
|---|---|
| Motor de inferencia | **ONNX Runtime** para usar la app; NeMo solo para entrenar LoRA. |
| Origen del modelo | El ONNX de istupakov; si falla, exportar el original de NVIDIA. |
| Detección de voz (VAD) | **Silero VAD** en ONNX. |
| Ruido y eco | **WebRTC APM**. |
| Palabra clave | Detectada con el propio Parakeet: openWakeWord trae modelos no comerciales. |
| Calibración | Obligatoria salvo omisión explícita: 12 paneles por idioma, y solo se activa si mejora el WER. |

### Aplicación

| Tema | Decisión |
|---|---|
| Plataforma | Solo **Windows**. |
| Interfaz | **PySide6** (Qt, LGPL), en español e inglés. |
| Escritura del texto | Teclear con `SendInput` (Unicode), sin tocar el portapapeles. |
| Activación | Por voz o por palabra clave, configurable. |
| Palabra clave por defecto | «oye cotorro». |
| Atajo | `Ctrl+Win`. |
| Logo | La cotorra dibujada a mano, azulejada y sin fondo; también es el icono de la aplicación. |

### Proyecto

| Tema | Decisión |
|---|---|
| Licencia | **MIT**. |
| Repositorio | [`github.com/alfiq/cotorreando`](https://github.com/alfiq/cotorreando), privado al principio. |
| Distribución | Ejecutable con **Nuitka** (Apache-2.0, salida sin restricciones) y opción de iniciar con Windows. |
| Reportes de seguridad y de conducta | Por el canal privado de GitHub, sin correo público en el repositorio: un solo canal que no hay que mantener ni que se filtre. Ver [SECURITY.md](../SECURITY.md) y [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md). |

## Cambios sobre la marcha

Lo que se decidió distinto al chocar con la realidad.

#### SoundCard → PyAudioWPatch
SoundCard falló con la webcam Logitech C270, que exige `WAVE_FORMAT_EXTENSIBLE`.
PyAudioWPatch (Apache-2.0) cubre micrófono y loopback con una sola dependencia.
`sounddevice` también se descartó: su PortAudio no expone el loopback de WASAPI.

#### Streaming real
Primero se simuló re-transcribiendo la frase cada 0,8 s y corrigiendo con retroceso: borraba
demasiado y se atascaba en frases largas. Ahora es streaming por bloques con el estado del
decodificador: nunca reescribe y no tiene límite de duración.

#### ONNX Runtime → onnxruntime-directml
Incluye CPU y usa cualquier GPU vía DirectML. Con ventana de tamaño fijo, cada paso de
streaming baja de **~250 ms** (CPU) a **~55 ms** (GPU).

#### Sin CUDA en la app
CUDA y cuDNN tienen licencia propietaria de NVIDIA, así que no se distribuyen. El entorno
de entrenamiento opcional sí los descarga con PyTorch si hay una GPU NVIDIA.

#### Sin modelo fp32
Pesa 2,4 GB y no es más rápido que el int8 con forma fija.

#### Pérdida TDT propia
La de NeMo exige numba CUDA (`nvvm.dll`), que pip no instala en Windows.

#### LoRA injertado, no fusionado
Fusionar el adaptador y recuantizar a int8 lo borraba, y entrenar sobre el fp32 de NeMo
empeoraba la app. Ahora se entrena sobre los pesos int8 de la app y se injerta como rama
fp32; por defecto, atención + FFN con rango 4. Detalles en [LORA.md](LORA.md).

#### Una sola paleta, sacada de la cotorra
La interfaz, el blob, el instalador, el icono y el README usan los colores de la cotorra, todos
definidos en `cotorreando/palette.py`; nadie más escribe un hex. El icono deja de ser la esfera azul
y pasa a ser la cotorra. Las reglas están en [IDENTIDAD.md](IDENTIDAD.md).

#### Tamaño del blob
Configurable: pequeño, mediano o grande.

#### Descarga directa en el sitio
La portada del sitio abre con un botón que baja el instalador más reciente. Apunta a
`releases/latest/download/Cotorreando-setup.exe`, y al publicar cada Release un workflow le sube una
copia del instalador con ese nombre fijo. No usa la API de GitHub ni JavaScript.

#### Globito de la cotorra
Al pasar el mouse sobre la cotorra sale un globito con una frase distinta cada vez («¿Tienes algo
que decir?», «Cuenta el chisme.», «A ver, cuéntamelo todo.») y el atajo al final. Los botones y
menús se quedan sobrios; el juego va solo en los globitos.

## Pendientes

- [ ] Hacer público el repositorio.
- [ ] Confirmar con más grabaciones reales que el LoRA mejora. En el barrido mejoró en 2 de 6
      grupos y no empeoró en ninguno, pero con pocas grabaciones.
