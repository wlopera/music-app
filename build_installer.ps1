# Script para compilar el instalador final con Inno Setup
# Uso: powershell -ExecutionPolicy Bypass -File build_installer.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Compilador de Instalador Music-App     " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Verificar si existe la carpeta compilada dist\Music-App
$distApp = Join-Path $PSScriptRoot "dist\Music-App\Music-App.exe"
if (-not (Test-Path $distApp)) {
    Write-Host "[1/2] Compilando la aplicacion primero con build.ps1..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build.ps1")
} else {
    Write-Host "[1/2] Ejecutable existente encontrado en dist\Music-App\Music-App.exe" -ForegroundColor Green
}

# 2. Localizar el compilador de Inno Setup (ISCC.exe)
$isccCandidates = @(
    "ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
)

$isccPath = $null
foreach ($candidate in $isccCandidates) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $isccPath = $candidate
        break
    }
    if (Test-Path $candidate) {
        $isccPath = $candidate
        break
    }
}

if (-not $isccPath) {
    Write-Host ""
    Write-Host "AVISO: No se encontro Inno Setup (ISCC.exe) instalado en el sistema." -ForegroundColor Yellow
    Write-Host "Para compilar el instalador, puedes instalar Inno Setup 6:" -ForegroundColor White
    Write-Host "  * Opcion A (winget):  winget install JRSoftware.InnoSetup" -ForegroundColor Cyan
    Write-Host "  * Opcion B (web):     https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "El script 'setup.iss' ya esta listo en la raiz del proyecto." -ForegroundColor Green
    exit 0
}

Write-Host "[2/2] Compilando instalador con Inno Setup ($isccPath)..." -ForegroundColor Yellow
$issPath = Join-Path $PSScriptRoot "setup.iss"
& $isccPath $issPath

$installerOut = Join-Path $PSScriptRoot "dist\installer\MusicApp-Setup.exe"
if (Test-Path $installerOut) {
    Write-Host ""
    Write-Host "EXITO! Instalador generado en:" -ForegroundColor Green
    Write-Host "   $installerOut" -ForegroundColor White
} else {
    Write-Host "Verifica la salida de Inno Setup." -ForegroundColor Yellow
}
