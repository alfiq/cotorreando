# Guía para agentes

Cotorreando es una aplicación de dictado por voz para Windows, en Python con PySide6. El
reconocimiento corre en local (Parakeet sobre ONNX Runtime). Código en `cotorreando/`, pruebas en
`tests/`, documentación en `docs/`.

## Pruebas

```bash
pip install -e ".[test]"
python -m pytest -q
python -m ruff check .
python -m ruff format .
```

## Reglas

- Sin emojis en código, interfaz, documentación ni commits.
- Documentación en español; los textos de la interfaz van en `cotorreando/i18n.py` (español e inglés).
- Cualquier cambio de color o de aspecto sigue [docs/IDENTIDAD.md](docs/IDENTIDAD.md), y la
  actualiza si la cambia.
- Los colores salen de `cotorreando/palette.py`; no escribas hex en ningún otro archivo.
- Sin atribución a IA en commits, pull requests ni archivos.
- Si se resuelve una cuestión de diseño, se anota en [docs/DECISIONES.md](docs/DECISIONES.md).
- Lanzar una versión: [docs/VERSIONES.md](docs/VERSIONES.md). El botón de descarga del sitio
  depende de que cada Release tenga `Cotorreando-setup.exe`, que sube el workflow
  `instalador-fijo.yml`; no lo subas a mano ni cambies ese nombre.
- Arquitectura: [docs/DISENO.md](docs/DISENO.md). Contribuir: [CONTRIBUTING.md](CONTRIBUTING.md).
