# Regenerates the hashed locks of the training environment from cotorreando/lora/requirements.in.
$ErrorActionPreference = "Stop"
$lora = Join-Path $PSScriptRoot "..\cotorreando\lora"
$uv = Join-Path $env:LOCALAPPDATA "Cotorreando\tools\uv.exe"
if (-not (Test-Path $uv)) { $uv = "uv" }
foreach ($v in "cu128", "cpu") {
    $override = New-TemporaryFile
    "torch==2.11.0+$v`ntorchaudio==2.11.0+$v" | Set-Content $override -Encoding utf8
    & $uv pip compile "$lora\requirements.in" --python-version 3.12 `
        --python-platform x86_64-pc-windows-msvc --generate-hashes `
        --extra-index-url "https://download.pytorch.org/whl/$v" --index-strategy unsafe-best-match `
        --override $override --no-header -q -o "$lora\requirements-$v.txt"
    Remove-Item $override
}
