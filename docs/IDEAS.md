# Ideas

Cosas que podrían venir después. Ninguna es necesaria para que funcione.

- **Comandos de voz**: «nueva línea», «punto y aparte», «borra eso».
- **Diccionario personal**: reemplazos tras la transcripción (nombres, siglas). Hoy tus
  correcciones solo refuerzan esas palabras al reconocer; no las sustituyen.
- **Retroalimentación del blob**: un destello breve cuando una frase se descarta
  porque estabas tecleando.
- **Modelo de streaming nativo**: si NVIDIA publica un Parakeet multilingüe con caché
  (*cache-aware*), bajaría la latencia por debajo de 0,5 s.
- **Pegar en vez de teclear** para textos muy largos, como opción.
- **Historial**: las últimas frases dictadas, para copiar de nuevo.

## Ya hechas

- **Menos memoria**: el modelo se libera tras un rato sin dictar y se recarga al volver a hablar.
- **Atajo grabable**: la combinación se captura pulsando las teclas.
- **Entrenamiento con verificación**: se reservan grabaciones para medir el WER antes y después,
  y el adaptador se descarta si no mejora.
