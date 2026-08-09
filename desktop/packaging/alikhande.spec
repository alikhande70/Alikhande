# PyInstaller spec — builds AlikhandeScanner.exe
#
# Run from the `desktop/` directory on Windows:
#
#     pip install -r requirements.txt pyinstaller
#     pyinstaller packaging/alikhande.spec --noconfirm
#
# Produces dist/AlikhandeScanner/AlikhandeScanner.exe.
#
# A one-folder build rather than --onefile, deliberately. A one-file build
# unpacks itself into %TEMP% on every launch, which costs several seconds of
# start-up, trips some corporate antivirus heuristics, and makes the running
# executable's own path meaningless. None of that is worth the tidier icon.

import sys
from pathlib import Path

BLOCK_CIPHER = None
ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "alikhande" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Imported lazily inside a try/except, so the dependency graph does not
        # see it. On a non-Windows build machine it is genuinely absent, which
        # is why the failure has to stay soft.
        "MetaTrader5",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt ships a great deal this application never touches. Excluding it is
    # worth roughly 40 MB and, more usefully, removes whole subsystems that
    # would otherwise need justifying to a security review.
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtNetwork",
        "PySide6.QtBluetooth",
        "PySide6.QtPositioning",
        "PySide6.QtSql",
        "PySide6.QtTest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=BLOCK_CIPHER,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AlikhandeScanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX compression is a reliable way to get flagged as malware
    console=False,  # a GUI application; the CLI subcommands still work via -m
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AlikhandeScanner",
)
