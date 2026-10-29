# Builds dist\cotorreando.dist\Cotorreando.exe with Nuitka (Apache-2.0).
# Standalone, not onefile: Qt DLLs stay as separate, replaceable files (LGPL).
$ErrorActionPreference = "Stop"
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
    --company-name=Alfiq --product-name=Cotorreando --product-version=0.1.0 `
    cotorreando
