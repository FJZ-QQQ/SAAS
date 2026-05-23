# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

# Playwright driver path
playwright_path = os.path.join(
    os.path.dirname(sys.executable),
    'Lib', 'site-packages', 'playwright'
)

# Collect playwright data
playwright_datas = [(playwright_path, 'playwright')]

a = Analysis(
    ['rpa_server.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('rpa_server.py', '.'),
        ('ai_replier.py', '.'),
        ('slot_manager.py', '.'),
        ('db_manager.py', '.'),
        ('lead_extractor.py', '.'),
    ] + playwright_datas,
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'fastapi',
        'starlette',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'httptools',
        'dotenv',
        'psycopg2',
        'requests',
        'playwright',
        'playwright.async_api',
        'playwright._impl',
        'playwright._impl._driver',
        'greenlet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='rpa_engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='rpa_engine',
)
