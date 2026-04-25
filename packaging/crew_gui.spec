# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Crew.app / Crew.exe / Crew.AppImage.

Build from repo root:

    pip install -e '.[gui,package]'
    python packaging/build.py

or directly:

    pyinstaller packaging/crew_gui.spec --noconfirm

The spec is cross-platform — it branches on ``sys.platform`` only for
the macOS ``.app`` bundle wrapper and the Windows/Linux icon. Output
goes to ``dist/Crew/`` (folder) and on macOS additionally to
``dist/Crew.app/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ``SPECPATH`` is injected by PyInstaller — the directory containing this spec.
REPO_ROOT = Path(SPECPATH).parent  # type: ignore[name-defined]
ENTRY = str(REPO_ROOT / "crew" / "gui" / "__main__.py")

# Data files that need to travel with the bundle. The destination paths
# mirror the source layout so ``Path(__file__).parent`` lookups inside
# ``crew/gui/app.py`` resolve at runtime.
datas = [
    (str(REPO_ROOT / "crew" / "gui" / "templates"), "crew/gui/templates"),
    (str(REPO_ROOT / "crew" / "gui" / "static"), "crew/gui/static"),
    (str(REPO_ROOT / "crew" / "gui" / "fixtures"), "crew/gui/fixtures"),
]
datas += collect_data_files("webview")  # pywebview platform runtime assets

# Hidden imports: uvicorn / starlette / sse_starlette lazy-load plenty of
# protocol/transport modules that PyInstaller's static analysis misses.
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("starlette")
    + collect_submodules("sse_starlette")
    + collect_submodules("webview")
    + [
        "crew.gui.app",
        "crew.gui.server",
        "crew.gui.config",
        "crew.gui.routes.home",
        "crew.gui.routes.timeline",
        "crew.gui.routes.context",
        "crew.gui.routes.standup",
        "crew.gui.routes.status",
        "crew.gui.routes.events",
    ]
)

# Icons — ship generic placeholders; swap in real .icns/.ico artwork
# before the first signed release.
icon_path = None
_mac_icon = REPO_ROOT / "packaging" / "Crew.icns"
_win_icon = REPO_ROOT / "packaging" / "Crew.ico"
if sys.platform == "darwin" and _mac_icon.exists():
    icon_path = str(_mac_icon)
elif sys.platform == "win32" and _win_icon.exists():
    icon_path = str(_win_icon)

block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Crew",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window on Windows / macOS launchers
    argv_emulation=True,    # macOS: deliver Finder open-file events
    target_arch=None,
    codesign_identity=None, # set to your Developer ID for signed releases
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Crew",
)

# macOS app bundle — produces dist/Crew.app/ alongside dist/Crew/.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Crew.app",
        icon=icon_path,
        bundle_identifier="com.crew.app",
        info_plist={
            "CFBundleName": "Crew",
            "CFBundleDisplayName": "Crew",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSUIElement": False,
            # Keep the window event loop alive when all windows close so
            # reopening from the dock does the right thing later.
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
