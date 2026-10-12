# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
from importlib import import_module

datas = [('assets/nuffsaid.png', 'assets'), ('assets/nuffsaid.ico', 'assets')]
binaries = []
hiddenimports = ['pynput.keyboard._win32', 'pynput.mouse._win32']
hiddenimports += collect_submodules('comtypes')

# Bundle CUDA user-space libraries. NVIDIA's display driver stays on the host.
for package in ('nvidia.cublas', 'nvidia.cudnn', 'nvidia.cuda_runtime', 'nvidia.cuda_nvrtc'):
    module = import_module(package)
    for location in module.__path__:
        binaries += [(str(dll), 'cuda') for dll in (Path(location) / 'bin').glob('*.dll')
                     if not dll.name.endswith('.alt.dll')]
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
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt 6 uses the Windows ICU API. An unrelated Poppler ICU build from a
# development runtime has versioned exports and must not shadow System32 ICU.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in {'icuuc.dll', 'icudt78.dll'}]
# Analysis may discover a second copy through NVIDIA package import paths.
# Keep a single canonical CUDA DLL only when its source matches exactly.
canonical = {Path(dest).name.lower(): Path(src).resolve()
             for dest, src, kind in a.binaries
             if dest.replace('\\', '/').lower().startswith('cuda/')}
a.binaries = [(dest, src, kind) for dest, src, kind in a.binaries
              if not (dest.replace('\\', '/').lower().startswith('nvidia/')
                      and canonical.get(Path(dest).name.lower()) == Path(src).resolve())]
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
