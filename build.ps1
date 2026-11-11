# Builds the app with Nuitka (Apache-2.0) and the installer with Inno Setup.
#   dist\cotorreando.dist\Cotorreando.exe   the program
#   dist\Cotorreando-<version>-setup.exe    the installer
# Standalone, not onefile: Qt DLLs stay as separate, replaceable files (LGPL).
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
# Exact, hashed versions (requirements.lock); regenerate it as described in its header.
python -m pip install --require-hashes -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw "Could not install requirements.lock" }
python -m pip install -e . --no-deps
if ($LASTEXITCODE -ne 0) { throw "Could not install cotorreando" }
python -m nuitka `
    --standalone `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --output-dir=dist `
    --output-filename=Cotorreando.exe `
    --include-package-data=cotorreando `
    --include-data-files=cotorreando/lora/train.py=cotorreando/lora/train.py `
    --include-data-files=cotorreando/lora/panels.py=cotorreando/lora/panels.py `
    --include-package=comtypes `
    --include-package=pyrage `
    --include-data-files=LICENSE=LICENSE `
    --include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md `
    --nofollow-import-to=torch,nemo,huggingface_hub `
    --company-name=Alfiq --product-name=Cotorreando --product-version=0.1.3 --file-version=0.1.3 `
    --windows-icon-from-ico=cotorreando/icon.ico `
    --assume-yes-for-downloads `
    cotorreando
if ($LASTEXITCODE -ne 0) { throw "Nuitka failed" }

# Nuitka skips the native library livekit loads at runtime (noise suppression, AEC).
$livekit = python -c "import livekit.rtc, os; print(os.path.dirname(livekit.rtc.__file__))"
$resources = New-Item -ItemType Directory -Force dist\cotorreando.dist\livekit\rtc\resources
Copy-Item "$livekit\resources\livekit_ffi.dll" $resources -Force

# Full license texts of everything bundled, which the licenses require us to ship.
python scripts\collect_licenses.py dist\cotorreando.dist\licenses
if ($LASTEXITCODE -ne 0) { throw "Could not collect the license texts" }

# The packaged exe must load everything it needs. It is a windowed program, so PowerShell would
# not wait for it: Start-Process -Wait, and its lines come through a log file.
function Test-Build($exe) {
    $log = Join-Path $env:TEMP "cotorreando-selftest-$PID.log"
    $proc = Start-Process -FilePath (Resolve-Path $exe) -ArgumentList "--self-test", "--self-test-log", "`"$log`"" `
        -Wait -PassThru -NoNewWindow
    if (Test-Path $log) { Get-Content $log; Remove-Item $log }
    if ($proc.ExitCode -ne 0) { throw "Self-test of $exe failed (exit code $($proc.ExitCode))" }
}
Test-Build dist\cotorreando.dist\Cotorreando.exe

python scripts\installer_art.py dist\installer-art.bmp
if ($LASTEXITCODE -ne 0) { throw "Could not draw the installer art" }

# Inno Setup 6: winget install JRSoftware.InnoSetup (GitHub's windows runners already have it).
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source }
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found" }
& $iscc installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
