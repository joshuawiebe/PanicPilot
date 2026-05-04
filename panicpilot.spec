# =============================================================================
#  panicpilot.spec  –  PyInstaller build specification for PanicPilot
# =============================================================================
#
#  Usage:
#    pip install pyinstaller
#    pyinstaller panicpilot.spec
#
#  Output:
#    dist/PanicPilot/        ← folder containing the executable + dependencies
#    dist/PanicPilot/PanicPilot      (Linux/macOS)
#    dist/PanicPilot/PanicPilot.exe  (Windows)
#
# =============================================================================

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    # Bundle the assets directory so sounds are available at runtime
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        # numpy internals sometimes missed by the hook
        'numpy',
        'numpy.core',
        'numpy.random',
        # pygame modules that may not be auto-detected
        'pygame',
        'pygame.mixer',
        'pygame.font',
        'pygame.scrap',
        'pygame.display',
        'pygame.event',
        'pygame.time',
        'pygame.draw',
        # standard library modules used at runtime
        'socket',
        'threading',
        'json',
        'subprocess',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # exclude test modules to keep bundle small
        'test_task1',
        'tkinter',
        'unittest',
        'doctest',
    ],
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
    exclude_binaries=True,   # onedir mode: binaries stay next to exe
    name='PanicPilot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # no console window (GUI game)
    disable_windowed_traceback=False,
    target_arch=None,        # use host architecture
    codesign_identity=None,
    entitlements_file=None,
    # Windows: show a proper application name in the taskbar
    version=None,
    icon=None,               # set to path of .ico/.icns file if available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PanicPilot',       # output folder name inside dist/
)
