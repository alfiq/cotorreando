"""The blob's hover tip rotates through its phrases and ends with the hotkey."""

import pytest

pytest.importorskip("PySide6")

from cotorreando.blob import Blob
from cotorreando.i18n import set_language, tr


@pytest.fixture(autouse=True)
def spanish(qapp):
    set_language("es")
    yield
    set_language("es")


def test_tips_rotate_and_show_the_hotkey():
    blob = Blob()
    blob.set_hotkey("ctrl+win")
    tips = [blob.next_tip() for _ in range(4)]
    assert tips[0] == f"{tr('blob_tip0')} (Ctrl+Win)"
    assert len(set(tips[:3])) == 3
    assert tips[3] == tips[0]


def test_tip_without_hotkey_is_just_the_phrase():
    blob = Blob()
    assert blob.next_tip() == tr("blob_tip0")
