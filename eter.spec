# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for eter.  Build from the project root:
#
#   macOS   : pyinstaller eter.spec           -> dist/eter.app
#   Windows : pyinstaller eter.spec           -> dist/eter/eter.exe
#   Linux   : pyinstaller eter.spec           -> dist/eter/eter
#
# We rely on PyInstaller's per-module PySide6 hooks (which bundle the Qt
# Multimedia FFmpeg plugin + its libs for the imported QtMultimedia), and
# EXCLUDE the large Qt modules eter never uses (QtWebEngine ~285MB, QML/Quick3D,
# QtPdf, Designer, …). This keeps the bundle a fraction of a `collect_all` build.
import re
import sys

from PyInstaller.utils.hooks import collect_data_files


def _app_version() -> str:
    text = open("eter/__init__.py", encoding="utf-8").read()  # single source of truth
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else "0.0.0"


APP_VERSION = _app_version()
# CFBundleShortVersionString must be numeric (x.y.z); strip any pre-release suffix.
_m = re.match(r"\d+(?:\.\d+){0,2}", APP_VERSION)
SHORT_VERSION = _m.group(0) if _m else "0.0.0"

datas = collect_data_files("eter")  # bundles eter/resources/presets/*.json
hiddenimports = ["eter", "eter.__main__"]

# Heavy Qt modules we don't import — keep them out of the bundle.
excludes = [
    "tkinter",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineQuickDelegatesQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtWebSockets",
    "PySide6.QtWebChannel",
    "PySide6.QtSensors",
    "PySide6.QtLocation",
]

a = Analysis(
    ["packaging/launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="eter",
    debug=False,
    strip=True,
    upx=False,
    console=False,  # GUI app: no console window on Windows
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="eter",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="eter.app",
        icon=None,
        bundle_identifier="app.eter",
        info_plist={
            "LSUIElement": True,  # menu-bar accessory: no Dock icon
            "CFBundleName": "eter",
            "CFBundleDisplayName": "eter",
            "CFBundleShortVersionString": SHORT_VERSION,
            "CFBundleVersion": SHORT_VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
