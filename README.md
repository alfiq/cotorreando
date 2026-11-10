<p align="center">
  <img src="docs/assets/banner.png" alt="Cotorreando: dictado por voz para todo Windows" width="720">
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licencia MIT" src="https://img.shields.io/badge/licencia-MIT-157f35"></a>
  <img alt="Windows 10 y 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0f6b4a">
  <img alt="Sin nube" src="https://img.shields.io/badge/privacidad-sin%20nube-5a7d0e">
  <a href="https://github.com/alfiq/cotorreando/releases"><img alt="Versión" src="https://img.shields.io/github/v/release/alfiq/cotorreando?label=versi%C3%B3n&color=cb4426"></a>
</p>

# Cotorreando

Hablas y el texto aparece donde tengas el cursor: en el navegador, en el editor, en el chat, donde
sea. Así de fácil.

Todo pasa en tu computadora. Sin nube, sin cuentas y sin telemetría. Solo se conecta a internet
para bajar los modelos y, una vez al día, para ver si hay versión nueva. Si decides entrenar tu voz,
baja además las herramientas para hacerlo. Tu audio nunca se sube. Lo que dices es tuyo, punto.
Los detalles están en [Privacidad](docs/PRIVACIDAD.md) ([English](docs/PRIVACY.md)).

Por dentro usa [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
sobre ONNX Runtime. Entiende 25 idiomas europeos y pone solito la puntuación y las mayúsculas.

## La cotorra en pantalla

Es un círculo que flota encima de todas las ventanas y te dice en qué anda:

| Estado | Cómo se ve |
|---|---|
| Desactivado | Gris y quieto. No gasta CPU en animarse. |
| Escuchando | Verde cotorra, respira tranquila. |
| Hablando | Se deforma con tu voz y suelta ondas alrededor. |
| Escribiendo | Pasa por los colores del plumaje: menta, verde, lima, amarillo, naranja y rojo. |

Escucha y escribe al mismo tiempo. El texto sale mientras hablas, con un retraso de ≈0,8 s con GPU
o ≈1,1 s solo con CPU. Lo que ya quedó definitivo no lo toca: solo corrige las últimas palabras
que está escribiendo en ese momento, y si mueves el cursor ni eso. Puedes hablar todo lo que quieras.
El tamaño lo eliges en Opciones.

- **Arrástrala** a donde quieras. Te sigue con un resorte y se acuerda de dónde la dejaste.
- **Clic derecho**: activar o desactivar, ocultar, opciones, calibrar mi voz, acerca de y salir.
- **Bandeja del sistema**: con clic izquierdo la muestras o la ocultas; con clic derecho sale el
  mismo menú.

## Cómo te escucha

| Modo | Cómo funciona |
|---|---|
| Micrófono abierto | Escucha siempre. Cada frase, separada por pausas, se escribe. |
| Pulsar para hablar | Mantén el atajo (`Ctrl+Win` de fábrica) mientras hablas. |
| Activación por voz | Solo reacciona cuando la voz pasa del umbral de energía. |
| Activación por palabra clave | Di «oye cotorro…» y te sigue escuchando unos segundos más. |

En todos los modos menos *pulsar para hablar*, el atajo prende o apaga el dictado.

**Si tecleas, suelta la frase que estabas dictando** para no escribirte encima. Retoma con la
siguiente frase después de un ratito, 1,2 s de fábrica, y ese tiempo lo puedes cambiar.

El umbral lo puedes poner a mano o dejar que lo calcule la app. Mide el ruido de fondo mientras no
hablas y lo pone 12 dB arriba.

El audio pasa por el procesador de WebRTC, que quita ruido, cancela el eco de tus bocinas y ajusta
el volumen solo. Así no se pone a escribir lo que dice el video que tienes abierto.

## Instalar y ejecutar

Necesitas Windows 10 u 11 y Python 3.10 o más nuevo.

```bash
pip install -e .
```

```bash
cotorreando
```

La primera vez baja el modelo (~670 MB) a `%LOCALAPPDATA%\Cotorreando\models`. Mientras baja ves
el progreso, con la cotorra encendiéndose poco a poco, y un botón para cancelar.

Antes de empezar revisa que tengas espacio. Cada archivo se baja como `.part` y solo se acepta si
su tamaño y su SHA-256, que publica Hugging Face, coinciden. Si no hay conexión, se corta o el
modelo no carga, Cotorreando te avisa y te deja elegir: reintentar (sigue donde se quedó), volver a
bajarlo, usar tu propio modelo o salir.

#### Usar tu propio modelo

Ve a **Opciones → Modelo → Elegir carpeta…**, o hazlo desde el aviso de error, y elige la carpeta
de otro modelo. Tiene que ser un NVIDIA NeMo **FastConformer-TDT**, por ejemplo Parakeet TDT 0.6B
v2 o v3, exportado a ONNX con la estructura de [onnx-asr](https://github.com/istupakov/onnx-asr):

| Archivo | Contenido |
|---|---|
| `nemo128.onnx` | preprocesador: entradas `waveforms`, `waveforms_lens` → espectrograma de 128 bandas mel |
| `encoder-model.onnx` o `encoder-model.int8.onnx` | entradas `audio_signal`, `length`; 2 salidas (submuestreo ×8, 80 ms por trama) |
| `decoder_joint-model.onnx` o `.int8.onnx` | entradas `encoder_outputs`, `targets`, `target_length`, `input_states_1`, `input_states_2`; 4 salidas; la primera trae los tokens, el blank y las duraciones TDT |
| `vocab.txt` | una línea `token índice` por token, `▁` marca el inicio de palabra, el índice más alto es el blank |
| `tokenizer.json` (opcional) | tokenizador de Hugging Face, para potenciar tus palabras |

El audio va a 16 kHz. Da igual si está cuantizado a int8 o en float32; si vienen los dos, usa el
int8. No sirven modelos RNN-T o CTC (su decodificador no predice duraciones), Whisper ni otras
arquitecturas, ni un `.nemo` sin exportar.

Antes de aceptar la carpeta, abre los tres grafos en ONNX Runtime y revisa sus entradas y salidas.
Ojo: con un modelo propio no se usan las adaptaciones LoRA, porque están entrenadas sobre el modelo
de fábrica.

### Ejecutable

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

Arma `dist\cotorreando.dist\Cotorreando.exe` con Nuitka y el instalador
`dist\Cotorreando-<versión>-setup.exe` con [Inno Setup](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`). El instalador no pide permisos de administrador.

### GPU

Usa `onnxruntime-directml`, que corre en CPU y aprovecha cualquier GPU con DirectX 12 si activas
«Usar GPU» en Opciones.

## Entrenar tu voz (LoRA)

Mientras más te conoce, mejor te entiende. En el menú elige **Calibrar mi voz…**, o ve a
**Opciones → Modelo**: lees en voz alta 12 textos cortos, unos 3 minutos por idioma (español o
inglés), y con eso se entrena un adaptador LoRA para el modelo.

Para entrenar hacen falta PyTorch y NeMo (~6 GB). **No vienen incluidos**: la app te avisa y los
instala aparte, solo si tú se lo pides. Los detalles están en [docs/LORA.md](docs/LORA.md).

## Documentación

- [docs/DISENO.md](docs/DISENO.md): cómo está armado y por qué.
- [docs/LORA.md](docs/LORA.md): cómo se entrena el adaptador.
- [docs/DECISIONES.md](docs/DECISIONES.md): preguntas que resolvimos en el camino.
- [docs/IDENTIDAD.md](docs/IDENTIDAD.md): identidad visual, con logo, paleta, tipografía y tono.
- [docs/IDEAS.md](docs/IDEAS.md): ideas y pendientes.
- [docs/VERSIONES.md](docs/VERSIONES.md): cómo se numeran las versiones y cómo se publica una.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): licencias y créditos.
- [CONTRIBUTING.md](CONTRIBUTING.md): cómo reportar fallos, proponer ideas y aportar código.

## Créditos

Autor: **Alfiq** · [github.com/alfiq](https://github.com/alfiq) ·
[github.com/alfiq/cotorreando](https://github.com/alfiq/cotorreando)

La idea viene de [Handy](https://github.com/cjpais/handy) (MIT).
El modelo [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) es de NVIDIA,
bajo [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); Ilya Stupakov lo convirtió a ONNX y
lo cuantizó a int8. Los demás componentes y sus licencias están en
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

El código de Cotorreando tiene licencia MIT.

## El aviso de Windows al instalar

Cotorreando no tiene un certificado de firma de una autoridad reconocida, así que Windows
SmartScreen puede decirte «Windows protegió su PC». No te asustes: pulsa **Más información** y luego
**Ejecutar de todos modos**.

El ejecutable y el instalador van firmados con un certificado autofirmado (`CN=Alfiq`). Windows no
lo reconoce como editor de confianza, así que el aviso sale igual. No tienes que instalar ningún
certificado. Y por favor, no lo importes en «Entidades de certificación raíz de confianza»:
cualquier programa firmado con esa clave pasaría a ser de confianza en tu PC sin ningún aviso.
