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
    --include-data-files=cotorreando/lora/panels.py=cotorreando/lora/panels.py `
    --include-package=comtypes `
    --include-package=pyrage `
    --include-data-files=LICENSE=LICENSE `
    --include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md `
    --nofollow-import-to=torch,nemo,huggingface_hub `
    --company-name=Alfiq --product-name=Cotorreando --product-version=0.0.9 --file-version=0.0.9 `
    --windows-icon-from-ico=cotorreando/icon.ico `
    --assume-yes-for-downloads `
    cotorreando

# Nuitka skips the native library livekit loads at runtime (noise suppression, AEC).
$livekit = python -c "import livekit.rtc, os; print(os.path.dirname(livekit.rtc.__file__))"
$resources = New-Item -ItemType Directory -Force dist\cotorreando.dist\livekit\rtc\resources
Copy-Item "$livekit\resources\livekit_ffi.dll" $resources -Force

# Full license texts of everything bundled, which the licenses require us to ship.
python scripts\collect_licenses.py dist\cotorreando.dist\licenses
if ($LASTEXITCODE -ne 0) { throw "Could not collect the license texts" }

# Self-signed code-signing certificate, created once in the user's store and reused.
# Clients only trust it after importing dist\Cotorreando.cer (see README).
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object Subject -eq "CN=Alfiq" | Select-Object -First 1
if (-not $cert) {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=Alfiq" `
        -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5)
}
Export-Certificate -Cert $cert -FilePath dist\Cotorreando.cer | Out-Null
function Sign($path) {
    Set-AuthenticodeSignature -FilePath $path -Certificate $cert -HashAlgorithm SHA256 `
        -TimestampServer "http://timestamp.digicert.com" | Out-Null
}
Sign dist\cotorreando.dist\Cotorreando.exe

python scripts\installer_art.py dist\installer-art.bmp

# Inno Setup: winget install JRSoftware.InnoSetup
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $iscc installer.iss
Sign (Get-ChildItem dist\Cotorreando-*-setup.exe | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
