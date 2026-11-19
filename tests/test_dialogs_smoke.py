"""Dialogs build and behave offscreen. They are never shown and exec() is never called."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QPushButton

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
    saved = Settings.load()  # from the temporary settings file
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
    assert widget.problem()  # mismatch
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

    monkeypatch.setattr(dialogs.settings_pages, "list_microphones", lambda: ["Test Mic"])
    monkeypatch.setattr(dialogs.settings_pages, "MODELS_DIR", isolated_data / "models")
    monkeypatch.setattr(learning, "FieldReader", lambda: None)
    monkeypatch.setattr(learning.Learner, "_watch", lambda self: None)
    learner = learning.Learner(Settings())
    learner.vault = unlocked_vault
    settings = Settings()
    return settings, dialogs.SettingsDialog(settings, FakeListener(), learner=learner)


def test_settings_dialog_builds_and_keeps_values(settings_dialog):
    settings, dialog = settings_dialog
    before = Settings()
    dialog._accept()
    assert settings == before  # nothing touched: nothing changes


def test_settings_dialog_applies_edits(settings_dialog):
    settings, dialog = settings_dialog
    dialog.keyword.setText("  Hey Loro ")
    dialog.streaming.setChecked(False)
    dialog.retention.setValue(30)
    dialog._accept()
    assert settings.keyword == "hey loro" and settings.streaming is False and settings.retention_days == 30


def test_settings_dialog_rejects_a_bad_hotkey(settings_dialog):
    settings, dialog = settings_dialog
    dialog.hotkey.setValue("not+a+hotkey+at+all")
    dialog._accept()
    assert settings.hotkey == "ctrl+win" and dialog.result() == 0


def test_settings_dialog_saves_a_recorded_hotkey(settings_dialog, monkeypatch):
    settings, dialog = settings_dialog
    snapshots = iter([set(), {0xA2, 0x5B, 0x70}, set()])  # ctrl+win+f1, then released
    monkeypatch.setattr(dialogs.keyboard, "down_keys", lambda: next(snapshots))
    dialog.hotkey.start()
    for _ in range(3):
        dialog.hotkey._tick()
    assert not dialog.hotkey.recording() and dialog.hotkey.text() == "Ctrl+Win+F1"
    dialog._accept()
    assert settings.hotkey == "ctrl+win+f1"


def test_hotkey_reset_button_restores_the_default(settings_dialog):
    settings, dialog = settings_dialog
    dialog.hotkey.setValue("ctrl+alt+a")
    reset = next(b for b in dialog.findChildren(QPushButton) if b.text() == dialogs.tr("hotkey_reset"))
    reset.click()
    assert dialog.hotkey.value() == "ctrl+win" and dialog.hotkey.text() == "Ctrl+Win"


def test_hotkey_recording_pauses_and_always_resumes_the_real_hotkey(settings_dialog, monkeypatch):
    settings, dialog = settings_dialog
    monkeypatch.setattr(dialogs.keyboard, "down_keys", lambda: set())
    edit = dialog.hotkey
    edit.start()
    assert dialogs.keyboard.hotkey_paused.is_set()
    edit.stop()
    assert not dialogs.keyboard.hotkey_paused.is_set() and not edit.recording()


@pytest.mark.parametrize("close", ["reject", "accept", "close", "hide"])
def test_closing_the_dialog_mid_recording_resumes_the_real_hotkey(settings_dialog, monkeypatch, close):
    settings, dialog = settings_dialog
    monkeypatch.setattr(dialogs.keyboard, "down_keys", lambda: set())
    dialog.show()  # close and hide only mean something on a shown window
    dialog.hotkey.start()
    assert dialogs.keyboard.hotkey_paused.is_set()
    getattr(dialog, close)()
    assert not dialogs.keyboard.hotkey_paused.is_set() and not dialog.hotkey.recording()


def test_escape_cancels_a_recording_and_keeps_the_old_hotkey(settings_dialog, monkeypatch):
    settings, dialog = settings_dialog
    snapshots = iter([set(), {0x1B}])
    monkeypatch.setattr(dialogs.keyboard, "down_keys", lambda: next(snapshots))
    dialog.hotkey.start()
    dialog.hotkey._tick()
    dialog.hotkey._tick()
    assert not dialog.hotkey.recording() and dialog.hotkey.value() == "ctrl+win"
    assert not dialogs.keyboard.hotkey_paused.is_set()


@pytest.mark.parametrize("locked, idle, closes", [(True, 0, True), (False, 10**9, True), (False, 1000, False)])
def test_data_window_closes_when_the_computer_is_left_alone(unlocked_vault, monkeypatch, locked, idle, closes):
    monkeypatch.setattr(dialogs.keyboard, "session_locked", lambda: locked)
    monkeypatch.setattr(dialogs.keyboard, "idle_ms", lambda: idle)
    from cotorreando import learning

    monkeypatch.setattr(learning, "FieldReader", lambda: None)
    monkeypatch.setattr(learning.Learner, "_watch", lambda self: None)
    learner = learning.Learner(Settings())
    learner.vault = unlocked_vault
    window = dialogs.DataDialog(learner)
    rejected = []
    window.rejected.connect(lambda: rejected.append(True))
    window._check_away()
    assert bool(rejected) == closes
    window.done(0)


def _esc(kind, auto=False):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    typ = QEvent.KeyPress if kind == "press" else QEvent.KeyRelease
    return QKeyEvent(typ, Qt.Key_Escape, Qt.NoModifier, "", auto)


def test_escape_key_event_cancels_a_recording_without_closing_the_dialog(settings_dialog, monkeypatch):
    settings, dialog = settings_dialog
    monkeypatch.setattr(dialogs.keyboard, "down_keys", lambda: set())
    dialog.show()
    dialog.hotkey.start()
    event = _esc("press")
    event.ignore()
    dialog.hotkey.keyPressEvent(event)
    assert event.isAccepted() and dialog.isVisible()
    assert not dialog.hotkey.recording() and not dialogs.keyboard.hotkey_paused.is_set()
    dialog.hide()


def test_late_escape_after_cancel_by_polling_does_not_close_the_dialog(settings_dialog, monkeypatch):
    settings, dialog = settings_dialog
    snapshots = iter([set(), {0x1B}])
    monkeypatch.setattr(dialogs.keyboard, "down_keys", lambda: next(snapshots))
    dialog.show()
    edit = dialog.hotkey
    edit.start()
    edit._tick()
    edit._tick()
    assert not edit.recording()
    for event in (_esc("press"), _esc("press", auto=True)):
        event.ignore()
        edit.keyPressEvent(event)
        assert event.isAccepted()
    release = _esc("release")
    release.ignore()
    edit.keyReleaseEvent(release)
    assert release.isAccepted() and dialog.isVisible()
    edit._cancel_at -= 0.3
    assert not edit._owns_escape(_esc("press"))
    dialog.hide()


def test_escape_without_recording_is_not_taken_by_the_field(settings_dialog):
    settings, dialog = settings_dialog
    event = _esc("press")
    event.ignore()
    dialog.hotkey.keyPressEvent(event)
    assert not event.isAccepted()
    assert not dialog.hotkey._owns_escape(_esc("press"))


def test_languages_put_the_pc_ones_first_and_tick_them(isolated_data):
    dialog = dialogs.LanguagesDialog(Settings(), detected=["fr", "en"])
    assert [dialog.list.item(i).data(Qt.UserRole) for i in (0, 1)] == ["fr", "en"]
    assert dialog.chosen() == ["fr", "en"]


@pytest.mark.parametrize("query", ["ingles", "English", "INGLÉS", "en"])
def test_languages_search_in_either_language(isolated_data, query):
    dialog = dialogs.LanguagesDialog(Settings(), detected=[])
    dialog.search.setText(query)
    visible = [dialog.list.item(i).data(Qt.UserRole) for i in range(dialog.list.count())]
    visible = [c for i, c in enumerate(visible) if not dialog.list.item(i).isHidden()]
    assert "en" in visible and "de" not in visible


def test_languages_accept_saves_and_picks_calibration(isolated_data):
    settings = Settings()
    dialog = dialogs.LanguagesDialog(settings, detected=["es", "en", "de"])
    dialog.accept()
    saved = Settings.load()
    assert saved.languages == ["es", "en", "de"] and saved.lora_language == "es"  # three: the first, not 9 minutes


def test_languages_refuse_none(isolated_data):
    settings = Settings()
    dialog = dialogs.LanguagesDialog(settings, detected=["es"])
    dialog.list.item(0).setCheckState(Qt.Unchecked)
    dialog.accept()
    assert settings.languages == []


def test_languages_click_toggles_once(isolated_data):
    dialog = dialogs.LanguagesDialog(Settings(), detected=["es"])
    item = dialog.list.item(0)
    assert not item.flags() & Qt.ItemIsUserCheckable  # else Qt flips it a second time
    dialog.list.itemClicked.emit(item)
    assert dialog.chosen() == []


def test_languages_closing_keeps_the_interface_language(isolated_data):
    settings = Settings(ui_language="en")
    dialog = dialogs.LanguagesDialog(settings, detected=["es"])
    dialog.list.item(0).setCheckState(Qt.Unchecked)
    dialog.reject()
    assert settings.languages == ["en"] and dialog.result() == QDialog.Accepted


def test_languages_closing_with_an_unlisted_interface_language_still_closes(isolated_data):
    settings = Settings(ui_language="xx")  # not one of the model's languages
    dialog = dialogs.LanguagesDialog(settings, detected=["es"])
    dialog.list.item(0).setCheckState(Qt.Unchecked)
    dialog.reject()
    assert settings.languages == ["es"] and dialog.result() == QDialog.Accepted and not dialog.warning.isVisible()


def test_languages_space_toggles(isolated_data):
    from PySide6.QtGui import QKeyEvent

    dialog = dialogs.LanguagesDialog(Settings(), detected=["es"])
    dialog.list.setCurrentRow(0)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    assert dialog.eventFilter(dialog.list, event)
    assert dialog.chosen() == []


@pytest.mark.parametrize(
    "old, codes, new",
    [("es", ["es", "de"], "es"), ("both", ["es", "en"], "both"), ("both", ["es"], "all"), ("en", ["de"], "all")],
)
def test_languages_keep_a_calibration_choice_that_fits(isolated_data, old, codes, new):
    settings = Settings(lora_language=old)
    dialog = dialogs.LanguagesDialog(settings, detected=codes)
    dialog.accept()
    assert settings.lora_language == new


def test_languages_space_ignores_a_hidden_item(isolated_data):
    from PySide6.QtGui import QKeyEvent

    dialog = dialogs.LanguagesDialog(Settings(), detected=["es"])
    dialog.list.setCurrentRow(0)
    dialog.search.setText("deutsch")
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    dialog.eventFilter(dialog.list, event)
    assert dialog.chosen() == ["es"]


def test_languages_from_the_options_cancel_without_saving(isolated_data):
    settings = Settings(languages=["de"])
    dialog = dialogs.LanguagesDialog(settings, detected=["es"], required=False)
    dialog.reject()
    assert settings.languages == ["de"] and dialog.result() == QDialog.Rejected


def test_options_show_the_spoken_languages(settings_dialog):
    settings, dialog = settings_dialog
    dialog.spoken_settings.languages = ["es", "en", "de", "fr"]
    dialog._show_languages()
    assert dialog.spoken.text() == "Español, English, Deutsch +1"


def test_options_languages_apply_only_with_the_options(settings_dialog):
    settings, dialog = settings_dialog
    before = list(settings.languages)
    dialog.spoken_settings.languages = ["de"]
    dialog.spoken_changed = True
    assert settings.languages == before  # not until the options are accepted
    dialog._accept()
    assert settings.languages == ["de"]


def test_options_keep_a_calibration_choice_made_meanwhile(settings_dialog):
    settings, dialog = settings_dialog
    settings.lora_language = "en"  # e.g. chosen in the calibration while the options were open
    dialog._accept()
    assert settings.lora_language == "en"
