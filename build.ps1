# Builds the app with Nuitka (Apache-2.0) and the installer with Inno Setup.
#   dist\cotorreando.dist\Cotorreando.exe   the program
#   dist\Cotorreando-<version>-setup.exe    the installer
# Standalone, not onefile: Qt DLLs stay as separate, replaceable files (LGPL).
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
python -m pip install -e ".[build]"
python -m nuitka `
    --standalone `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --output-dir=dist `
    --output-filename=Cotorreando.exe `
    --include-package-data=cotorreando `
    --include-data-files=cotorreando/lora/train.py=cotorreando/lora/train.py `
    --include-data-files=LICENSE=LICENSE `
    --include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md `
    --nofollow-import-to=torch,nemo `
    --company-name=Alfiq --product-name=Cotorreando --product-version=0.0.1 --file-version=0.0.1 `
    --windows-icon-from-ico=cotorreando/icon.ico `
    --assume-yes-for-downloads `
    cotorreando

# Inno Setup: winget install JRSoftware.InnoSetup
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $iscc installer.iss
