"""Update check: version comparison, daily throttle, skipped versions, silent failures. No real network."""

import io
import json
import urllib.error

import pytest

from cotorreando import updates
from cotorreando.config import Settings

DAY = updates.INTERVAL_S
NOW = 1_800_000_000.0


class FakeOpener:
    def __init__(self, tag="v9.9.9", error=None, body=None):
        self.calls, self.tag, self.error, self.body = [], tag, error, body

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        body = self.body if self.body is not None else json.dumps(
            {"tag_name": self.tag, "html_url": "https://github.com/alfiq/cotorreando/releases/tag/" + self.tag})
        return io.BytesIO(body.encode())


@pytest.fixture
def settings(isolated_data):
    return Settings()


@pytest.mark.parametrize("candidate, current, newer", [
    ("v0.0.9", "0.0.8", True),
    ("0.0.10", "0.0.9", True),     # numeric, not lexical
    ("v0.1.0", "0.0.99", True),
    ("v1.0", "1.0.0", False),
    ("v0.0.8", "0.0.8", False),
    ("v0.0.7", "0.0.8", False),
    ("v2.0.0-beta", "0.0.8", False),   # unparseable tags are ignored
    ("", "0.0.8", False),
])
def test_is_newer(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_finds_a_newer_release(settings):
    opener = FakeOpener()
    assert updates.check(settings, NOW, opener) == (
        "9.9.9", "https://github.com/alfiq/cotorreando/releases/tag/v9.9.9")
    request, timeout = opener.calls[0]
    assert request.full_url == updates.LATEST_URL
    assert request.get_header("User-agent").startswith("Cotorreando/")
    assert timeout <= 10


def test_same_version_is_not_offered(settings):
    assert updates.check(settings, NOW, FakeOpener("v" + updates.__version__)) is None


def test_once_per_day(settings):
    opener = FakeOpener()
    updates.check(settings, NOW, opener)
    assert updates.check(settings, NOW + DAY - 1, opener) is None
    assert len(opener.calls) == 1
    assert updates.check(settings, NOW + DAY, opener) is not None
    assert len(opener.calls) == 2


def test_last_check_survives_a_restart(settings):
    updates.check(settings, NOW, FakeOpener())
    assert Settings.load().update_last_check == NOW
    opener = FakeOpener()
    assert updates.check(Settings.load(), NOW + 60, opener) is None
    assert not opener.calls


def test_skipped_version_is_not_offered_but_a_later_one_is(settings):
    settings.update_skipped = "9.9.9"
    assert updates.check(settings, NOW, FakeOpener("v9.9.9")) is None
    assert updates.check(settings, NOW + DAY, FakeOpener("v9.9.10")) is not None


@pytest.mark.parametrize("opener", [
    FakeOpener(error=urllib.error.URLError("offline")),
    FakeOpener(error=TimeoutError()),
    FakeOpener(body="not json"),
    FakeOpener(body="{}"),
])
def test_failures_are_silent_and_still_throttled(settings, opener):
    assert updates.check(settings, NOW, opener) is None
    assert settings.update_last_check == NOW


def test_off_means_no_request(settings):
    settings.check_updates = False
    opener = FakeOpener()
    assert updates.check(settings, NOW, opener) is None
    assert not opener.calls
    assert not updates.due(settings, NOW)


def test_foreign_release_url_falls_back(settings):
    body = json.dumps({"tag_name": "v9.9.9", "html_url": "https://evil.example/"})
    assert updates.check(settings, NOW, FakeOpener(body=body))[1] == updates.RELEASES_URL


def test_update_state_stays_on_this_machine():
    from cotorreando.transfer import MACHINE_FIELDS
    assert {"update_last_check", "update_skipped"} <= MACHINE_FIELDS
