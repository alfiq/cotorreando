# Cambios

## 0.0.6 — 2026-11-01

- Ver mis datos rediseñado: tarjetas con el texto completo, en el estilo del resto de los menús.
- Se puede escuchar el audio de cada registro, sin dejar copias sin cifrar en el disco.
- El texto de cada registro se puede editar a mano; lo editado cuenta como verificado y se vuelve a entrenar.
- Cada registro se puede borrar desde su propia tarjeta.

## 0.0.5 — 2026-10-31

- Entrenamiento mucho más rápido: la pérdida ya no construye un grafo por celda y la VRAM no se
  desborda. Con voz sintética, un trabajo de 160 pasos pasa de más de una hora a unos 2 min.
- La evaluación final no repite medidas ni cargas de modelo.
- Dictado en CPU con menos latencia y menos consumo: los hilos del codificador ya no giran en vacío.

## 0.0.4 — 2026-10-30

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
- Instalador propio: con las plumas de fondo, primero platica qué es Cotorreando y luego instala.
- Ventanas con barra de título propia, del color de la ventana y solo con cerrar.
- La burbuja se desvanece hasta ser transparente justo en su contorno, tenga la forma que tenga.
- Sin gancho de teclado: la app ya no recibe lo que tecleas; solo consulta las teclas del atajo y
  la hora de la última actividad. Mover el ratón mientras tecleas puede ocultar alguna pulsación.
- Contraseña obligatoria para aprender: todo se cifra con age y ya no lo puede abrir otro programa de
  tu cuenta de Windows. Se pide al entrenar o ver tus datos, y un aviso de la burbuja la ofrece para
  activar tus correcciones. Incluye código de recuperación. Los datos anteriores se pasan a una clave nueva.

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
