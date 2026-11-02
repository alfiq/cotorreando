"""Download and model-problem dialogs build and react offscreen; nothing is shown or downloaded."""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from cotorreando import dialogs, model_store
from cotorreando.config import Settings
from cotorreando.i18n import set_language


@pytest.fixture(autouse=True)
def spanish(qapp):
    set_language("es")
    yield
    set_language("es")


def test_progress_lights_the_mosaic(isolated_data):
    dialog = dialogs.DownloadDialog(lambda progress, cancelled: None)
    dialog._show(0, 1000)
    dialog._show(500 * 1024 ** 2, 1000 * 1024 ** 2)
    assert dialog.mosaic.progress == pytest.approx(0.5)
    assert "500 MB" in dialog.label.text() and "50%" in dialog.label.text()


def test_failure_is_kept_for_the_caller(isolated_data):
    dialog = dialogs.DownloadDialog(lambda progress, cancelled: None)
    error = model_store.NoConnection("offline")
    dialog._running = True
    dialog._finish(error)
    assert dialog.error is error and dialog.result() == 0
    assert "conexión" in dialogs.model_error_text(error)


def test_cancel_while_running_asks_the_worker_to_stop(isolated_data):
    dialog = dialogs.DownloadDialog(lambda progress, cancelled: None)
    dialog._running = True
    dialog.reject()
    assert dialog._cancel.is_set()
    assert not dialog.cancel.isEnabled()


def test_worker_turns_any_exception_into_a_model_error(isolated_data):
    def broken(progress, cancelled):
        raise RuntimeError("boom")
    dialog = dialogs.DownloadDialog(broken)
    got = []
    dialog._ended.disconnect()
    dialog._ended.connect(got.append)
    dialog._run()
    assert isinstance(got[0], model_store.DownloadFailed)


def test_error_dialog_reports_the_choice(isolated_data):
    dialog = dialogs.ModelErrorDialog("x", [("own", "Mine"), ("retry", "Retry")])
    assert dialog.choice == "quit"
    dialog._pick("retry")
    assert dialog.choice == "retry"


def test_every_model_error_has_text_in_both_languages():
    errors = [model_store.NoConnection("d"), model_store.DownloadFailed("d"),
              model_store.NotEnoughSpace(10, 5), model_store.Cancelled(),
              model_store.InvalidModel("model_missing", files="vocab.txt")]
    for lang in ("es", "en"):
        set_language(lang)
        for err in errors:
            assert dialogs.model_error_text(err) != err.key


def test_settings_model_page_keeps_the_custom_folder(isolated_data):
    settings = Settings(custom_model="C:/models/mine")
    learner = SimpleNamespace(vault=SimpleNamespace(ready=False))
    dialog = dialogs.SettingsDialog(settings, learner=learner)
    assert dialog.model_label.text() == "C:/models/mine"
    dialog._set_model("")
    dialog._accept()
    assert settings.custom_model == ""
