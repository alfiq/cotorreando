# Cambios

## 0.0.2 — 2026-10-30

- Calibración inicial: paneles breves en español e inglés, palabras que se iluminan al leer,
  fin automático de panel y entrenamiento LoRA en segundo plano.
- El adaptador solo se activa si reduce los errores en una lectura reservada.
- Opciones rediseñadas: navegación lateral, tarjetas y estilo sobrio.
- Logo azulejado de la cotorra, que se va armando con el progreso.
- Dictado sin frases perdidas: el modelo ve 0,96 s por delante en lugar de 0,48 s.
- Texto provisional inmediato que se corrige en una sola acción, sin tocar el texto previo.
- Aprendizaje continuo: detecta correcciones en el campo, las comprueba contra el audio y, si se
  repiten, las aplica sola. Lleva una lista de palabras dudosas.
- Datos cifrados por cuenta de Windows y PC, con contraseña opcional y opciones de privacidad.
- Paneles de lectura escritos con Qwen3 0.6B (4 bits) que contienen tus palabras difíciles.
- Entrenamiento opcional al apagar o reiniciar, a pantalla completa, que se puede cancelar y retomar.

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
