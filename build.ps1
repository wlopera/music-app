# Build del .exe portable de Music-App (Windows)
# Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
$PY = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

& $PY -m pip install -r requirements.txt --quiet
& $PY -m pip install pyinstaller --quiet

Write-Host "==> Empaquetando Music-App (onedir)…"
& $PY -m PyInstaller --noconfirm --clean build.spec

$dist = Join-Path $PSScriptRoot "dist\Music-App"
if (Test-Path $dist) {
    Write-Host "OK  ->  $dist"
    Write-Host "     Ejecutable: dist\Music-App\Music-App.exe"
} else {
    Write-Error "No se genero la carpeta dist\Music-App"
    exit 1
}