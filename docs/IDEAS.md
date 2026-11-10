# Ideas

> Lo que podría venir después. Nada de esto hace falta para que Cotorreando funcione, pero se
> vale soñar.

## Por hacer

### Escritura

| Idea | Qué haría |
|---|---|
| **Comandos de voz** | Entender «nueva línea», «punto y aparte» o «borra eso» como órdenes, no como texto. |
| **Diccionario personal** | Cambiar, después de transcribir, los nombres y siglas que tú escribes a tu manera. Hoy tus correcciones solo *refuerzan* esas palabras al reconocer; no las sustituyen. |
| **Pegar en vez de teclear** | Una opción para textos muy largos, donde teclear letra por letra es lento. |
| **Historial** | Las últimas frases que dictaste, a la mano para copiarlas otra vez. |

### Interfaz

| Idea | Qué haría |
|---|---|
| **Aviso en el blob** | Un destello breve cuando se tira una frase porque estabas tecleando. |

### Modelo

| Idea | Qué haría |
|---|---|
| **Streaming nativo** | Si NVIDIA publica un Parakeet multilingüe *cache-aware*, la latencia podría bajar bastante del ≈0,8 s actual con GPU. |

## Ya hechas

| Idea | Cómo quedó |
|---|---|
| **Menos memoria** | El modelo se libera tras un rato sin dictar y se recarga al volver a hablar. |
| **Atajo grabable** | La combinación se captura pulsando las teclas, no escribiéndola. |
| **Entrenamiento con verificación** | Se reservan grabaciones para medir el WER antes y después; si el adaptador no mejora, se descarta. |
