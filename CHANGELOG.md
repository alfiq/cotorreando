# Cambios

## 0.1.3 — 2026-11-09

- Los textos de la app y de la documentación hablan de tú y con más soltura: avisos de error más
  claros, una bienvenida más cercana y un recordatorio de imprimir el código de recuperación.
- Al pasar el mouse sobre la cotorra sale un globito con una frase distinta cada vez y el atajo
  para dictar.
- La página de privacidad dice con más precisión qué revisa del teclado y el mouse, que al teclear
  se descarta la frase en curso, qué lee del campo al empezar a dictar y dónde queda la caché del
  entrenamiento. La versión en inglés ya dice lo mismo que la española. 

## 0.1.2 — 2026-11-09

- Los colores de la interfaz, el blob y el icono de la bandeja salen ahora de la cotorra: verde,
  menta, lima, amarillo, naranja y rojo, con contraste AA en todos los textos.
- El entrenamiento de voz (LoRA) mejora el modelo que usa la app: los adaptadores ya no se pierden
  al exportar y se entrenan sobre los mismos pesos int8. Ahora también adaptan la parte FFN.
- El README tiene cabecera con la cotorra.

## 0.1.1 — 2026-11-05

- El modelo de voz se libera de la memoria tras 10 minutos sin dictar y vuelve a cargarse solo al
  hablar, sin perder lo que dijiste. El tiempo se cambia en Opciones; 0 lo deja siempre cargado.
- El atajo ya no se escribe a mano: haces clic en el campo y pulsas la combinación. Esc cancela y
  «Restaurar» vuelve a Ctrl+Win.
- El README explica cómo pasar el aviso de SmartScreen y ya no pide instalar el certificado.

## 0.1.0 — 2026-11-02

- Seguridad: todo lo que se descarga (el modelo de voz, el detector de voz, las herramientas y
  el modelo base para entrenar) viene de una versión fija y se comprueba byte a byte antes de usarlo.
- El entorno para entrenar se instala con versiones exactas y verificadas de cada paquete.
- Ver mis datos se cierra solo, y vuelve a pedir la contraseña, si bloqueas Windows o dejas el
  equipo 5 minutos sin usar.
- Un ajuste dañado o un archivo importado con valores raros ya no puede borrar tus grabaciones
  ni cerrar la app: se ignora y se usa el valor de siempre.
- Importar rechaza archivos con dictados mal formados.

## 0.0.9 — 2026-11-02

- Avisa cuando hay una versión nueva en GitHub, una vez al día; se apaga en Opciones › Privacidad.
  Nunca descarga ni instala nada solo.
- Descarga del modelo con progreso en el mosaico de la cotorra, cancelable y reanudable, con errores
  claros si no hay conexión, si se corta o si falta espacio.
- Puedes usar tu propio modelo Parakeet TDT en ONNX; se valida antes de aceptarlo.
- Página de privacidad (docs/PRIVACIDAD.md), enlazada desde la bienvenida, Opciones y Acerca de.
- Al desinstalar pregunta si borrar también tus datos.
- Calibrar avisa qué se descarga de internet para entrenar.
- Correcciones: importar ya no acepta el aviso de privacidad, ni deja datos a medias si el archivo
  viene dañado; ajustes guardados de forma atómica; un evento dañado ya no bloquea el aprendizaje;
  la descarga del VAD se reintenta si se cortó; se registran las palabras dudosas.
- Pruebas automáticas y CI en GitHub Actions.

## 0.0.8 — 2026-11-02

- El instalador tiene una página "Lo legal, en corto": hay que aceptar la licencia, con un enlace
  para leer las licencias.
- Aviso de privacidad al abrir por primera vez: qué se queda en la PC, qué se guarda y dónde, y si
  guardar datos para aprender. Si no lo aceptas, la app se cierra sin descargar ni grabar nada.

## 0.0.7 — 2026-11-02

- Sesgo hacia tus palabras, como el phrase boosting de NVIDIA NeMo: automático, siempre o nunca,
  y puedes agregar o quitar palabras propias.
- Las palabras aprendidas se ven en su propia pestaña de los datos guardados.
- Exportar ajustes y palabras en un archivo cifrado, e importarlos agregando o reemplazando.
- Las correcciones solo se buscan mientras el campo dictado tiene el foco.
- La burbuja vuelve a quedar encima si otra ventana siempre visible la tapa (pasaba al iniciar Windows).
- Pre-roll de 0.6 s y migración de datos antiguos más robusta.

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
