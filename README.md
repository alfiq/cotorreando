# Cotorreando

Dictado por voz para todo Windows. Hablas, y el texto aparece donde esté el cursor:
en el navegador, en el editor, en el chat… Todo corre en tu máquina, sin nube.

Usa [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
(25 idiomas europeos, con puntuación y mayúsculas) sobre ONNX Runtime.

## El blob

Un círculo flotante, siempre encima de todo, que muestra lo que está pasando:

| Estado | Aspecto |
|---|---|
| Desactivado | Gris y quieto. No consume CPU en animación. |
| Escuchando | Azul, respira suavemente. |
| Hablando | Se deforma con tu voz y suelta ondas a su alrededor. |
| Escribiendo | Colores tornasol que giran. |

Hablar y escribir se combinan: el texto aparece mientras hablas (≈0,8 s de retraso con GPU,
≈1,1 s solo con CPU), sin
borrar ni reescribir, y sin límite de duración. El tamaño se elige en Opciones.

- **Arrástralo** a donde quieras; lo sigue con un resorte elástico y recuerda la posición.
- **Clic derecho**: activar/desactivar, ocultar, opciones, entrenar mi voz, acerca de, salir.
- **Bandeja del sistema**: clic izquierdo lo muestra u oculta; clic derecho da el mismo menú.

## Modos de escucha

| Modo | Cómo funciona |
|---|---|
| Micrófono abierto | Escucha siempre; cada frase (separada por pausas) se escribe. |
| Pulsar para hablar | Mantén el atajo (por defecto `Ctrl+Win`) mientras hablas. |
| Activación por voz | Solo reacciona a voz por encima del umbral de energía. |
| Activación por palabra clave | Di «oye cotorro …»; sigue escuchando unos segundos después. |

En los modos que no son *pulsar para hablar*, el atajo activa o desactiva.

**Si tecleas, el dictado se pausa** aunque sigas hablando, y se reanuda tras el
tiempo de amortiguamiento configurable (1,2 s por defecto).

El umbral puede fijarse a mano o dejar que la app lo calcule: mide el ruido de fondo
mientras no hablas y lo pone 12 dB por encima.

El audio pasa por el procesador de WebRTC: supresión de ruido, cancelación de eco
(usando lo que suena por tus bocinas como referencia) y control automático de ganancia.

## Instalar y ejecutar

Requiere Windows 10/11 y Python 3.10 o superior.

```bash
pip install -e .
```

```bash
cotorreando
```

La primera vez descarga el modelo (~670 MB) a `%LOCALAPPDATA%\Cotorreando\models`.

### Ejecutable

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

Genera `dist\cotorreando.dist\Cotorreando.exe` con Nuitka y el instalador
`dist\Cotorreando-<versión>-setup.exe` con [Inno Setup](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`). El instalador no pide permisos de administrador.

### GPU

Usa `onnxruntime-directml`, que funciona en CPU y aprovecha cualquier GPU de DirectX 12
si está activado «Usar GPU» en Opciones.

## Entrenar tu voz (LoRA)

Desde el menú, **Entrenar mi voz…**: lees en voz alta una lista de frases y se entrena
un adaptador LoRA para el modelo. Hay tres conjuntos en español (30, 60 y 150 frases),
y puedes añadir los tuyos como `.txt` en `%LOCALAPPDATA%\Cotorreando\datasets`.

Entrenar necesita PyTorch y NeMo (~6 GB). **No vienen incluidos**: la app avisa y los
instala aparte, solo si lo pides. Detalles en [docs/LORA.md](docs/LORA.md).

## Documentación

- [docs/DISENO.md](docs/DISENO.md) — arquitectura y decisiones.
- [docs/LORA.md](docs/LORA.md) — entrenamiento del adaptador.
- [docs/DECISIONES.md](docs/DECISIONES.md) — preguntas resueltas durante el diseño.
- [docs/IDEAS.md](docs/IDEAS.md) — ideas y pendientes.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — licencias y créditos.

## Créditos

Autor: **Alfiq** · [github.com/alfiq](https://github.com/alfiq) ·
[github.com/alfiq/cotorreando](https://github.com/alfiq/cotorreando)

Inspirado en la idea de [Handy](https://github.com/cjpais/handy) (MIT).
Modelo Parakeet TDT 0.6B v3 de NVIDIA bajo CC BY 4.0.
El resto de componentes y sus licencias están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Licencia MIT.
