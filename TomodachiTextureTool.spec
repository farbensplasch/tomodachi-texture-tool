import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

# customtkinter ships theme JSON files that must be bundled
ctk_datas, ctk_bins, ctk_hidden = collect_all("customtkinter")

# tkinterdnd2 ships a native shared library per platform
try:
    dnd_datas, dnd_bins, dnd_hidden = collect_all("tkinterdnd2")
except Exception:
    dnd_datas, dnd_bins, dnd_hidden = [], [], []

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=ctk_bins + dnd_bins,
    datas=ctk_datas + dnd_datas,
    hiddenimports=(
        ctk_hidden
        + dnd_hidden
        + [
            "PIL._tkinter_finder",
            "numpy",
            "zstandard",
        ]
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TomodachiTextureTool",
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no terminal window
    windowed=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# macOS: also wrap in a .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="TomodachiTextureTool.app",
        bundle_identifier="com.farbensplasch.tomodachi-texture-tool",
    )
