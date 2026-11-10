from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('mediapipe')

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=[('hand_landmarker.task', '.'), ('logo.png', '.')] + datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig=[],
    runtime_hooks=[],
    excludes=[],
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
    name='gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='logo.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
