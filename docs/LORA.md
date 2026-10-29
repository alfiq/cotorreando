# Entrenar tu voz (LoRA)

## Qué hace

1. Eliges un conjunto de frases y las lees una por una (Grabar → Detener).
2. Con al menos 10 frases grabadas, pulsas **Entrenar**.
3. Se añaden adaptadores LoRA (rango 8, alfa 16) a las proyecciones `q`, `k`, `v` y
   `out` de la atención de las 24 capas del codificador Conformer. Solo se entrenan
   los adaptadores (~1,6 M de parámetros); el modelo base queda congelado.
4. Se fusionan los adaptadores con los pesos, se exporta a ONNX y se cuantiza a int8.
   El resultado queda en `%LOCALAPPDATA%\Cotorreando\models\adapters\<nombre>` y se activa.

En **Opciones → Modelo** puedes volver al modelo original o elegir otro adaptador.

## Conjuntos de frases

| Archivo | Frases | Lectura aprox. |
|---|---|---|
| `es_30.txt` | 30 | 4 min |
| `es_60.txt` | 60 | 8 min |
| `es_150.txt` | 150 | 20 min |

Los conjuntos están anidados: las 30 primeras frases son las de mayor variedad. Cubren:
todos los fonemas del español, vibrante simple y múltiple (*pero/perro*), oclusivas y
sus alófonos aproximantes (*b/d/g* entre vocales), *ñ*, *ll/y*, *ch*, *j/g*, *x*
(México, Xochimilco, Ximena), *tl* (tlacuache), diptongos e hiatos, nahuatlismos,
números, fechas, signos de puntuación, comandos de edición y anglicismos usuales
(software, PDF, wifi).

Puedes crear los tuyos: un `.txt` con una frase por línea (las que empiezan con `#` se
ignoran) en `%LOCALAPPDATA%\Cotorreando\datasets`.

## Dependencias (solo al entrenar)

| Paquete | Licencia | Tamaño |
|---|---|---|
| PyTorch + torchaudio (CUDA 12.8) | BSD-3 | ~3 GB |
| NVIDIA NeMo Toolkit [asr] | Apache-2.0 | ~2 GB con dependencias |
| onnx, onnxruntime | Apache-2.0, MIT | ~50 MB |
| uv | MIT / Apache-2.0 | ~40 MB |

No se instalan con la app. Al abrir **Entrenar mi voz…** se avisa; al pulsar **Entrenar**
se descarga `uv`, se crea un entorno con Python 3.12 en `%LOCALAPPDATA%\Cotorreando\train-env`
y se instalan ahí. El script `lora/train.py` corre en ese entorno, separado de la app.

Requiere GPU NVIDIA (probado para 16 GB de VRAM; 8 GB debería bastar con lotes de 4).

## Respaldo del modelo

Si la descarga del ONNX de istupakov falla, `asr.export_from_nemo` usa este mismo
entorno para exportar el modelo original de NVIDIA (`train.py --export-only`).
