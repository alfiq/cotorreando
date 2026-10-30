# Diseño

## Objetivo

Lo más pequeño y eficiente posible. Cada dependencia tiene que ganarse su lugar.

## Flujo

```
micrófono ──► WebRTC APM ──► Listener ──► cola ──► Parakeet ──► SendInput
 (WASAPI)    ruido/eco/AGC   VAD + modo            (ONNX)       (teclado)
                ▲
bocinas ────────┘ (loopback, referencia para el eco)
```

## Módulos

| Archivo | Qué hace |
|---|---|
| `app.py` | Conecta todo; menú, bandeja, hilos. |
| `audio.py` | Captura WASAPI a la frecuencia nativa, remuestrea a 16 kHz, aplica WebRTC APM. |
| `listener.py` | Detecta inicio y fin de cada frase según el modo y el VAD; umbral automático. |
| `vad.py` | Silero VAD v5 en ONNX (2 MB). |
| `asr.py` | Parakeet TDT: preprocesador, codificador, decodificador TDT voraz y `Stream` (streaming por bloques). |
| `keyboard.py` | Hook de teclado de bajo nivel (atajo y detección de tecleo) y escritura Unicode. |
| `blob.py` | La ventana flotante y su animación. |
| `dialogs.py` | Opciones, Acerca de y estilos. |
| `credits.py` | Lista única de créditos y licencias. |
| `i18n.py` | Textos en español e inglés. |
| `lora/` | Grabación, entorno de entrenamiento, script de entrenamiento y frases. |

## Decisiones técnicas

**ONNX en vez de NeMo/PyTorch.** NeMo + PyTorch pesan varios GB; ONNX Runtime ~15 MB.
El modelo cuantizado a int8 ocupa ~670 MB y en CPU transcribe ~8× más rápido que el
tiempo real (6 s de audio en 0,7 s). NeMo solo aparece si el usuario entrena.

**Streaming real.** Parakeet TDT v3 es un modelo *offline* (atención completa), así que
no tiene caché de streaming nativa. Se usa streaming por bloques: cada 0,96 s se codifica
una ventana de 2,6 s de contexto ya decodificado + el bloque nuevo + 0,48 s de anticipación,
y solo se decodifican los cuadros del bloque nuevo. El decodificador TDT conserva su estado
(LSTM, último token y el salto pendiente) entre bloques, así que cada token se emite una
única vez: el texto nunca se borra ni se reescribe. El costo por paso es constante, sin
límite de duración. Latencia ≈ 1,4 s; en CPU corre a 0,66× tiempo real y con DirectML a
0,46×. En las pruebas, el resultado es idéntico al de transcribir la frase completa.

**Decodificación TDT.** El decodificador fusionado devuelve, por cada paso, logits de
token (8193 + blank) y de duración (0–4 cuadros). Se elige el token, y si la duración
es 0 se sigue emitiendo en el mismo cuadro (con un tope de 10).

**Captura.** Se intentó SoundCard, pero falla con micrófonos cuyo formato no es
WAVE_FORMAT_EXTENSIBLE (por ejemplo, la webcam Logitech C270). PyAudioWPatch abre
micrófono y loopback con el mismo código. Los dispositivos se abren a su formato
nativo y se remuestrean con un FIR de 64 coeficientes + interpolación lineal.

**Ruido y eco.** El módulo de procesamiento de audio de WebRTC, vía el SDK de LiveKit
(única opción con ruedas para Windows y AEC incluido). Para el eco, el audio de las
bocinas se captura por loopback y se pasa como señal de referencia.

**VAD y umbral.** Silero decide si hay voz; además se exige energía sobre el umbral
(salvo en micrófono abierto). El umbral automático es el percentil 20 del nivel en
los cuadros sin voz de los últimos ~10 s, más 12 dB.

**Palabra clave.** Los modelos preentrenados de openWakeWord son CC BY-NC-SA (no
comerciales), así que se reutiliza Parakeet: se transcribe la frase y se busca la
palabra clave con comparación difusa (ratio ≥ 0,75, sin acentos ni puntuación).

**Pausa al teclear.** El hook ignora las teclas con la bandera `LLKHF_INJECTED`
(las nuestras), así que solo las pulsaciones reales pausan el dictado.

**Atajo Ctrl+Win.** Al soltar Win sola, Windows abre Inicio. Al activarse el atajo se
inyecta una tecla sin asignar (0xE8), lo que lo evita.

**Interfaz.** PySide6 (LGPL, enlazado dinámico). La ventana es `Tool` + `WindowDoesNotAcceptFocus`:
no roba el foco a la aplicación donde se escribe. La animación se detiene por completo
cuando está desactivado y quieto.

**Elasticidad.** Al arrastrar, el ratón mueve un punto objetivo; la ventana lo sigue con un
resorte amortiguado (k = 220, c = 16) y el contorno se estira en la dirección de la velocidad.

**Ejecutable.** Nuitka en modo *standalone*: las DLL de Qt quedan separadas y
reemplazables, como pide la LGPL.

## Tamaño

| Parte | Tamaño aprox. |
|---|---|
| Dependencias Python (sin modelo) | ~150 MB (Qt es la mayor parte) |
| Modelo Parakeet int8 | ~670 MB (se descarga una vez) |
| Silero VAD | 2 MB |
| Entorno de entrenamiento (opcional) | ~6 GB |
