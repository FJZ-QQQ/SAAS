# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

def _read_env_values(env_path):
    values = {}
    deny_names = {
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    }
    deny_prefixes = ("DB_", "POSTGRES_", "SUPABASE_")
    if not os.path.exists(env_path):
        values["GUANGCHEN_CLIENT_MODE"] = "1"
        values["GUANGCHEN_CLOUD_API"] = os.environ.get("GUANGCHEN_CLOUD_API", "http://124.223.99.238:8100")
        values["GUANGCHEN_BACKEND_API"] = os.environ.get("GUANGCHEN_BACKEND_API", values["GUANGCHEN_CLOUD_API"])
        return values
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in deny_names or key.startswith(deny_prefixes):
                continue
            if key:
                values[key] = value
    values["GUANGCHEN_CLIENT_MODE"] = "1"
    values.setdefault("GUANGCHEN_CLOUD_API", os.environ.get("GUANGCHEN_CLOUD_API", "http://124.223.99.238:8100"))
    values.setdefault("GUANGCHEN_BACKEND_API", os.environ.get("GUANGCHEN_BACKEND_API", values["GUANGCHEN_CLOUD_API"]))
    return values

embedded_env_hook = os.path.abspath(os.path.join("build", "_embedded_env_runtime.py"))
os.makedirs(os.path.dirname(embedded_env_hook), exist_ok=True)
with open(embedded_env_hook, "w", encoding="utf-8") as f:
    f.write("import os\n")
    f.write(f"_EMBEDDED_ENV = {_read_env_values('.env')!r}\n")
    f.write("for _key, _value in _EMBEDDED_ENV.items():\n")
    f.write("    os.environ.setdefault(_key, _value)\n")

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
    datas=playwright_datas,
    hiddenimports=[
        'ai_replier',
        'slot_manager',
        'db_manager',
        'lead_extractor',
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
    runtime_hooks=[embedded_env_hook],
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
