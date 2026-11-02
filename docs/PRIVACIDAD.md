# Privacidad

Cotorreando oye tu micrófono y escribe en tus programas, así que es justo que sepas qué hace con
eso. En corto: **tu voz se procesa en tu PC**, no hay cuentas, ni telemetría, ni analíticas, y lo
que aprende de ti se guarda cifrado con tu contraseña.

*English: [PRIVACY.md](PRIVACY.md)*

## Qué escucha y cuándo

- El micrófono solo está abierto mientras Cotorreando está **activado** (la burbuja no está gris).
  Desactivarlo, con el atajo o el menú, cierra el micrófono.
- Qué se convierte en texto depende del modo de escucha:
  - **Micrófono abierto**: cada frase que dices.
  - **Pulsar para hablar**: solo lo que dices mientras mantienes el atajo.
  - **Activación por voz**: despierta con voz por encima del umbral y escucha hasta unos segundos de silencio.
  - **Activación por palabra clave**: despierta al oír la palabra clave («oye cotorro»).
- Para detectar voz, el audio pasa por un detector local (Silero VAD). Nada de eso se graba.
- Si la cancelación de eco está activa, también lee el sonido que sale de tus bocinas, solo para
  restarlo del micrófono.

## Qué escribe y cómo

- Escribe **simulando el teclado** (`SendInput` de Windows) en la ventana que tiene el cursor.
  Nunca escribe en sus propias ventanas.
- **No lee tus teclas.** No usa un *hook* de teclado: para saber que estás tecleando solo mira la
  hora de la última entrada. Si tecleas, el dictado se pausa y sigue tras un momento (1,2 s por defecto).

## Qué sale a internet, y cuándo

Todo el reconocimiento ocurre en tu equipo. Solo hay estas conexiones, todas HTTPS y sin datos tuyos:

| Qué | A dónde | Cuándo |
|---|---|---|
| Modelo de voz (~670 MB) | Hugging Face (`istupakov/parakeet-tdt-0.6b-v3-onnx`) | La primera vez, o si pides volver a descargarlo. Con un modelo propio no se descarga. |
| Detector de voz (Silero VAD, ~2 MB) | GitHub (`snakers4/silero-vad`, v5.1.2) | La primera vez. |
| `tokenizer.json` del modelo | Hugging Face (`nvidia/parakeet-tdt-0.6b-v3`) | La primera vez que se usa el impulso de tus palabras, con el modelo descargado. |
| Buscar actualizaciones | `api.github.com` | Como mucho una vez al día. Es un GET simple con el *User-Agent* `Cotorreando/<versión>`; GitHub ve tu IP, como en cualquier visita. Nunca descarga ni instala nada. Se apaga en Opciones › Privacidad › Buscar actualizaciones. |
| Entorno de entrenamiento (opcional, varios GB) | GitHub (`uv`), PyPI, `download.pytorch.org`, Hugging Face (NeMo `nvidia/parakeet-tdt-0.6b-v3` y `Qwen/Qwen3-0.6B`) | Solo si entrenas tu voz. El entrenamiento corre en tu PC: tu audio no se sube. |

Además, los enlaces (novedades, licencias, esta página) se abren en tu navegador solo cuando les das clic.

## Qué guarda y dónde

Todo vive en `%LOCALAPPDATA%\Cotorreando`:

| Archivo o carpeta | Qué es | ¿Cifrado? |
|---|---|---|
| `settings.json` | Tus opciones (incluye la palabra clave y las apps excluidas). | No |
| `cotorreando.log` | Registro técnico de la última sesión (se borra al abrir). Errores, modo de escucha, nombre del micrófono, cuántas palabras cambió una corrección. **No guarda lo que dictas.** | No |
| `models\` | Modelos descargados y tus modelos de voz entrenados (`models\adapters`). | No: hacen falta para dictar |
| `vault\records\` | Audio y texto de tus correcciones. | Sí |
| `vault\journal\` | Palabras que notó mientras la bóveda estaba cerrada, por fundir en tus listas. | Sí |
| `vault\*.sealed` | Listas de palabras difíciles, correcciones y palabras tuyas; punto de control de entrenamiento. | Sí |
| `vault\trained.json` | Solo los identificadores (fechas) de lo ya entrenado. | No |
| `recordings\` | Lecturas de calibración de tu voz. | Sí |
| `tools\`, `train-env\` | El entorno de entrenamiento, si lo instalaste. | No (no tiene datos tuyos) |

**Cómo se cifra**: con [age](https://age-encryption.org). Lo que se guarda se sella con una clave
pública, así que el dictado puede guardar sin poder leerlo. La clave privada está en disco cifrada
con **tu contraseña** y, aparte, con un **código de recuperación** que se muestra una sola vez.
Para leer cualquier cosa hace falta la contraseña. Sin contraseña puedes dictar, pero no se aprende ni se guarda nada de tu voz.

**Retención**: los registros y el diario con más días que «Borrar datos con más de (días)»
(180 por defecto) se borran al abrir Cotorreando.

## Aprendizaje

Es opcional: se apaga en la bienvenida o en Opciones › Privacidad › Aprender de mis correcciones,
y además necesita que hayas creado una contraseña. Cuando está activo:

- Guarda las **palabras en las que el modelo dudó** (solo la palabra, sin audio).
- Busca **correcciones**: tras dictar, mira el campo donde escribió, cada 2 s y **solo mientras
  ese campo tiene el foco**, hasta 2 minutos. Si cambiaste unas pocas palabras por otras que suenan
  parecido, guarda la frase corregida con su audio. Si borraste o reescribiste el texto, no guarda nada.
- No lee ni aprende de **campos de contraseña**, ni de las **apps excluidas** que pongas en Opciones.
- El resto del audio se olvida en cuanto termina la frase.

## Ver, exportar y borrar tus datos

En Opciones › Privacidad (te pide la contraseña):

- **Ver mis datos…**: escucha, edita o borra cada corrección, o bórralas todas; quita palabras de tus listas.
- **Exportar** crea un archivo `.cotorreando` cifrado con una contraseña que eliges (el audio solo si lo marcas).
- **Importar** lo trae a otra instalación.

## Desinstalar

El desinstalador quita el programa y el inicio automático, pero **no borra tus datos**. Para
quitarlo todo, después de desinstalar borra la carpeta `%LOCALAPPDATA%\Cotorreando`
(pega esa ruta en el Explorador de archivos).

## Dudas

Abre un issue en <https://github.com/alfiq/cotorreando/issues>. El código es abierto: todo lo
de esta página se puede comprobar en el repositorio.
