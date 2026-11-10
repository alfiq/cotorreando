# Entrenar tu voz (LoRA)

Mientras más te oye, mejor te entiende. Lees unas frases en voz alta y Cotorreando ajusta el
modelo a tu voz, a tu acento y a tu micrófono. Todo en tu computadora.

## Qué hace

1. La primera vez que termina de cargar el modelo, se abre la calibración. Te la puedes saltar y
   hacerla después en **Opciones → Modelo**.
2. Lees paneles cortos. Parakeet te va siguiendo en vivo (`lora/align.py`): las palabras se
   iluminan y el panel termina solo cuando dices las últimas y te quedas callado 1,2 s. Si no,
   pulsa **Terminado**. Se da por hecho que leíste lo que dice el texto.
3. Una de cada seis grabaciones se reserva. Se añaden adaptadores LoRA (rango 4, alfa 8) a
   las proyecciones `q`, `k`, `v` y `out` de la atención y a las dos `feed_forward` de las 24
   capas del codificador.
   Solo se entrenan los adaptadores; el modelo base queda congelado.
   Los adaptadores no se fusionan en los pesos: se injertan como ramas fp32 en paralelo
   (`y = W·x + (α/r)·B·A·x`) sobre el mismo `encoder-model.int8.onnx` que usa la app. Fusionarlos
   y volver a cuantizar los borraba (el cambio es un 2 % de un escalón int8) y una exportación
   nueva desde NeMo salía peor que el modelo original. El injerto añade ~11 MB y deja
   el modelo base intacto. Para comparar diseños: `scripts/lora_sweep.py`.
   Se entrena sobre el modelo que usa la app, no sobre el fp32 de NeMo: los pesos que la app
   cuantiza se sustituyen por su valor int8 (desplegando la BatchNorm que el exportador fusionó en
   las convoluciones depthwise) y sus entradas pasan por la misma cuantización uint8 dinámica
   (`AppWeights` en `train.py`). Entrenado sobre fp32, el LoRA corregía errores que solo comete
   NeMo y empeoraba la app.
4. Se compara el WER sobre lo reservado, primero en NeMo y luego con el ONNX en streaming, que
   es lo que se usa al dictar. Si no mejora, se conserva el modelo original. Si mejora, queda en
   `%LOCALAPPDATA%\Cotorreando\models\adapters\<nombre>` y se activa.

La descarga arranca en cuanto empiezas a leer y el entrenamiento sigue en segundo plano. Mientras
tanto puedes dictar con el modelo de siempre.

## Por qué este diseño

Barrido con `scripts/lora_sweep.py` (validación cruzada en 6 grupos, medido como en la app:
int8 con injerto y en streaming; WER del modelo base 3,1 %):

| Diseño | WER | Grupos que mejoran / empeoran |
|---|---|---|
| Solo atención, entrenado en fp32 (lo anterior) | 4,7 % | 0 / 2 |
| Solo atención, entrenado en int8 | 2,8 % | 1 / 0 |
| Atención + FFN, rango 8 | 1,5 % | 2 / 0 |
| **Atención + FFN, rango 4** | **1,5 %** | **2 / 0** |
| Coseno, LR más alto o dropout | 2,3–3,1 % | empeoran en algunos |

El rango 4 rinde igual que el 8 con la mitad de parámetros. Ojo: hay pocas grabaciones, así que
esto es una señal, no una prueba. Por eso el paso 4 sigue tirando el adaptador si no mejora.

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

No vienen con la app, porque pesan un montón y no todos van a entrenar. La pantalla de bienvenida
te avisa cuánto pesan. Si pulsas **Empezar**, baja `uv`, crea un entorno con Python 3.12 en
`%LOCALAPPDATA%\Cotorreando\train-env` y los instala ahí. El script `lora/train.py` corre en ese
entorno, aparte de la app.

Con GPU NVIDIA usa CUDA (probado con 16 GB de VRAM). Sin ella instala PyTorch para CPU, que pesa
menos pero entrena mucho más lento. Ve por un café.

## Respaldo del modelo

`asr.export_from_nemo` puede usar este mismo entorno para exportar el modelo original de NVIDIA
(`train.py --export-only`) si la descarga del ONNX de istupakov falla. Ojo: hoy nada en la app la
llama, así que este respaldo no está conectado.
