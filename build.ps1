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
    # Config portable junto al .exe: si el build la borro, se repone la plantilla
    # con campos vacios para que el usuario configure sus datos desde ⚙ Config.
    $cfg = Join-Path $dist "config.json"
    if (-not (Test-Path $cfg)) {
        $tmpl = Join-Path $PSScriptRoot "config_template.json"
        if (Test-Path $tmpl) {
            Copy-Item -LiteralPath $tmpl -Destination $cfg
            Write-Host "config.json repuesto (plantilla vacia) junto al .exe"
        }
    }
    Write-Host "OK  ->  $dist"
    Write-Host "     Ejecutable: dist\Music-App\Music-App.exe"
} else {
    Write-Error "No se genero la carpeta dist\Music-App"
    exit 1
}