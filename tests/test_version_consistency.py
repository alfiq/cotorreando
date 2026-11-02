"""The version is written in several places; releasing with one of them stale is easy to do."""

import re
from pathlib import Path

import pytest

import cotorreando

ROOT = Path(cotorreando.__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def version():
    return cotorreando.__version__


def test_version_is_semver(version):
    assert SEMVER.match(version)


def test_pyproject_matches(version):
    assert re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.M).group(1) == version


def test_installer_matches(version):
    iss = read("installer.iss")
    assert re.search(r'^#define AppVersion "([^"]+)"', iss, re.M).group(1) == version
    assert re.search(r"^AppVersion=\{#AppVersion\}\s*$", iss, re.M)
    assert re.search(r"^OutputBaseFilename=.*\{#AppVersion\}.*$", iss, re.M)


def test_build_script_matches(version):
    build = read("build.ps1")
    assert re.search(r"--product-version=(\S+)", build).group(1) == version
    assert re.search(r"--file-version=(\S+)", build).group(1) == version


def test_changelog_has_a_heading_for_it(version):
    assert re.search(rf"^## {re.escape(version)}\b", read("CHANGELOG.md"), re.M)
