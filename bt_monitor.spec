# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - BehaviorTree Monitor

将 Python 后端 + Vue 前端 dist 打包为单文件可执行程序。
使用方法:
  1. cd frontend && pnpm install && pnpm build   # 生成 dist/
  2. uv run --group dev pyinstaller bt_monitor.spec  # 打包
"""

import os

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # 打包前端构建产物
        (os.path.join(ROOT, 'dist'), 'dist'),
        # 应用资源（图标等）
        (os.path.join(ROOT, 'resources'), 'resources'),
    ],
    hiddenimports=[
        'aiohttp',
        'aiohttp.web',
        'zmq',
        'zmq.asyncio',
        'PySide6',
        'PySide6.QtWebEngineWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='BehaviorTreeMonitor',
    icon=os.path.join(ROOT, 'resources', 'icon.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
