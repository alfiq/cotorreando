# Contribuir a Cotorreando

*Issues and pull requests are welcome in Spanish or English.*

Gracias por pasarte. Cotorreando es un proyecto pequeño y personal, así que cualquier ayuda se nota.

## Reportar un fallo

¿Metimos la pata? Cuéntanos. Abre un issue con la plantilla **Reportar un fallo**. Lo que más
ayuda:

- Versión de Cotorreando (en *Acerca de*) y versión de Windows.
- GPU, o si va solo con CPU, y el micrófono que usas.
- Modo de escucha (micrófono abierto, pulsar para hablar, activación por voz o por palabra clave).
- Pasos para reproducirlo, qué pasó y qué esperabas.
- El registro: `%LOCALAPPDATA%\Cotorreando\cotorreando.log`. Se sobrescribe en cada arranque, así
  que cópialo justo después del fallo, antes de volver a abrir la app.

Revisa el registro antes de pegarlo y **no adjuntes grabaciones ni texto dictado**, a menos que
de verdad quieras. La privacidad es la razón de ser del proyecto. Más en
[docs/PRIVACIDAD.md](docs/PRIVACIDAD.md).

Si el problema es una vulnerabilidad de seguridad, no abras un issue: repórtala en privado como se
indica en [SECURITY.md](SECURITY.md).

## Proponer una idea

Usa la plantilla **Proponer una idea**. Cuéntanos primero el problema y después la solución.
Échale un ojo a [docs/IDEAS.md](docs/IDEAS.md) y a [docs/DECISIONES.md](docs/DECISIONES.md), por
si ya la pensamos o ya la descartamos.

## Enviar código

- **Arreglos pequeños** (erratas, fallos obvios): manda el pull request directo.
- **Todo lo demás**: abre primero un issue y nos ponemos de acuerdo en el enfoque. Así nadie pierde
  tiempo en algo que no encaja.

Para preparar el entorno y correr las pruebas:

```bash
pip install -e ".[test]"
python -m pytest -q
python -m ruff check .
```

Antes de enviar, revisa que las pruebas y `ruff check .` pasen y que tu código se parezca al que ya está.
Si vas a mover la arquitectura, [docs/DISENO.md](docs/DISENO.md) explica cómo encaja todo.
Si tocas la interfaz, los colores o las imágenes, sigue [docs/IDENTIDAD.md](docs/IDENTIDAD.md).

Al contribuir aceptas que tu aporte se publique bajo la [licencia MIT](LICENSE) del proyecto.

Participar en el proyecto implica seguir el [Código de conducta](CODE_OF_CONDUCT.md).
