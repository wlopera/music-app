# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec: Music-App (onedir, windowed, FFmpeg estatico ya incluido en PyQt6)."""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))

from PyQt6 import __file__ as _pyqt6_file  # noqa: E402
PYQT = Path(_pyqt6_file).resolve().parent
QT6 = PYQT / "Qt6"

# --- Plugins multimedia (QtMultimedia con ffmpeg estatico dentro del plugin) ----
multimedia_binaries = []
multim_dir = QT6 / "plugins" / "multimedia"
for dll in multim_dir.glob("*.dll"):
    multimedia_binaries.append((str(dll), "PyQt6/Qt6/plugins/multimedia"))

# QSS de los temas (data) y assets (icono)
theme_files = [
    (str(ROOT / "app" / "ui" / "theme.qss"), "app/ui"),
    (str(ROOT / "app" / "ui" / "theme_dark.qss"), "app/ui"),
]
if (ROOT / "assets").is_dir():
    for asset_file in (ROOT / "assets").glob("*.*"):
        theme_files.append((str(asset_file), "assets"))

# Modulos pesados y ajenos que se excluyen del bundle (reducen tamano)
EXCLUDES = [
    "tkinter",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngine",
    "PyQt6.QtQml", "PyQt6.QtQuick",
    "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets", "PyQt6.QtQuickControls2",
    "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DInput", "PyQt6.Qt3DExtras",
    "PyQt6.QtBluetooth", "PyQt6.QtDataVisualization", "PyQt6.QtDesigner",
    "PyQt6.QtLocation", "PyQt6.QtMultimediaQuick", "PyQt6.QtNetworkAuth",
    "PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtPositioning",
    "PyQt6.QtPrintSupport", "PyQt6.QtQmlModels", "PyQt6.QtQuickTest",
    "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtStateMachine",
    "PyQt6.QtSvg", "PyQt6.QtSvgWidgets", "PyQt6.QtTest", "PyQt6.QtTextToSpeech",
    "PyQt6.QtWebChannel", "PyQt6.QtWebSockets", "PyQt6.QtXml",
    "PyQt6.QtDBus", "PyQt6.QtHelp",
]

# Motor de audio opcional (librosa). En el codigo se importa de forma dinamica
# (importlib.import_module), asi que PyInstaller no lo detecta solo: hay que
# forzarlo. Los hooks de pyinstaller-hooks-contrib recogen datas/binaries.
# Nota: 'email' (email.message) es requerido por importlib.metadata y soundfile/librosa.
AUDIO_HIDDEN_IMPORTS = [
    "email", "email.message", "email.parser",
    "librosa", "soundfile", "numba", "llvmlite",
    "scipy", "scipy.signal", "scipy.fft",
    "sklearn", "sklearn.cluster", "sklearn.metrics", "sklearn.neighbors",
    "sklearn.utils", "soxr", "pooch", "lazy_loader", "joblib", "decorator",
    "msgpack", "platformdirs",
]

a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=multimedia_binaries,
    datas=theme_files,
    hiddenimports=["PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets"] + AUDIO_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Music-App",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Music-App",
)