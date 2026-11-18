"""The languages Parakeet TDT 0.6B v3 understands, and which of them this PC already uses."""

from __future__ import annotations

import ctypes
import logging
import sys
import unicodedata

log = logging.getLogger(__name__)

# code: (own name, name in Spanish, name in English). The model card lists these 25.
LANGUAGES = {
    "bg": ("Български", "Búlgaro", "Bulgarian"),
    "cs": ("Čeština", "Checo", "Czech"),
    "da": ("Dansk", "Danés", "Danish"),
    "de": ("Deutsch", "Alemán", "German"),
    "el": ("Ελληνικά", "Griego", "Greek"),
    "en": ("English", "Inglés", "English"),
    "es": ("Español", "Español", "Spanish"),
    "et": ("Eesti", "Estonio", "Estonian"),
    "fi": ("Suomi", "Finés", "Finnish"),
    "fr": ("Français", "Francés", "French"),
    "hr": ("Hrvatski", "Croata", "Croatian"),
    "hu": ("Magyar", "Húngaro", "Hungarian"),
    "it": ("Italiano", "Italiano", "Italian"),
    "lt": ("Lietuvių", "Lituano", "Lithuanian"),
    "lv": ("Latviešu", "Letón", "Latvian"),
    "mt": ("Malti", "Maltés", "Maltese"),
    "nl": ("Nederlands", "Neerlandés", "Dutch"),
    "pl": ("Polski", "Polaco", "Polish"),
    "pt": ("Português", "Portugués", "Portuguese"),
    "ro": ("Română", "Rumano", "Romanian"),
    "ru": ("Русский", "Ruso", "Russian"),
    "sk": ("Slovenčina", "Eslovaco", "Slovak"),
    "sl": ("Slovenščina", "Esloveno", "Slovenian"),
    "sv": ("Svenska", "Sueco", "Swedish"),
    "uk": ("Українська", "Ucraniano", "Ukrainian"),
}

# Every language has calibration texts in lora/datasets; these two are hand-written, and only these
# two get the practice panels that Qwen writes.
HAND_WRITTEN = ("es", "en")


def label(code: str, ui_language: str) -> str:
    """'Deutsch (Alemán)': its own name, and the one the user reads if it differs."""
    own, es, en = LANGUAGES[code]
    other = es if ui_language == "es" else en
    return own if other == own else f"{own} ({other})"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def matches(code: str, query: str) -> bool:
    """Whether ``query`` is part of any of its names or its code, ignoring case and accents."""
    query = _fold(query.strip())
    return not query or any(query in _fold(name) for name in (code, *LANGUAGES[code]))


def _locale_code(lcid: int) -> str:
    buffer = ctypes.create_unicode_buffer(85)
    if not ctypes.windll.kernel32.LCIDToLocaleName(lcid, buffer, 85, 0):  # type: ignore[attr-defined]
        return ""
    return buffer.value.split("-")[0].lower()


def system_languages() -> list[str]:
    """Known languages of the keyboards and the regional format on this PC, in that order."""
    if sys.platform != "win32":
        return []
    found: list[str] = []
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        count = user32.GetKeyboardLayoutList(0, None)
        layouts = (ctypes.c_void_p * count)()
        user32.GetKeyboardLayoutList(count, layouts)
        lcids = [(layout or 0) & 0xFFFF for layout in layouts]
        lcids.append(ctypes.windll.kernel32.GetUserDefaultLCID())  # type: ignore[attr-defined]
        for lcid in lcids:
            code = _locale_code(lcid)
            if code in LANGUAGES and code not in found:
                found.append(code)
    except (OSError, AttributeError):
        log.exception("Could not read the system languages")
    return found


def calibration_languages(choice: str, chosen: list[str]) -> list[str]:
    """What a calibration reads: one language, every chosen one ("all"), or Spanish and English
    ("both", from before languages were asked)."""
    if choice == "both" and {"es", "en"} <= set(chosen):
        return ["es", "en"]
    if choice in LANGUAGES and (choice in chosen or not chosen):
        return [choice]
    chosen = [code for code in chosen if code in LANGUAGES] or ["es"]
    if choice == "all" or len(chosen) <= 2:
        return chosen
    return chosen[:1]  # a choice that no longer fits, with many languages: the first, as a new one
