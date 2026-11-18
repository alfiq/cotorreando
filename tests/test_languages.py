import pytest

from cotorreando.languages import LANGUAGES, calibration_languages, matches
from cotorreando.lora import job


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_every_language_has_calibration_panels(code):
    panels = job.read_panels(code)
    assert len(panels) >= 10
    assert all(140 <= len(p) <= 215 for p in panels)  # 15-20 seconds, like the hand-written ones


def test_calibration_languages():
    assert calibration_languages("all", ["de", "fr"]) == ["de", "fr"]
    assert calibration_languages("de", ["de", "fr"]) == ["de"]
    assert calibration_languages("both", ["es", "en", "de"]) == ["es", "en"]
    assert calibration_languages("both", ["de"]) == ["de"]  # neither chosen any more: all
    assert calibration_languages("all", []) == ["es"]
    assert calibration_languages("de", ["fr"]) == ["fr"]  # e.g. from an imported profile
    assert calibration_languages("de", ["fr", "it", "pt"]) == ["fr"]  # many: the first, not 9 minutes
    assert calibration_languages("all", ["fr", "it", "pt"]) == ["fr", "it", "pt"]


def test_matches_ignores_accents_and_case():
    assert matches("de", "aleman") and matches("de", "GERMAN") and matches("de", "Deutsch")
    assert not matches("de", "frances")
