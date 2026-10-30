# Entrenar tu voz (LoRA)

## Qué hace

1. Al terminar de cargar el modelo por primera vez se abre la calibración. Se puede omitir
   y repetir luego en **Opciones → Modelo**.
2. Se leen paneles breves. Parakeet sigue la lectura en vivo (`lora/align.py`): las palabras
   se iluminan y el panel termina solo tras las últimas palabras y 1,2 s de silencio;
   si no, se pulsa **Terminado**. Se asume que el audio coincide con el texto.
3. Una de cada seis grabaciones se reserva. Se añaden adaptadores LoRA (rango 8, alfa 16) a
   las proyecciones `q`, `k`, `v` y `out` de la atención de las 24 capas del codificador.
   Solo se entrenan los adaptadores; el modelo base queda congelado.
4. Se compara el WER sobre lo reservado, primero en NeMo y luego con el ONNX en streaming, que
   es lo que se usa al dictar. Si no mejora, se conserva el modelo original. Si mejora, queda en
   `%LOCALAPPDATA%\Cotorreando\models\adapters\<nombre>` y se activa.

La descarga arranca al empezar a leer y el entrenamiento sigue en segundo plano; mientras tanto
se dicta con el modelo actual.

## Paneles

`lora/datasets/es.txt` y `en.txt`: 12 paneles por idioma, unos 2,4 min de lectura.
`scripts/coverage.py` mide la cobertura: 24/24 fonemas del español (reglas, seseante) y
39/39 del inglés (CMUdict), con 223 y 368 difonos distintos dentro de palabra. Cubren todos
los fonemas, no todos los difonos posibles. También incluyen números, fechas, puntuación,
comandos de edición y anglicismos.

## Dependencias (solo al entrenar)

| Paquete | Licencia | Tamaño |
|---|---|---|
| PyTorch + torchaudio (CUDA 12.8) | BSD-3 | ~3 GB |
| NVIDIA NeMo Toolkit [asr] | Apache-2.0 | ~2 GB con dependencias |
| onnx, onnxruntime | Apache-2.0, MIT | ~50 MB |
| uv | MIT / Apache-2.0 | ~40 MB |

No se instalan con la app. La pantalla de bienvenida avisa del tamaño; al pulsar **Empezar**
se descarga `uv`, se crea un entorno con Python 3.12 en `%LOCALAPPDATA%\Cotorreando\train-env`
y se instalan ahí. El script `lora/train.py` corre en ese entorno, separado de la app.

Con GPU NVIDIA usa CUDA (probado con 16 GB de VRAM). Sin ella instala PyTorch para CPU, que
pesa menos pero entrena mucho más lento.

## Respaldo del modelo

Si la descarga del ONNX de istupakov falla, `asr.export_from_nemo` usa este mismo
entorno para exportar el modelo original de NVIDIA (`train.py --export-only`).
