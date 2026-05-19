# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DLP File Transfer Simulator.

Builds a single-file executable that bundles:
  - All Python source (file_transfer/, desktop_agent/, handlers/)
  - Test files (detectors_profile_test_files/)
  - Config templates (config.yaml, .env.example)

Build:
    pyinstaller dlp_simulator.spec

Output:
    dist/DLPSimulator.exe   (Windows)
    dist/DLPSimulator        (Mac/Linux)
"""

import os
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

# ── Data files to bundle ──────────────────────────────────────────
# Format: (source_path, destination_in_bundle)
datas = [
    # Test files for the DLP detector profiles
    (str(ROOT / 'detectors_profile_test_files'), 'detectors_profile_test_files'),

    # Config templates
    (str(ROOT / 'file_transfer' / 'config.yaml'), '.'),
    (str(ROOT / 'file_transfer' / '.env.example'), '.'),

    # Handler modules (collected as data so they're importable)
    (str(ROOT / 'file_transfer' / 'handlers'), 'handlers'),

    # Desktop agent package
    (str(ROOT / 'file_transfer' / 'desktop_agent'), 'desktop_agent'),

    # Watcher module
    (str(ROOT / 'file_transfer' / 'watcher.py'), '.'),
    (str(ROOT / 'file_transfer' / 'main.py'), '.'),
]

# ── Hidden imports ────────────────────────────────────────────────
# PyInstaller misses some dynamic imports; list them explicitly.
hiddenimports = [
    'handlers',
    'handlers.base',
    'handlers.box_handler',
    'handlers.desktop_agent_handler',
    'handlers.dropbox_handler',
    'handlers.local_copy_handler',
    'handlers.onedrive_handler',
    'handlers.sftp_handler',
    'handlers.teams_handler',
    'handlers.telegram_handler',
    'handlers.wetransfer_handler',
    'handlers.whatsapp_handler',
    'handlers.zoom_handler',
    'desktop_agent',
    'desktop_agent.agent',
    'desktop_agent.actions',
    'desktop_agent.screen',
    'desktop_agent.tasks',
    'watcher',
    'yaml',
    'dotenv',
    'watchdog',
    'watchdog.observers',
    'watchdog.events',
    'pyautogui',
    'mss',
    'PIL',
    'anthropic',
]

# ── Excludes ──────────────────────────────────────────────────────
# Keep the bundle lean — drop heavy packages we don't need.
excludes = [
    'playwright',
    'playwright.sync_api',
    'playwright.async_api',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    'tkinter',
    'matplotlib',
    'numpy',
    'scipy',
    'pandas',
    'IPython',
    'jupyter',
    'notebook',
    'test',
    'unittest',
]

# ── Analysis ──────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / 'file_transfer' / 'launcher.py')],
    pathex=[str(ROOT / 'file_transfer')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DLPSimulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # Keep console — needed for interactive wizard
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
