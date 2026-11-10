# Privacidad

La privacidad es un derecho, no un privilegio. Cotorreando oye tu micrófono y escribe en tus
programas, así que te toca saber qué hace con eso.

En corto: **tu voz se procesa en tu PC**. No hay cuentas, ni telemetría, ni analíticas. Lo que
aprende de ti se guarda cifrado, y solo se abre con tu contraseña o con tu código de recuperación.
Nadie más mete las narices... ni el pico.

*English: [PRIVACY.md](PRIVACY.md)*

## Qué escucha y cuándo

- El micrófono solo está abierto mientras Cotorreando está **activado** (la burbuja no está gris).
  Desactivarlo, con el atajo o el menú, cierra el micrófono.
- Qué se convierte en texto depende del modo de escucha:
  - **Micrófono abierto**: cada frase que dices.
  - **Pulsar para hablar**: solo lo que dices mientras mantienes el atajo.
  - **Activación por voz**: despierta con voz por encima del umbral y escucha hasta unos segundos de silencio.
  - **Activación por palabra clave**: despierta al oír la palabra clave («oye cotorro»).
- Para saber si estás hablando, el audio pasa por un detector local (Silero VAD). Nada de eso se
  graba.
- Si tienes activa la cancelación de eco, también oye lo que sale de tus bocinas, pero solo para
  restarlo del micrófono.

## Qué escribe y cómo

- Escribe **haciéndose pasar por el teclado** (`SendInput` de Windows) en la ventana donde está el
  cursor. Nunca escribe en sus propias ventanas.
- **No registra lo que tecleas.** No usa un *hook* de teclado. Lo que sí hace:
  - Revisa si están presionadas las teclas de tu atajo, para saber cuándo lo usas.
  - Mira a qué hora fue tu última tecla o movimiento del mouse, para saber si estás tecleando.
  - Vigila los clics del mouse, para saber si moviste el cursor y no escribir en otro lado.
  - Mientras grabas un atajo nuevo en Opciones, lee qué teclas tienes presionadas.

  Nada de eso se guarda.
- **Si tecleas mientras dictas, suelta la frase que estabas diciendo** para no escribirte encima.
  Retoma con la siguiente frase, 1,2 s después de tu última tecla (de fábrica).

## Qué sale a internet, y cuándo

Todo el reconocimiento pasa en tu computadora. Estas son las conexiones que hace. Todas van por
HTTPS y ninguna lleva datos tuyos; las librerías de descarga mandan su versión, como cualquier
programa:

| Qué | A dónde | Cuándo |
|---|---|---|
| Modelo de voz (~670 MB) | Hugging Face (`istupakov/parakeet-tdt-0.6b-v3-onnx`) | La primera vez, o si pides volver a descargarlo. Con un modelo propio no se descarga. |
| Detector de voz (Silero VAD, ~2 MB) | GitHub (`snakers4/silero-vad`, v5.1.2) | La primera vez. |
| `tokenizer.json` del modelo | Hugging Face (`nvidia/parakeet-tdt-0.6b-v3`) | La primera vez que se usa el impulso de tus palabras, con el modelo descargado. |
| Buscar actualizaciones | `api.github.com` | Como mucho una vez al día. Es un GET simple con el *User-Agent* `Cotorreando/<versión>`; GitHub ve tu IP, como en cualquier visita. Nunca descarga ni instala nada. Se apaga en Opciones › Privacidad › Buscar actualizaciones. |
| Entorno de entrenamiento (opcional, varios GB) | GitHub (`uv` y, si no lo tienes, Python 3.12), PyPI, `download.pytorch.org`, Hugging Face (NeMo `nvidia/parakeet-tdt-0.6b-v3` y `Qwen/Qwen3-0.6B`) | Solo si entrenas tu voz, y cada vez que entrenas vuelve a revisar Hugging Face. Qwen solo se usa con GPU NVIDIA, para escribir en tu PC frases de práctica con tus palabras difíciles. El entrenamiento corre en tu PC: tu audio no se sube. |

Los enlaces (novedades, licencias, esta página) se abren en tu navegador solo cuando tú les das clic.

## Qué guarda y dónde

Tus datos viven en `%LOCALAPPDATA%\Cotorreando`:

| Archivo o carpeta | Qué es | ¿Cifrado? |
|---|---|---|
| `settings.json` | Tus opciones (incluye la palabra clave y las apps excluidas). | No |
| `cotorreando.log` | Registro técnico de la última sesión (se borra al abrir). Errores, modo de escucha, nombre del micrófono, cuántas palabras cambió una corrección. No guarda lo que dictas. Si entrenas, también guarda los mensajes de las herramientas de entrenamiento: revísalo antes de compartirlo. | No |
| `models\` | Modelos descargados y tus modelos de voz entrenados (`models\adapters`). | No: hacen falta para dictar |
| `vault\records\` | Audio y texto de tus correcciones. | Sí |
| `vault\journal\` | Palabras que notó mientras la bóveda estaba cerrada, por fundir en tus listas. | Sí |
| `vault\*.sealed` | Listas de palabras difíciles, correcciones y palabras tuyas; punto de control de entrenamiento. | Sí |
| `vault\trained.json` | Solo los identificadores (fechas) de lo ya entrenado. | No |
| `recordings\` | Lecturas de calibración de tu voz. | Sí |
| `tools\`, `train-env\` | El entorno de entrenamiento, si lo instalaste. | No (no tiene datos tuyos) |

Si instalaste el entorno de entrenamiento, las herramientas también dejan caché fuera de esa
carpeta: en `%USERPROFILE%\.cache\huggingface` y en la caché de `uv`. Son varios GB, sin nada
tuyo.

**Sin contraseña no se guarda nada de tu voz ni de lo que dictas, punto.** Puedes dictar igual,
pero no aprende. Lo único que se guarda son tus opciones, el registro técnico y los modelos.

**La contraseña y el código de recuperación.** La primera vez, cuando el modelo ya cargó, te
ofrece crear una contraseña. Es opcional. Cuando la creas, te da un **código de recuperación** que
solo se muestra esa vez. Imprímelo y guárdalo en un lugar seguro. En un archivo de texto en la
misma computadora no, por favor, no seas así. Si se te olvida la contraseña, ese código es la
única forma de recuperar tus grabaciones, tus correcciones y lo que aprendió de tu voz. Cuídalo.

Para cambiar la contraseña, haz clic derecho en la cotorra, elige **Opciones…** y en la pestaña
**Privacidad** pulsa **Cambiar contraseña…**. Si la olvidaste, al pedirte la contraseña pulsa
**La olvidé** y usa el código.

**Cómo se cifra**: con [age](https://age-encryption.org). Lo que se guarda se sella con una clave
pública, así que el dictado puede guardar cosas sin poder leerlas. La clave privada está en disco,
cifrada con tu contraseña y, aparte, con el código de recuperación.

Nosotros hacemos lo posible para que nadie más lo lea. Lo demás te toca a ti: no dejes tu
computadora desbloqueada cuando no estás.

**Cuánto tiempo se guarda**: los registros y el diario que pasen de «Borrar datos con más de
(días)», 180 de fábrica, se borran al abrir Cotorreando. Las lecturas de calibración se quedan
hasta que las borres.

## Aprendizaje

Cotorreando aprende de los errores que comete cuando corriges lo que escribió. Es opcional: lo
apagas en la bienvenida o en Opciones › Privacidad › Aprender de mis correcciones, y además
necesita que hayas creado una contraseña. Cuando está prendido:

- **Al empezar a dictar lee el texto que ya hay en el campo** (hasta 20 000 caracteres), para
  acertar con mayúsculas y espacios y preferir palabras que ya usaste ahí. Eso se queda en memoria
  y no se guarda.
- Guarda las **palabras en las que el modelo dudó** (solo la palabra, sin audio).
- Busca **correcciones**: tras dictar, mira el campo donde escribió, cada 2 s y **solo mientras
  ese campo tiene el foco**, hasta 2 minutos. Si cambiaste unas pocas palabras por otras que suenan
  parecido, guarda la frase corregida con su audio. Si reescribiste casi todo, no cuenta como
  corrección. Si corregiste unas palabras y luego enviaste o borraste el texto, se queda la última
  versión corregida que alcanzó a ver.
- No lee ni aprende de los **campos que Windows reconoce como de contraseña**, ni de las **apps
  excluidas** que pongas en Opciones.
- El resto del audio se olvida en cuanto termina la frase.

## Ver, exportar y borrar tus datos

En Opciones › Privacidad (te pide la contraseña):

- **Ver mis datos…**: escucha, edita o borra cada corrección, o bórralas todas; quita palabras de tus listas.
- **Exportar** crea un archivo `.cotorreando` cifrado con una contraseña que eliges (el audio solo si lo marcas).
- **Importar** lo trae a otra instalación.

## Desinstalar

El desinstalador quita el programa y el inicio automático, y después **te pregunta si quieres
borrar tus datos** (la carpeta `%LOCALAPPDATA%\Cotorreando`). El botón marcado de fábrica es No,
para que puedas reinstalar sin perderlos, y en una desinstalación silenciosa no se borra nada. Si
dijiste que no y luego cambias de opinión, borra esa carpeta a mano: pega la ruta en el Explorador
de archivos y listo.

La caché del entrenamiento (`%USERPROFILE%\.cache\huggingface` y la de `uv`) no la borra el
desinstalador. Si quieres recuperar ese espacio, bórrala a mano.

## Dudas

Abre un issue en <https://github.com/alfiq/cotorreando/issues>. El código es abierto, así que no
tienes que creernos: todo lo de esta página lo puedes comprobar en el repositorio.
