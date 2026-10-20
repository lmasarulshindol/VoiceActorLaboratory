# -*- mode: python ; coding: utf-8 -*-
"""Stream Soundboard の PyInstaller 設定。"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    "stream_soundboard",
    "stream_soundboard.audio_devices",
    "stream_soundboard.audio_mixer",
    "stream_soundboard.audio_player",
    "stream_soundboard.config_store",
    "stream_soundboard.sample_loader",
    "stream_soundboard.widget_gui",
]

for pkg in ("sounddevice", "soundfile", "numpy"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_cov"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StreamSoundboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
