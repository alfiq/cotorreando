"""Ask GitHub, at most once a day, whether a newer release exists. Never downloads anything.

The request is a plain GET of the public "latest release" endpoint: no cookies, no id,
nothing about this install beyond what any web request carries (IP and User-Agent).
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request

from . import __version__

log = logging.getLogger(__name__)

LATEST_URL = "https://api.github.com/repos/alfiq/cotorreando/releases/latest"
RELEASES_URL = "https://github.com/alfiq/cotorreando/releases/latest"
INTERVAL_S = 24 * 3600
TIMEOUT_S = 5


def parse(version: str) -> tuple[int, ...] | None:
    """'v1.2.3' -> (1, 2, 3); None for anything that is not plain dotted numbers."""
    text = version.strip().lstrip("vV")
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        return None
    parts = [int(p) for p in text.split(".")]
    while len(parts) > 1 and parts[-1] == 0:  # 1.0 == 1.0.0
        parts.pop()
    return tuple(parts)


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, old = parse(candidate), parse(current)
    return new is not None and old is not None and new > old


def due(settings, now: float | None = None) -> bool:
    if not settings.check_updates:
        return False
    now = time.time() if now is None else now
    last = settings.update_last_check
    return not (0 <= now - last < INTERVAL_S)  # a clock set back counts as due


def fetch_latest(opener=urllib.request.urlopen) -> tuple[str, str]:
    """(tag without the 'v', release page URL). Raises on any network or format problem."""
    request = urllib.request.Request(
        LATEST_URL, headers={"User-Agent": f"Cotorreando/{__version__}", "Accept": "application/vnd.github+json"}
    )
    with opener(request, timeout=TIMEOUT_S) as response:
        data = json.loads(response.read().decode("utf-8"))
    tag = str(data["tag_name"]).strip().lstrip("vV")
    url = data.get("html_url") or RELEASES_URL
    if not str(url).startswith("https://github.com/"):
        url = RELEASES_URL
    return tag, url


def check(settings, now: float | None = None, opener=urllib.request.urlopen) -> tuple[str, str] | None:
    """(version, page URL) when a newer, not-skipped release exists; None otherwise or on failure."""
    if not due(settings, now):
        return None
    settings.update_last_check = time.time() if now is None else now
    settings.save()  # a failed check also waits a day, so an offline PC is not nagged
    try:
        tag, url = fetch_latest(opener)
    except Exception as err:  # noqa: BLE001 - offline, rate limited, malformed: all the same to us
        log.info("Update check failed: %s", err)
        return None
    if not is_newer(tag) or tag == settings.update_skipped:
        return None
    log.info("Version %s is available", tag)
    return tag, url
