# Cambios

## 0.0.1 — 2026-10-29

Primera versión.

- Dictado por voz en cualquier aplicación de Windows con Parakeet TDT 0.6B v3 (ONNX int8).
- Streaming real por bloques: el texto aparece mientras hablas y nunca se reescribe.
- Codificador en GPU vía DirectML con ventana de tamaño fijo; CPU como respaldo.
- Modos: micrófono abierto, pulsar para hablar y activación por voz o palabra clave.
- Supresión de ruido, cancelación de eco y control de ganancia (WebRTC).
- Pausa automática del dictado mientras tecleas.
- Blob flotante: burbuja translúcida con plumas de colores, ondas con la voz, tornasol al
  escribir, estiramiento pegajoso al arrastrar y tres tamaños.
- Entrenamiento de voz con LoRA (dependencias opcionales, se instalan bajo demanda).
- Interfaz en español e inglés; ejecutable con Nuitka e instalador con Inno Setup.
