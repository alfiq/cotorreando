"""Translation table: every key the code asks for exists, in both languages, with the same placeholders."""

import ast
import string
from pathlib import Path

import pytest

from cotorreando import i18n
from cotorreando.i18n import STRINGS, set_language, tr

PACKAGE = Path(i18n.__file__).parent


@pytest.fixture(autouse=True)
def restore_language():
    before = i18n._lang
    yield
    i18n._lang = before


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_entries_are_pairs_of_non_empty_strings():
    for key, value in STRINGS.items():
        assert isinstance(value, tuple) and len(value) == 2, key
        assert all(isinstance(t, str) and t.strip() for t in value), key


def test_placeholders_match_between_languages():
    for key, (es, en) in STRINGS.items():
        assert placeholders(es) == placeholders(en), key


def test_missing_key_returns_the_key():
    assert tr("no_such_key_at_all") == "no_such_key_at_all"


def test_set_language_switches_and_defaults_to_spanish():
    set_language("en")
    assert tr("quit") == "Quit"
    set_language("es")
    assert tr("quit") == "Salir"
    set_language("fr")          # anything but "en" is Spanish
    assert tr("quit") == "Salir"


def test_format_arguments():
    set_language("en")
    assert tr("downloading", pct=42) == "Downloading model… 42%"
    set_language("es")
    assert tr("downloading", pct=7) == "Descargando modelo… 7%"


def literal_keys() -> dict[str, list[str]]:
    """Every ``tr("literal")`` call in the package, with where it is."""
    found: dict[str, list[str]] = {}
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, []).append(f"{path.name}:{node.lineno}")
    return found


def test_every_literal_key_exists():
    used = literal_keys()
    assert used, "the scan found no tr() calls: the test itself is broken"
    missing = {key: where for key, where in used.items() if key not in STRINGS}
    assert not missing, f"keys used but not defined: {missing}"


def test_dynamic_key_prefixes_have_entries():
    # tr("kind_" + meta["kind"]) in the data dialog: both kinds add_record is called with need a label
    kinds = [key for key in STRINGS if key.startswith("kind_")]
    assert {"kind_correction", "kind_panel"} <= set(kinds)


@pytest.mark.parametrize("problem", ["password_short", "password_weak"])
def test_password_problem_keys_exist(problem):
    assert problem in STRINGS


def test_welcome_keys_exist():
    for key in ("welcome_title", "welcome_text", "welcome_learning", "welcome_accept", "welcome_exit"):
        assert key in STRINGS
    for key in ("password_mismatch", "password_new_hint", "password_again", "password_generate"):
        assert key in STRINGS
