"""Every dialog of the app and the shared look of its windows and menus; app.py uses them from here."""

from .. import keyboard
from ..i18n import tr
from .base import Notice, Prompt, Window, apply_theme, ask_password, privacy_link, styled_menu
from .data import DataDialog
from .hotkey import HotkeyEdit
from .model import DownloadDialog, ModelErrorDialog, choose_model_folder, model_error_text
from .passwords import NewPassword, RecoverDialog, SetupDialog, UnlockDialog, show_recovery_code
from .settings import SettingsDialog
from .settings_pages import adapters
from .welcome import AboutDialog, LanguagesDialog, WelcomeDialog

__all__ = [
    "AboutDialog",
    "DataDialog",
    "DownloadDialog",
    "HotkeyEdit",
    "LanguagesDialog",
    "ModelErrorDialog",
    "NewPassword",
    "Notice",
    "Prompt",
    "RecoverDialog",
    "SettingsDialog",
    "SetupDialog",
    "UnlockDialog",
    "WelcomeDialog",
    "Window",
    "adapters",
    "apply_theme",
    "ask_password",
    "choose_model_folder",
    "keyboard",
    "model_error_text",
    "privacy_link",
    "show_recovery_code",
    "styled_menu",
    "tr",
]
