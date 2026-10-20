# -*- mode: python ; coding: utf-8 -*-
"""Stream Soundboard の PyInstaller 設定（onedir・依存縮小）。"""

from PyInstaller.utils.hooks import collect_dynamic_libs

# PortAudio / libsndfile の DLL だけ拾う（numpy の collect_all は肥大化の原因なので使わない）
binaries = []
binaries += collect_dynamic_libs("sounddevice")
binaries += collect_dynamic_libs("soundfile")

hiddenimports = [
    "stream_soundboard",
    "stream_soundboard.audio_devices",
    "stream_soundboard.audio_mixer",
    "stream_soundboard.audio_player",
    "stream_soundboard.config_store",
    "stream_soundboard.sample_loader",
    "stream_soundboard.widget_gui",
    "numpy",
    "sounddevice",
    "soundfile",
    "_soundfile_data",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_cov",
        "numba",
        "llvmlite",
        "scipy",
        "matplotlib",
        "pandas",
        "IPython",
        "notebook",
        "PIL",
        "cv2",
        "torch",
        "tensorflow",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StreamSoundboard",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StreamSoundboard",
)
