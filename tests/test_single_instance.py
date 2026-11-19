import ctypes

import pytest

from cotorreando import app


class FakeKernel32:
    def __init__(self, handle, error):
        self.handle, self.error = handle, error

    def CreateMutexW(self, *_args):  # noqa: N802 - Win32 name
        ctypes.set_last_error(self.error)
        return self.handle


@pytest.mark.parametrize(
    ("handle", "error", "expected"),
    [
        (123, 0, False),  # first copy
        (123, 183, True),  # ERROR_ALREADY_EXISTS
        (None, 5, True),  # ERROR_ACCESS_DENIED: the open copy runs as administrator
    ],
)
def test_already_running(monkeypatch, handle, error, expected):
    monkeypatch.setattr(app.ctypes, "WinDLL", lambda *_a, **_k: FakeKernel32(handle, error))
    assert app.already_running() is expected
