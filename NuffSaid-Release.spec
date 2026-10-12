# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
from importlib import import_module

# Release build (2026-10-12): no models and no NVIDIA libraries inside. first_run.py downloads them with a screen
# that says what, how big and why. Agency fonts come from assets/fonts on the build machine (not in git).
datas = [('assets/nuffsaid.png', 'assets'), ('assets/nuffsaid.ico', 'assets'), ('assets/gel.png', 'assets'), ('assets/gel-frames-idle.png', 'assets'), ('assets/gel-frames-speak.png', 'assets'), ('assets/gel-frames-clean.png', 'assets'), ('gel.frag', '.')]
datas += [(str(f), 'assets/fonts') for f in Path('assets/fonts').glob('*.*tf')]
binaries = []
hiddenimports = ['pynput.keyboard._win32', 'pynput.mouse._win32']
hiddenimports += collect_submodules('comtypes')

tmp_ret = collect_all('faster_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['run_flow.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['nvidia', 'torch', 'tensorflow', 'matplotlib', 'tkinter', 'IPython', 'pytest'],
    noarchive=False,
    optimize=0,
)
# Qt 6 uses the Windows ICU API. An unrelated Poppler ICU build from a
# development runtime has versioned exports and must not shadow System32 ICU.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in {'icuuc.dll', 'icudt78.dll'}]
# Never ship NVIDIA DLLs in the release; the optional boost downloads them.
a.binaries = [e for e in a.binaries if not e[0].replace(chr(92), '/').lower().startswith(('nvidia/', 'cuda/'))]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NuffSaid',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/nuffsaid.ico',
    version='version_info.txt',
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
    upx=True,
    upx_exclude=[],
    name='NuffSaid',
)
