"""The colours of Cotorreando, all in one place. See docs/IDENTIDAD.md.

Everything comes from the hand-drawn parrot (assets/parrot.png): its plumage, and dark
neutrals with a slight green tint. The interface, the blob, the tray icon, the installer,
the README banner and the palette sheet all read from here; change a colour here only.

Contrast (WCAG 2.x): text at least 4.5:1, large text and controls 3:1. White text on the
parrot green is only 2.8:1, so buttons carry DARK text (ON_ACCENT).
"""

# The plumage, in the order it runs along the parrot (the blob cycles it back and forth).
MINT = "#54d7a3"
GREEN = "#22b14c"
LIME = "#b5e61d"
YELLOW = "#fff200"
ORANGE = "#ff7f27"
RED = "#ed1c24"
PLUMAGE = (MINT, GREEN, LIME, YELLOW, ORANGE, RED)

# The rest of the drawing.
OLIVE = "#629a1f"
BRICK = "#cb4426"
GARNET = "#9f1d29"
PINK = "#ffaec9"
BROWN = "#64442b"
BEAK = "#000000"

# Interface: surfaces, from back to front.
DEEP = "#0d110e"          # full-screen calibration
BACKGROUND = "#161b17"    # windows
CARD = "#1d241f"
FIELD = "#252d27"
FIELD_DISABLED = "#1f2621"
HOVER = "#222a24"
SELECTED = "#2a342d"
LIST_SELECTED = "#333e36"
GHOST_HOVER = "#242c26"
MENU = "rgba(26, 31, 27, 240)"   # BACKGROUND-like, slightly see-through

# Interface: lines.
DIVIDER = "#262e28"
MENU_SEPARATOR = "#2c352e"
CARD_BORDER = "#29322b"
WINDOW_BORDER = "#303a32"
FIELD_BORDER = "#333d36"
GHOST_BORDER = "#38433b"
SCROLLBAR = "#3a453d"
CHECKBOX_BORDER = "#6b7a6f"   # 3.1:1 on FIELD, the minimum for controls

# Interface: text.
TITLE = "#f3f6f4"
TEXT = "#e8ece9"
BODY = "#b6c2b9"
SECONDARY = "#a4b0a7"
MUTED = "#8b998e"             # notes and captions, 5.9:1 on BACKGROUND
DISABLED_TEXT = "#6d7b71"
DISABLED_BUTTON_TEXT = "#7b887e"
WHITE = "#ffffff"

# Interface: accents and states.
ACCENT = GREEN
ACCENT_HOVER = "#2cc45a"
ACCENT_PRESSED = "#1d9a42"
ON_ACCENT = "#0b1a10"         # text on ACCENT, 6.4:1
LINK = MINT
CHEER = LIME
RECORDING = ORANGE
RECORDING_TEXT = "#ffb27a"
CLOSE_HOVER = BRICK           # with WHITE text, 4.8:1
CLOSE_PRESSED = GARNET
ORB = "#aa105c3e"           # the blob's glass: deep parrot green, translucent (#AARRGGBB)
OFF = "#808086"               # blob and tray when switched off

# README badges: shields.io always writes white text, so these are darker plumage tones.
BADGE_LICENSE = "#157f35"
BADGE_WINDOWS = "#0f6b4a"
BADGE_PRIVACY = "#5a7d0e"
BADGE_VERSION = BRICK


def tokens() -> dict[str, str]:
    """Every colour above by name, for style sheets written with %(NAME)s."""
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}
