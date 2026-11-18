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
| Reportes de seguridad y de conducta | Por el canal privado de GitHub, sin correo público en el repositorio: un solo canal que no hay que mantener ni que se filtre. Ver [SECURITY.md](https://github.com/alfiq/cotorreando/blob/main/SECURITY.md) y [CODE_OF_CONDUCT.md](https://github.com/alfiq/cotorreando/blob/main/CODE_OF_CONDUCT.md). |
| Linter | **ruff** con las reglas E, F, I, B y UP, en CI antes de las pruebas. Se ignoran E501 (textos de interfaz, CSS y licencias largos a propósito), B905 (`strict=` en `zip` cambiaría el comportamiento) y UP031 (la hoja de estilos de Qt es una plantilla `%(NOMBRE)s`). También `ruff format` (líneas de 120), comprobado en CI; el commit de formato está en `.git-blame-ignore-revs` para que `git blame` lo salte; también **pyright** en modo `basic` como aviso (`continue-on-error` en CI, solo con Python 3.12), limitado a `vault`, `config`, `model_store`, `learning`, `boosting` y `transfer` (lista en `[tool.pyright]`); hoy reporta 13 errores sin corregir, casi todos por stubs ausentes de `pyrage` y estrechamiento de `None`, y no bloquea nada. |
| Firma del instalador | **Sin firma** por ahora. Se quitó la autofirmada (`CN=Alfiq`): Windows no confía en ella, SmartScreen avisaba igual que sin firma, ataba las compilaciones al certificado de una sola PC y puede estorbar la validación de winget. La forma de comprobar el instalador es `SHA256SUMS.txt`. Una firma reconocida (Authenticode de una autoridad o un servicio de firma para software libre) sigue pendiente. |
| Release en CI | La compila, prueba y publica `.github/workflows/release.yml` al empujar una etiqueta `vX.Y.Z`: `build.ps1`, `--self-test` del ejecutable empaquetado, instalación y desinstalación silenciosas con `--self-test` del instalado, y Release con el instalador con versión, el fijo y `SHA256SUMS.txt`. Así no depende de una PC concreta y lo publicado es lo que se probó. A mano (`workflow_dispatch`) solo construye y prueba. |
| Sumas de verificación de los instaladores | Cada Release publica `SHA256SUMS.txt` con el SHA-256 del instalador con versión y del fijo. GitHub también muestra los digests, pero un archivo se puede comprobar sin conexión y winget lo usará. |
| winget | Pendiente de que Microsoft acepte el paquete `Alfiq.Cotorreando`. El manifiesto apunta al instalador **con versión** (`Cotorreando-X.Y.Z-setup.exe`), no al de nombre fijo, cuyo contenido cambia en cada Release y rompería el SHA-256. La automatización es el job `winget` al final de `release.yml` (winget-releaser fijado por SHA, secreto `WINGET_TOKEN`; sin secreto se omite), en el mismo workflow porque las Releases de `GITHUB_TOKEN` no disparan otros workflows. La primera versión la envía a mano la persona dueña del repositorio, porque la acción solo actualiza paquetes existentes. Ver [VERSIONES.md](VERSIONES.md). |
| Dependencias | `pyproject.toml` solo pone pisos (`>=`) sin techo, redondeados a lo instalado cuando se fijaron. `requirements.lock` fija cada paquete con hash SHA-256 y es lo que instalan `build.ps1` y el job de Python 3.12 de CI; el de 3.10 resuelve libre para detectar roturas de versiones nuevas. Dos pisos (`numpy`, `onnxruntime-directml`) quedan por debajo de lo instalado porque Python 3.10 no tiene wheels más nuevas. No se prueban las versiones mínimas: duplicaría la matriz de CI y los pisos se subirían igual en cuanto el código use algo nuevo. |

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
`releases/latest/download/Cotorreando-setup.exe`, y el workflow que publica cada Release le sube
una copia del instalador con ese nombre fijo. No usa la API de GitHub ni JavaScript.

#### Globito de la cotorra
Al pasar el mouse sobre la cotorra sale un globito con una frase distinta cada vez («¿Tienes algo
que decir?», «Cuenta el chisme.», «A ver, cuéntamelo todo.») y el atajo al final. Los botones y
menús se quedan sobrios; el juego va solo en los globitos.

#### Video de presentación
Un video de 31 s en la portada del sitio (`docs/_extra/cotorreando.mp4`). Para el README se sube
por la web de GitHub, que solo así lo muestra como reproductor. Va en git y no en Git LFS: pesa
2,5 MB y el workflow del sitio no baja archivos de LFS; `.gitattributes` lo marca como binario. La
miniatura (`cotorreando.jpg`, también el primer cuadro del video) es la cotorra con sus plumas y no
el logo, para no repetir el banner que va encima. La narración describe lo que se ve, para quien no ve, y los subtítulos van dentro
de la imagen, para quien no oye; por eso no lleva pista de subtítulos aparte, que los duplicaría, y
en su lugar el sitio muestra la transcripción en texto. La cotorra del video es el `Blob` real,
renderizado cuadro a cuadro con el volumen de la narración, no una imitación. Voz sintética
(Kokoro-82M, Apache-2.0) y música de Sascha Ende (CC BY 4.0), con crédito en el video y en el sitio.

#### Idiomas que habla el usuario
Al primer arranque (y una vez a quien ya lo tenía instalado) se pregunta en qué idiomas va a
hablar, entre los 25 que entiende Parakeet TDT 0.6B v3 (`cotorreando/languages.py`). Arriba van,
ya marcados, los de los teclados y el formato regional de Windows; el resto, en orden alfabético.
Una búsqueda filtra por el nombre propio, el español, el inglés o el código, sin distinguir
acentos ni mayúsculas. Se pregunta en la app y no en el instalador para que el texto viva en
`i18n.py`. El modelo detecta el idioma por sí solo, así que la elección no cambia el
reconocimiento: decide qué se lee en la calibración y queda guardada en `languages`.

#### Textos de calibración en los 25 idiomas
Los de español e inglés están escritos a mano. Los otros 23 los arma `scripts/build_panels.py` con
frases de la colección de Common Voice (CC0, revisadas por hablantes de cada idioma), fijada a un
commit para que se puedan regenerar idénticos: frases de 5 a 18 palabras, sin cifras ni enlaces,
unidas en 12 paneles de 150 a 210 caracteres, el largo de los escritos a mano (por palabras
salían el doble en idiomas como el ruso o el griego). Nadie del proyecto habla esos idiomas, así que no se
eligieron por cobertura fonética como los dos escritos a mano; si alguien los revisa, mejor. Cada
idioma toma unos 3 minutos. Con uno o dos elegidos, la calibración lee todos; con más, solo el
primero, para no pedir 24 minutos de lectura con ocho. "Todos mis idiomas" sigue disponible, al
final de la lista. Los idiomas se cambian después desde Opciones y se aplican con el resto de las opciones: cerrar
la ventana o cancelar Opciones los deja como estaban. Las grabaciones de calibración se guardan
por idioma y número de panel, no por texto: si se regeneran los paneles de un idioma con
`build_panels.py`, sus grabaciones viejas quedarían unidas a otro texto, así que hay que cambiar
de commit de Common Voice solo junto con una forma de descartarlas. Los paneles de práctica que escribe Qwen siguen solo en español e inglés. Si el usuario ya
calibraba en un idioma que sigue eligiendo (o en "ambos", con español e inglés), se respeta; un
idioma que dejó de elegir cuenta como "todos". Cerrar la ventana de idiomas equivale a aceptar lo
marcado, o el idioma de la interfaz si no hay nada: así quien actualiza nunca se queda sin poder
abrir la app.

## Pendientes

- [ ] Confirmar con más grabaciones reales que el LoRA mejora. En el barrido mejoró en 2 de 6
      grupos y no empeoró en ninguno, pero con pocas grabaciones.
