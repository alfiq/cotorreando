"""scripts/bump_version.py on a copy of the versioned files: every place changes, nothing else."""

import datetime
import importlib.util
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = ["pyproject.toml", "cotorreando/__init__.py", "installer.iss", "build.ps1", "CHANGELOG.md"]

spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts" / "bump_version.py")
bump_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump_version)


@pytest.fixture
def copy(tmp_path):
    for name in FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, tmp_path / name)
    return tmp_path


def test_updates_every_place(copy):
    bump_version.bump("9.8.7", copy, datetime.date(2030, 1, 2))
    for name, pattern in bump_version.PLACES:
        assert re.search(pattern, (copy / name).read_text(encoding="utf-8"), re.M).group(1) == "9.8.7"
    changelog = (copy / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(r"^## 9\.8\.7 — 2030-01-02$", changelog, re.M)
    assert changelog.index("## 9.8.7") < changelog.index("## 0.0.")


def test_keeps_line_endings_and_other_lines(copy):
    before = {n: (copy / n).read_bytes() for n in FILES}
    bump_version.bump("9.8.7", copy)
    for name in FILES[:4]:
        after = (copy / name).read_bytes()
        assert after.count(b"\r\n") == before[name].count(b"\r\n")
        assert len(after.splitlines()) == len(before[name].splitlines())


def test_twice_adds_one_heading(copy):
    bump_version.bump("9.8.7", copy)
    bump_version.bump("9.8.7", copy)
    assert (copy / "CHANGELOG.md").read_text(encoding="utf-8").count("## 9.8.7") == 1


def test_rejects_non_semver(copy):
    with pytest.raises(SystemExit):
        bump_version.bump("1.2", copy)
