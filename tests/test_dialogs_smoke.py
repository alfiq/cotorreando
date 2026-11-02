"""Dialogs build and behave offscreen. They are never shown and exec() is never called."""

import pytest

pytest.importorskip("PySide6")

from cotorreando import config, dialogs
from cotorreando.config import Settings
from cotorreando.i18n import set_language


@pytest.fixture(autouse=True)
def spanish(qapp):
    set_language("es")
    yield
    set_language("es")


@pytest.mark.parametrize("lang,title", [("es", "Bienvenido a Cotorreando"), ("en", "Welcome to Cotorreando")])
def test_welcome_builds_in_both_languages(isolated_data, lang, title):
    set_language(lang)
    dialog = dialogs.WelcomeDialog(Settings())
    assert dialog.windowTitle() == title


@pytest.mark.parametrize("learning", [True, False])
def test_welcome_checkbox_mirrors_learning(isolated_data, learning):
    dialog = dialogs.WelcomeDialog(Settings(learning=learning))
    assert dialog.learning.isChecked() is learning


@pytest.mark.parametrize("checked", [True, False])
def test_welcome_accept_saves(isolated_data, checked):
    settings = Settings(learning=True)
    dialog = dialogs.WelcomeDialog(settings)
    dialog.learning.setChecked(checked)
    dialog.accept()
    assert settings.welcome_accepted is True and settings.learning is checked
    saved = Settings.load()                     # from the temporary settings file
    assert saved.welcome_accepted is True and saved.learning is checked
    assert config.CONFIG_FILE.is_relative_to(isolated_data)


def test_welcome_reject_writes_nothing(isolated_data):
    settings = Settings()
    dialog = dialogs.WelcomeDialog(settings)
    dialog.learning.setChecked(False)
    dialog.reject()
    assert settings.welcome_accepted is False and settings.learning is True
    assert not config.CONFIG_FILE.exists()


def test_closing_with_the_title_bar_cross_counts_as_reject(isolated_data):
    settings = Settings()
    dialogs.WelcomeDialog(settings).close()
    assert settings.welcome_accepted is False and not config.CONFIG_FILE.exists()


def test_about_builds():
    dialog = dialogs.AboutDialog()
    assert dialog.windowTitle()


def test_prompt_builds_with_and_without_password():
    plain = dialogs.Prompt(None, "hello")
    assert plain.field.isHidden()
    secret = dialogs.Prompt(None, "hello", ok="OK", cancel=False, password=True)
    secret.field.setText("x")
    assert not secret.field.isHidden()


def test_new_password_validation():
    widget = dialogs.NewPassword()
    widget.first.setText("a long enough one")
    widget.second.setText("different")
    assert widget.problem()                         # mismatch
    widget.second.setText("a long enough one")
    assert widget.problem() is None and widget.password() == "a long enough one"
    widget.first.setText("short")
    widget.second.setText("short")
    assert widget.problem()


def test_new_password_generate_fills_both_fields():
    widget = dialogs.NewPassword()
    widget._generate()
    assert widget.first.text() == widget.second.text() and len(widget.first.text()) >= 20
    assert widget.problem() is None


# -- settings ---------------------------------------------------------------------------------

class FakeListener:
    last_level = -42.0
    threshold_db = -50.0

    def calibrate(self):
        pass


@pytest.fixture
def settings_dialog(isolated_data, monkeypatch, unlocked_vault):
    from cotorreando import learning
    monkeypatch.setattr(dialogs, "list_microphones", lambda: ["Test Mic"])
    monkeypatch.setattr(dialogs, "MODELS_DIR", isolated_data / "models")
    monkeypatch.setattr(learning, "FieldReader", lambda: None)
    monkeypatch.setattr(learning.Learner, "_watch", lambda self: None)
    learner = learning.Learner(Settings())
    learner.vault = unlocked_vault
    settings = Settings()
    return settings, dialogs.SettingsDialog(settings, FakeListener(), learner)


def test_settings_dialog_builds_and_keeps_values(settings_dialog):
    settings, dialog = settings_dialog
    before = Settings()
    dialog._accept()
    assert settings == before                    # nothing touched: nothing changes


def test_settings_dialog_applies_edits(settings_dialog):
    settings, dialog = settings_dialog
    dialog.keyword.setText("  Hey Loro ")
    dialog.streaming.setChecked(False)
    dialog.retention.setValue(30)
    dialog._accept()
    assert settings.keyword == "hey loro" and settings.streaming is False and settings.retention_days == 30


def test_settings_dialog_rejects_a_bad_hotkey(settings_dialog):
    settings, dialog = settings_dialog
    dialog.hotkey.setText("not+a+hotkey+at+all")
    dialog._accept()
    assert settings.hotkey == "ctrl+win" and dialog.result() == 0
