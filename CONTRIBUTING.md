# Contribuir a Cotorreando

*Issues and pull requests are welcome in Spanish or English.*

Gracias por pasarte. Cotorreando es un proyecto pequeño y personal, así que cualquier ayuda se nota.

## Reportar un fallo

Abre un issue con la plantilla **Reportar un fallo**. Lo que más ayuda:

- Versión de Cotorreando (en *Acerca de*) y versión de Windows.
- GPU, o si va solo con CPU, y el micrófono que usas.
- Modo de escucha (micrófono abierto, pulsar para hablar, activación por voz o por palabra clave).
- Pasos para reproducirlo, qué pasó y qué esperabas.
- El registro: `%LOCALAPPDATA%\Cotorreando\cotorreando.log`. Se sobrescribe en cada arranque, así
  que cópialo justo después del fallo, antes de volver a abrir la app.

Revisa el registro antes de pegarlo y **no adjuntes grabaciones ni texto dictado** salvo que quieras
hacerlo. La privacidad es la razón de ser del proyecto; más en [docs/PRIVACIDAD.md](docs/PRIVACIDAD.md).

## Proponer una idea

Usa la plantilla **Proponer una idea**. Cuenta el problema que quieres resolver antes que la solución.
Conviene echar un vistazo a [docs/IDEAS.md](docs/IDEAS.md) y [docs/DECISIONES.md](docs/DECISIONES.md),
por si ya está pensada o descartada.

## Enviar código

- **Arreglos pequeños** (erratas, fallos evidentes): manda el pull request directamente.
- **Todo lo demás**: abre antes un issue y acordemos el enfoque. Así nadie pierde tiempo en algo que
  no encaja.

Para preparar el entorno y pasar las pruebas:

```bash
pip install -e ".[test]"
python -m pytest -q
```

Antes de enviar, comprueba que las pruebas pasan y que el código sigue el estilo del que ya existe.
Para cambios de arquitectura, [docs/DISENO.md](docs/DISENO.md) explica cómo encaja todo.
Si tocas la interfaz, los colores o las imágenes, sigue [docs/IDENTIDAD.md](docs/IDENTIDAD.md).

Al contribuir aceptas que tu aporte se publique bajo la [licencia MIT](LICENSE) del proyecto.
