$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python environment.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install dependencies.' }
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --distpath dist BilingualFontTool.spec
if ($LASTEXITCODE -ne 0) { throw 'Failed to build executable.' }
Write-Host 'Built: dist\BilingualFontTool.exe'
