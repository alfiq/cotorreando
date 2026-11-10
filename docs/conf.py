"""Configuración de Sphinx para el sitio de documentación.

La portada (index.md) y la hoja de estilos se generan al compilar, a partir del README y de la
paleta de docs/IDENTIDAD.md, para no mantener copias en el repositorio.

    pip install sphinx pydata-sphinx-theme myst-parser
    sphinx-build docs _site
"""

import re
import tempfile
from pathlib import Path

DOCS = Path(__file__).parent
ROOT = DOCS.parent

project = "Cotorreando"
author = "Alfiq"
language = "es"

extensions = ["myst_parser"]
source_suffix = {".md": "markdown"}
myst_heading_anchors = 3
exclude_patterns = ["_build"]
suppress_warnings = ["myst.header"]

html_theme = "pydata_sphinx_theme"
html_title = "Cotorreando"
html_logo = str(ROOT / "cotorreando" / "assets" / "parrot.png")
html_favicon = html_logo
html_show_sourcelink = False
html_context = {"default_mode": "dark"}
html_theme_options = {
    "github_url": "https://github.com/alfiq/cotorreando",
    "logo": {"text": "Cotorreando"},
    "navbar_align": "left",
    "show_toc_level": 2,
    "footer_start": ["copyright"],
    "footer_end": [],
}

# Colores de docs/IDENTIDAD.md. En modo claro el verde cotorra y la menta no llegan a 4,5:1 sobre
# blanco, así que se usan las variantes oscuras de las insignias.
CSS = """
html {
  --pst-font-family-base: "Segoe UI", system-ui, sans-serif;
  --pst-font-family-heading: "Segoe UI", system-ui, sans-serif;
  --pst-font-family-monospace: Consolas, monospace;
}
html[data-theme="dark"] {
  --pst-color-background: #161b17;
  --pst-color-on-background: #1d241f;
  --pst-color-surface: #252d27;
  --pst-color-on-surface: #e8ece9;
  --pst-color-text-base: #e8ece9;
  --pst-color-text-muted: #a4b0a7;
  --pst-color-heading-color: #f3f6f4;
  --pst-color-border: #303a32;
  --pst-color-primary: #22b14c;
  --pst-color-primary-bg: #1d9a42;
  --pst-color-secondary: #54d7a3;
  --pst-color-accent: #b5e61d;
  --pst-color-link: #54d7a3;
  --pst-color-link-hover: #b5e61d;
  --pst-color-inline-code: #b5e61d;
  --pst-color-target: #2a342d;
}
html[data-theme="light"] {
  --pst-color-primary: #157f35;
  --pst-color-secondary: #0f6b4a;
  --pst-color-accent: #5a7d0e;
  --pst-color-link: #0f6b4a;
  --pst-color-link-hover: #157f35;
  --pst-color-inline-code: #5a7d0e;
}
.navbar-brand img, link[rel="icon"] { image-rendering: pixelated; }
h1, h2, h3, h4, .navbar-brand { font-weight: 600; }
.descarga {
  margin: 1.5rem 0 2rem; padding: 1.25rem 1.5rem; border-radius: 12px;
  border: 1px solid var(--pst-color-border); background: var(--pst-color-surface);
}
.descarga p { margin: 0 0 .75rem; }
.descarga .boton {
  display: inline-block; padding: .6rem 1.4rem; border-radius: 8px; font-weight: 600;
  background: var(--pst-color-primary); color: var(--pst-color-background); text-decoration: none;
}
.descarga .boton:hover { background: var(--pst-color-primary-bg); color: var(--pst-color-background); }
.descarga .resto { margin: .75rem 0 0; color: var(--pst-color-text-muted); }
"""

_static = Path(tempfile.mkdtemp(prefix="cotorreando-docs-"))
(_static / "cotorra.css").write_text(CSS, encoding="utf-8")
html_static_path = [str(_static)]
html_css_files = ["cotorra.css"]


DESCARGA = """
<div class="descarga">
<p>¿Vienes por la descarga? Aquí está, cotorro.</p>
<a class="boton" href="https://github.com/alfiq/cotorreando/releases/latest/download/Cotorreando-setup.exe">Descargar Cotorreando para Windows</a>
<p class="resto">¡Luego me cuentas cómo te fue! Y ahora, para los demás:</p>
</div>
"""


def _portada():
    """index.md a partir del README: quita las insignias y ajusta las rutas a docs/."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cuerpo = readme[readme.index("# Cotorreando"):]
    cuerpo = re.sub(r"\]\(docs/", "](", cuerpo)
    cuerpo = re.sub(r"\]\((?!https?://|#)([^)]+)\)",
                    lambda m: m.group(0) if (DOCS / m.group(1).split("#")[0]).exists()
                    else f"](https://github.com/alfiq/cotorreando/blob/main/{m.group(1)})",
                    cuerpo)
    indice = "\n".join(p.stem for p in sorted(DOCS.glob("*.md")) if p.stem != "index")
    return ("![Cotorreando](assets/banner.png)\n" + DESCARGA + "\n" + cuerpo
            + "\n\n```{toctree}\n:hidden:\n:maxdepth: 1\n\n" + indice + "\n```\n")


(DOCS / "index.md").write_text(_portada(), encoding="utf-8")
