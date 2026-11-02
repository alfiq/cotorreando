"""The privacy page exists in both languages and the app links to the right one."""

from pathlib import Path

from cotorreando import i18n
from cotorreando.i18n import STRINGS

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_privacy_docs_exist():
    for name in ("PRIVACIDAD.md", "PRIVACY.md"):
        assert (DOCS / name).read_text(encoding="utf-8").strip(), name


def test_privacy_link_keys_point_at_the_docs():
    assert "privacy_link" in STRINGS
    es, en = STRINGS["privacy_url"]
    assert es.startswith("https://github.com/alfiq/cotorreando/") and es.endswith("/docs/PRIVACIDAD.md")
    assert en.startswith("https://github.com/alfiq/cotorreando/") and en.endswith("/docs/PRIVACY.md")


def test_readme_links_the_privacy_page():
    readme = (DOCS.parent / "README.md").read_text(encoding="utf-8")
    assert "docs/PRIVACIDAD.md" in readme and "docs/PRIVACY.md" in readme
