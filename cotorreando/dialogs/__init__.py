"""Settings and About dialogs, plus the shared look of menus and windows."""

from .. import keyboard
from ..i18n import tr
from .base import Notice, Prompt, Window, apply_theme, ask_password, privacy_link, styled_menu
from .data import DataDialog
from .model import DownloadDialog, ModelErrorDialog, choose_model_folder, model_error_text
from .passwords import NewPassword, RecoverDialog, SetupDialog, UnlockDialog, show_recovery_code
from .settings import HotkeyEdit, SettingsDialog, adapters
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
