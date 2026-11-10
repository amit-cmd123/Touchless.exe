from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('mediapipe')

# Add PyArmor runtime folder to the datas
datas += [
    ('obf/pyarmor_runtime_000000', 'pyarmor_runtime_000000'),
    ('hand_landmarker.task', '.'),
    ('logo.png', '.')
]

# Explicitly list hidden imports because PyInstaller cannot scan imports from PyArmor obfuscated scripts
explicit_hiddenimports = [
    'cv2',
    'numpy',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'pyautogui',
    'camera',
    'hand_tracker',
    'mouse_controller',
    'gesture_detector'
]

a = Analysis(
    ['obf/gui.py'],
    pathex=['obf'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + explicit_hiddenimports,
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
    name='Touchless',
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
