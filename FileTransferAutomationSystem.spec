# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('docs', 'docs'), ('templates', 'templates')],
    hiddenimports=['pyzipper', 'pyminizip', 'watchdog', 'qfluentwidgets', 'openpyxl', 'core.compression_worker'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt uses Windows' native ICU ABI. A Poppler/Conda ICU on PATH can expose
# version-suffixed exports and break frozen QtWidgets imports. Never bundle it.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FileTransferAutomationSystem',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FileTransferAutomationSystem',
)
