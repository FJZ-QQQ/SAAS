"""
橙子AI - RPA 多商户服务端
"""
import sys
import os

# ★ 版本号 — 每次更新递增，客户端据此判断是否需要更新
APP_VERSION = "1.0.3"
APP_BUILD = "20260521"

# Fix Windows encoding
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ★ 全局异常处理：防止进程因未捕获异常而静默退出
import threading
import traceback

def _global_excepthook(exc_type, exc_value, exc_tb):
    print(f"[FATAL] Unhandled exception: {exc_type.__name__}: {exc_value}")
    traceback.print_exception(exc_type, exc_value, exc_tb)

def _thread_excepthook(args):
    print(f"[FATAL] Thread '{args.thread.name}' crashed: {args.exc_type.__name__}: {args.exc_value}")
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_tb)

sys.excepthook = _global_excepthook
threading.excepthook = _thread_excepthook

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import hashlib
import hmac
import secrets
from dotenv import load_dotenv
from slot_manager import SlotManager

# Load .env — 兼容开发模式和打包后的 EXE 模式
import pathlib
_script_dir = pathlib.Path(__file__).resolve().parent
# 优先从脚本同级目录加载（EXE 打包后的路径）
_env_candidates = [
    _script_dir / ".env",
    _script_dir.parent / ".env",
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path)
        print(f"[RPA] .env loaded from: {_env_path}")
        break
else:
    print("[RPA] WARNING: .env file not found!")

# Verify critical env vars are loaded
import os
db_url = os.getenv("DATABASE_URL", "")
coze_key = os.getenv("COZE_API_KEY", "")
print(f"[RPA] DATABASE_URL loaded: {'YES' if db_url else 'NO!!!'}")
print(f"[RPA] COZE_API_KEY loaded: {'YES' if coze_key else 'NO!!!'}")
print(f"[RPA] Version: {APP_VERSION} (build {APP_BUILD})")

app = FastAPI(title="Orange AI RPA Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

slot_manager = SlotManager()


def _parse_owner_slot(data: dict):
    owner_merchant_id = data.get("owner_merchant_id") or data.get("owner_id") or data.get("merchant_id")
    slot_id = data.get("slot_id") or data.get("store_id") or data.get("merchant_id")
    if not owner_merchant_id:
        return None, None, "missing owner_merchant_id"
    if not slot_id:
        return None, None, "missing slot_id"
    return int(owner_merchant_id), int(slot_id), None


@app.on_event("startup")
async def startup_event():
    print("[RPA] Service starting...")
    try:
        _ensure_runtime_schema()
    except Exception as e:
        print(f"[RPA] runtime schema check failed: {e}")
    # ★ 只加载账号记录（不打开浏览器），等用户手动点「启动」才打开
    try:
        await slot_manager.load_session_metadata()
    except Exception as e:
        print(f"[RPA] load metadata error: {e}")
    print("[RPA] ✅ API ready — browser will start when user clicks Start")


@app.on_event("shutdown")
async def shutdown_event():
    print("[RPA] Shutting down all slots...")
    await slot_manager.shutdown_all()
    print("[RPA] All slots closed")

@app.post("/shutdown")
async def shutdown_api():
    """★ Electron 退出时调用：优雅关闭所有浏览器和 Playwright"""
    print("[RPA] /shutdown called — closing all browsers...")
    try:
        await slot_manager.shutdown_all()
        print("[RPA] ✅ All browsers closed gracefully")
    except Exception as e:
        print(f"[RPA] shutdown error: {e}")
    # 延迟退出进程，让响应先返回
    import asyncio
    asyncio.get_event_loop().call_later(1, lambda: os._exit(0))
    return {"status": "ok", "message": "shutting down"}


@app.post("/slot/bind")
async def bind_slot(request: Request):
    data = await request.json()
    owner_merchant_id, slot_id, error = _parse_owner_slot(data)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    try:
        result = await slot_manager.create_bind_slot(owner_merchant_id, slot_id)
        return result
    except Exception as e:
        print(f"[RPA] /slot/bind error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"启动浏览器失败: {str(e)}"}, status_code=500)


@app.get("/slot/bind/status")
async def get_bind_status(merchant_id: int = 0, owner_merchant_id: int = 0, slot_id: int = 0):
    owner = owner_merchant_id or merchant_id
    slot = slot_id or merchant_id
    result = await slot_manager.check_bind_status(owner, slot)
    return result


@app.post("/slot/start")
async def start_slot(request: Request):
    data = await request.json()
    owner_merchant_id, slot_id, error = _parse_owner_slot(data)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    try:
        await slot_manager.start_monitoring(owner_merchant_id, slot_id)
        # Give the background task a moment to actually start
        import asyncio
        await asyncio.sleep(0.5)
        return {"status": "success", "message": "monitoring started"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/slot/stop")
async def stop_slot(request: Request):
    data = await request.json()
    owner_merchant_id, slot_id, error = _parse_owner_slot(data)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    await slot_manager.stop_monitoring(owner_merchant_id, slot_id)
    return {"status": "success", "message": "monitoring stopped"}


@app.post("/slot/delete")
async def delete_slot(request: Request):
    data = await request.json()
    owner_merchant_id, slot_id, error = _parse_owner_slot(data)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    await slot_manager.delete_slot(owner_merchant_id, slot_id)
    return {"status": "success", "message": "slot deleted"}


@app.post("/slot/show-browser")
async def show_browser():
    """弹出 Chrome 浏览器窗口到前台，方便用户审查"""
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32

        # 枚举所有窗口，找到 Chrome 窗口
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        chrome_hwnds = []

        def enum_callback(hwnd, lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if user32.IsWindowVisible(hwnd) and ("Chrome" in title or "抖音" in title or "douyin" in title.lower() or "creator" in title.lower()):
                    chrome_hwnds.append(hwnd)
            return True

        user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

        if chrome_hwnds:
            hwnd = chrome_hwnds[0]
            SW_RESTORE = 9
            SW_MAXIMIZE = 3
            # 如果最小化了就恢复
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            user32.SetForegroundWindow(hwnd)
            print(f"[RPA] Chrome window brought to front (hwnd={hwnd})")
            return {"status": "ok", "message": "Chrome window shown"}
        else:
            return {"status": "no_window", "message": "No Chrome window found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/status")
async def get_all_status(merchant_id: int = 0, owner_merchant_id: int = 0):
    owner = owner_merchant_id or merchant_id
    return await slot_manager.get_all_status(owner if owner > 0 else None)

# ================= 数据库工具函数 =================

import psycopg2
import re
import random
import time as _time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime

_POSTGRES_PARAMS = {
    "sslmode", "sslcert", "sslkey", "sslrootcert",
    "application_name", "options", "keepalives",
    "keepalives_idle", "keepalives_interval", "keepalives_count",
    "target_session_attrs",
}

def _clean_db_url(url):
    """清理 DATABASE_URL，移除 pgbouncer 等非标参数"""
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        clean_params = {k: v[0] for k, v in params.items() if k in _POSTGRES_PARAMS}
        clean_query = urlencode(clean_params) if clean_params else ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment))
    return url

def _get_db_conn():
    """获取一个新的数据库连接（调用方负责关闭）"""
    if not db_url:
        return None
    return psycopg2.connect(_clean_db_url(db_url))


def _ensure_runtime_schema():
    """保证正式库支持“一个登录商户多个店铺槽位”的运行字段。"""
    conn = _get_db_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            required = {
                "rpa_slot": "slot_id",
                "customer_lead": "slot_id",
                "chat_session": "slot_id",
            }
            missing = []
            for table, column in required.items():
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                    """,
                    (table, column)
                )
                if not cur.fetchone():
                    missing.append((table, column))
            if not missing:
                print("[RPA] runtime schema OK")
                return

            cur.execute("ALTER TABLE rpa_slot ADD COLUMN IF NOT EXISTS slot_id INTEGER")
            cur.execute("UPDATE rpa_slot SET slot_id = merchant_id WHERE slot_id IS NULL")
            cur.execute("ALTER TABLE customer_lead ADD COLUMN IF NOT EXISTS slot_id INTEGER")
            cur.execute("ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS slot_id INTEGER")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_rpa_slot_owner_slot ON rpa_slot(merchant_id, slot_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_customer_lead_owner_slot ON customer_lead(merchant_id, slot_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_session_owner_slot ON chat_session(merchant_id, slot_id)")
        conn.commit()
        print("[RPA] runtime schema OK")
    finally:
        conn.close()

# ================= 短信验证码（内存缓存） =================

_sms_codes = {}  # phone -> {"code": "1234", "expire": timestamp}

# ★ 免验证码的测试账号
_TEST_ACCOUNTS = {
    "1825134214": "888888",   # 老板测试账号，任意验证码可登录
}

def _generate_sms_code(phone: str) -> str:
    """生成6位验证码并缓存（5分钟有效）"""
    code = str(random.randint(100000, 999999))
    _sms_codes[phone] = {"code": code, "expire": _time.time() + 300}
    return code

def _verify_sms_code(phone: str, code: str) -> bool:
    """验证短信验证码"""
    # ★ 测试账号：任意验证码都通过
    if phone in _TEST_ACCOUNTS:
        return True
    
    entry = _sms_codes.get(phone)
    if not entry:
        return False
    if _time.time() > entry["expire"]:
        del _sms_codes[phone]
        return False
    if entry["code"] == code:
        del _sms_codes[phone]  # 验证成功后删除
        return True
    return False

def _generate_session_token() -> str:
    """生成随机会话 token"""
    return secrets.token_hex(32)

_PASSWORD_HASH_PREFIX = "sha256$"
_ADMIN_TOKENS = {}
_ADMIN_TOKEN_TTL_SECONDS = 12 * 60 * 60

def _hash_password(password: str) -> str:
    """生成带盐密码哈希。"""
    salt = secrets.token_hex(12)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"{_PASSWORD_HASH_PREFIX}{salt}${digest}"

def _verify_password(password: str, stored: str) -> bool:
    """验证密码；兼容旧库中的明文或无盐 sha256。"""
    if not password or not stored:
        return False
    stored = str(stored)
    if stored.startswith(_PASSWORD_HASH_PREFIX):
        try:
            _, salt, expected = stored.split("$", 2)
        except ValueError:
            return False
        actual = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual, expected)
    if re.fullmatch(r"[0-9a-fA-F]{64}", stored):
        actual = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual.lower(), stored.lower())
    return hmac.compare_digest(password, stored)

def _create_admin_token(admin_id: int, username: str, role: str) -> str:
    token = secrets.token_hex(32)
    _ADMIN_TOKENS[token] = {
        "admin_id": admin_id,
        "username": username,
        "role": role or "admin",
        "expire_at": _time.time() + _ADMIN_TOKEN_TTL_SECONDS,
    }
    return token

def _get_bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return ""
    return auth.split(" ", 1)[1].strip()

def _require_admin(request: Request):
    token = _get_bearer_token(request)
    if not token:
        return None
    admin = _ADMIN_TOKENS.get(token)
    if not admin:
        return None
    if _time.time() > admin["expire_at"]:
        _ADMIN_TOKENS.pop(token, None)
        return None
    admin["expire_at"] = _time.time() + _ADMIN_TOKEN_TTL_SECONDS
    return admin

def _admin_unauthorized():
    return JSONResponse({"error": "管理员登录已过期，请重新登录"}, status_code=401)

def _save_session_token(conn, merchant_id: int, token: str):
    """保存会话 token 到数据库（30天有效）"""
    try:
        with conn.cursor() as cur:
            # 先删除该商户的旧 token
            cur.execute("DELETE FROM merchant_session WHERE merchant_id = %s", (merchant_id,))
            # 插入新 token
            expire_at = datetime.now() + __import__('datetime').timedelta(days=30)
            cur.execute(
                "INSERT INTO merchant_session (merchant_id, token, expire_at, created_at) VALUES (%s, %s, %s, %s)",
                (merchant_id, token, expire_at, datetime.now())
            )
            conn.commit()
    except Exception as e:
        print(f"[AUTH] save token error: {e}")
        # 如果表不存在，自动创建
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS merchant_session (
                        id SERIAL PRIMARY KEY,
                        merchant_id INTEGER NOT NULL,
                        token VARCHAR(128) NOT NULL UNIQUE,
                        expire_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                conn.commit()
                # 重试插入
                expire_at = datetime.now() + __import__('datetime').timedelta(days=30)
                with conn.cursor() as cur2:
                    cur2.execute(
                        "INSERT INTO merchant_session (merchant_id, token, expire_at, created_at) VALUES (%s, %s, %s, %s)",
                        (merchant_id, token, expire_at, datetime.now())
                    )
                    conn.commit()
                print("[AUTH] created merchant_session table and saved token")
        except Exception as e2:
            print(f"[AUTH] create table error: {e2}")

def _verify_session_token(token: str) -> dict:
    """验证会话 token，返回商户信息或 None"""
    try:
        conn = _get_db_conn()
        if not conn:
            return None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.merchant_id, m.phone, m.balance, m.status, s.expire_at
                FROM merchant_session s
                JOIN merchant m ON m.id = s.merchant_id
                WHERE s.token = %s
            """, (token,))
            row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # 检查是否过期
        expire_at = row[4]
        if datetime.now() > expire_at:
            return None
        
        # 检查账号是否被禁用
        if row[3] != 1:
            return None
        
        return {
            "merchant_id": row[0],
            "phone": row[1],
            "balance": float(row[2]) if row[2] else 0,
        }
    except Exception as e:
        print(f"[AUTH] verify token error: {e}")
        return None

def _delete_session_token(token: str):
    """删除会话 token（退出登录时调用）"""
    try:
        conn = _get_db_conn()
        if conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM merchant_session WHERE token = %s", (token,))
                conn.commit()
            conn.close()
    except Exception as e:
        print(f"[AUTH] delete token error: {e}")

# ================= 运行时日志（内存） =================

_runtime_logs = []

def add_runtime_log(action, detail, log_type="info"):
    """向运行时日志中追加一条记录"""
    now = datetime.now()
    _runtime_logs.append({
        "time": now.strftime("%H:%M:%S"),
        "action": action,
        "detail": detail,
        "type": log_type
    })
    # 最多保留 200 条
    if len(_runtime_logs) > 200:
        _runtime_logs.pop(0)

# 启动时写入一条
add_runtime_log("系统", "RPA 服务启动完成", "info")

# ================= 桌面端 UI 数据接口（全部连接真实数据库） =================

@app.post("/api/sms/send")
async def send_sms(request: Request):
    """发送短信验证码"""
    data = await request.json()
    phone = data.get("phone", "").strip()
    
    if not phone or not re.match(r'^1[3-9]\d{9}$', phone):
        return JSONResponse({"error": "请输入正确的手机号"}, status_code=400)
    
    # ★ 测试账号：不需要真正发短信
    if phone in _TEST_ACCOUNTS:
        _sms_codes[phone] = {"code": "888888", "expire": _time.time() + 300}
        print(f"[SMS] 测试账号 {phone}，无需验证码")
        add_runtime_log("短信", f"测试账号 {phone} 免验证码", "info")
        return {"status": "ok", "message": "测试账号，无需验证码", "mock": True, "test_account": True}
    
    code = _generate_sms_code(phone)
    
    # 检查是否配置了阿里云SMS
    aliyun_key = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    if aliyun_key:
        # TODO: 接入阿里云SMS真实发送
        print(f"[SMS] 发送验证码到 {phone}: {code} (阿里云SMS)")
    else:
        # 模拟模式 — 验证码固定为 123456，打印到控制台
        _sms_codes[phone] = {"code": "123456", "expire": _time.time() + 300}
        print(f"[SMS] 模拟验证码 → {phone}: 123456")
    
    add_runtime_log("短信", f"验证码已发送到 {phone}", "info")
    return {"status": "ok", "message": "验证码已发送", "mock": not bool(aliyun_key)}

@app.post("/api/login")
async def login(request: Request):
    """用手机号+密码登录，账号由管理员预先创建。"""
    data = await request.json()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()
    
    if not phone:
        return JSONResponse({"error": "请输入手机号"}, status_code=400)
    if not password:
        return JSONResponse({"error": "请输入密码"}, status_code=400)
    
    try:
        conn = _get_db_conn()
        if not conn:
            return JSONResponse({"error": "数据库未连接，无法登录"}, status_code=500)
        with conn.cursor() as cur:
            cur.execute("SELECT id, phone, balance, status, password_hash FROM merchant WHERE phone = %s", (phone,))
            row = cur.fetchone()
            
            if not row:
                conn.close()
                return JSONResponse({"error": "账号不存在，请联系管理员开通"}, status_code=401)
            if not _verify_password(password, row[4]):
                conn.close()
                return JSONResponse({"error": "手机号或密码错误"}, status_code=401)
            if row[3] != 1:
                conn.close()
                return JSONResponse({"error": "账号已被禁用，请联系管理员"}, status_code=403)
        
        # ★ 生成并保存会话 token（30天有效）
        token = _generate_session_token()
        _save_session_token(conn, row[0], token)
        conn.close()
        
        add_runtime_log("登录", f"商户 #{row[0]} ({phone}) 登录成功", "success")
        return {
            "status": "ok",
            "merchant_id": row[0],
            "phone": row[1],
            "balance": float(row[2]) if row[2] else 0,
            "token": token,
        }
    except Exception as e:
        print(f"[RPA] /api/login error: {e}")
        return JSONResponse({"error": f"登录失败: {e}"}, status_code=500)

@app.post("/api/auth/check")
async def check_auth(request: Request):
    """★ 自动登录：验证本地保存的 token 是否有效"""
    data = await request.json()
    token = data.get("token", "")
    
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    
    merchant = _verify_session_token(token)
    if not merchant:
        return JSONResponse({"error": "token expired"}, status_code=401)
    
    add_runtime_log("自动登录", f"商户 #{merchant['merchant_id']} ({merchant['phone']}) token 验证通过", "info")
    return {"status": "ok", **merchant}

@app.post("/api/auth/logout")
async def logout(request: Request):
    """★ 退出登录：删除服务端 token，前端清除 localStorage"""
    data = await request.json()
    token = data.get("token", "")
    if token:
        _delete_session_token(token)
    return {"status": "ok"}

@app.post("/api/auth/change-password")
async def change_password(request: Request):
    """★ 修改密码：需要旧密码验证"""
    data = await request.json()
    merchant_id = data.get("merchant_id")
    old_password = data.get("old_password", "").strip()
    new_password = data.get("new_password", "").strip()

    if not merchant_id:
        return JSONResponse({"error": "缺少商户信息"}, status_code=400)
    if not old_password:
        return JSONResponse({"error": "请输入原密码"}, status_code=400)
    if not new_password:
        return JSONResponse({"error": "请输入新密码"}, status_code=400)
    if len(new_password) < 6:
        return JSONResponse({"error": "新密码至少 6 位"}, status_code=400)

    try:
        conn = _get_db_conn()
        if not conn:
            return JSONResponse({"error": "数据库未连接"}, status_code=500)
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM merchant WHERE id = %s", (merchant_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return JSONResponse({"error": "账号不存在"}, status_code=404)
            if not _verify_password(old_password, row[0]):
                conn.close()
                return JSONResponse({"error": "原密码不正确"}, status_code=401)
            new_hash = _hash_password(new_password)
            cur.execute("UPDATE merchant SET password_hash = %s WHERE id = %s", (new_hash, merchant_id))
            conn.commit()
        conn.close()
        add_runtime_log("安全", f"商户 #{merchant_id} 修改了登录密码", "info")
        return {"status": "ok", "message": "密码修改成功"}
    except Exception as e:
        print(f"[RPA] change-password error: {e}")
        return JSONResponse({"error": f"修改失败: {e}"}, status_code=500)

@app.get("/api/logs")
async def get_logs():
    """返回运行时真实日志"""
    return list(reversed(_runtime_logs[-30:]))

@app.get("/api/stats")
async def get_stats(merchant_id: int = 0):
    """返回工作台统计数据（按商户隔离）"""
    result = {"messages": 0, "ai_replies": 0, "leads": 0,
              "today_messages": 0, "today_leads": 0, "lead_rate": 0,
              "ai_success_rate": 100, "avg_response_time": 0}
    
    # ★ 从 SlotManager 获取今日实时统计
    try:
        today = slot_manager.get_today_stats()
        result.update(today)
    except Exception as e:
        print(f"[RPA] today stats error: {e}")
    
    # ★ 从数据库获取历史总数（按 merchant_id 隔离）
    try:
        conn = _get_db_conn()
        if conn:
            with conn.cursor() as cur:
                if merchant_id > 0:
                    cur.execute("SELECT COUNT(id) FROM customer_lead WHERE merchant_id = %s", (merchant_id,))
                else:
                    cur.execute("SELECT COUNT(id) FROM customer_lead")
                result["leads"] = cur.fetchone()[0]
                try:
                    if merchant_id > 0:
                        cur.execute("SELECT COALESCE(SUM(total_messages), 0), COALESCE(SUM(total_replies), 0) FROM rpa_slot WHERE merchant_id = %s", (merchant_id,))
                    else:
                        cur.execute("SELECT COALESCE(SUM(total_messages), 0), COALESCE(SUM(total_replies), 0) FROM rpa_slot")
                    row = cur.fetchone()
                    if row:
                        result["messages"] = row[0]
                        result["ai_replies"] = row[1]
                except Exception:
                    conn.rollback()
            conn.close()
    except Exception as e:
        print(f"[RPA] /api/stats DB error: {e}")
    
    return result

@app.get("/api/leads")
async def get_leads(merchant_id: int = 0):
    """返回线索中心数据（★ 按商户隔离）"""
    try:
        conn = _get_db_conn()
        if not conn:
            return []
        with conn.cursor() as cur:
            if merchant_id > 0:
                cur.execute("""
                    SELECT id, merchant_id, slot_id, douyin_nickname, contact, contact_type, created_at 
                    FROM customer_lead 
                    WHERE merchant_id = %s
                    ORDER BY created_at DESC LIMIT 100
                """, (merchant_id,))
            else:
                cur.execute("""
                    SELECT id, merchant_id, slot_id, douyin_nickname, contact, contact_type, created_at 
                    FROM customer_lead 
                    ORDER BY created_at DESC LIMIT 100
                """)
            rows = cur.fetchall()
            leads = []
            for row in rows:
                leads.append({
                    "id": row[0],
                    "source": f"店铺 {row[2] or row[1]}",
                    "user": row[3] or "未知用户",
                    "type": "手机号" if row[5] == 1 else "微信号",
                    "value": row[4] or "",
                    "time": row[6].strftime("%Y-%m-%d %H:%M") if row[6] else "",
                    "status": "已提取"
                })
        conn.close()
        return leads
    except Exception as e:
        print(f"[RPA] /api/leads DB error: {e}")
        return []

@app.get("/api/leads/export")
async def export_leads(merchant_id: int = 0):
    """导出留资数据为 CSV 文件（★ 按商户隔离）"""
    from fastapi.responses import StreamingResponse
    import io, csv
    
    leads = await get_leads(merchant_id=merchant_id)
    
    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Excel
    writer = csv.writer(output)
    writer.writerow(["序号", "抖音昵称", "联系方式", "类型", "来源", "时间", "状态"])
    for i, lead in enumerate(leads, 1):
        writer.writerow([i, lead["user"], lead["value"], lead["type"], lead["source"], lead["time"], lead["status"]])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"}
    )

@app.get("/api/sensitive-words")
async def get_sensitive_words(merchant_id: int = 0):
    """获取敏感词列表（★ 按商户隔离）"""
    suffix = f"_{merchant_id}" if merchant_id > 0 else ""
    sw_file = os.path.join(AGENT_CONFIG_DIR, f"sensitive_words{suffix}.json")
    # 如果商户独立文件不存在，尝试读全局文件
    if not os.path.exists(sw_file):
        sw_file = os.path.join(AGENT_CONFIG_DIR, "sensitive_words.json")
    try:
        if os.path.exists(sw_file):
            with open(sw_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[RPA] 读取敏感词失败: {e}")
    return {"words": []}

@app.post("/api/sensitive-words")
async def save_sensitive_words(req: dict):
    """保存敏感词列表（★ 按商户隔离）"""
    merchant_id = req.get("merchant_id", 0)
    suffix = f"_{merchant_id}" if merchant_id > 0 else ""
    sw_file = os.path.join(AGENT_CONFIG_DIR, f"sensitive_words{suffix}.json")
    words = req.get("words", [])
    with open(sw_file, "w", encoding="utf-8") as f:
        json.dump({"words": words}, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "count": len(words)}

# ★ 本地 JSON 配置文件（每个店铺独立一份）
AGENT_CONFIG_DIR = os.path.join(str(_script_dir), "agent_configs")
os.makedirs(AGENT_CONFIG_DIR, exist_ok=True)

def _config_file(merchant_id: int) -> str:
    return os.path.join(AGENT_CONFIG_DIR, f"store_{merchant_id}.json")

def _load_agent_config(merchant_id: int = 1) -> dict:
    """从本地 JSON 文件读取指定店铺的 AI 配置"""
    default = {"nickname": "", "persona": "", "knowledge_base": "", "keywords": []}
    path = _config_file(merchant_id)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)}
    except Exception as e:
        print(f"[RPA] 读取店铺{merchant_id}配置失败: {e}")
    # 兼容旧的全局配置文件
    old_file = os.path.join(str(_script_dir), "agent_config.json")
    try:
        if os.path.exists(old_file):
            with open(old_file, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)}
    except Exception:
        pass
    return default

def _save_agent_config(config: dict, merchant_id: int = 1):
    """保存指定店铺的 AI 配置到本地 JSON 文件"""
    with open(_config_file(merchant_id), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

@app.get("/api/scripts")
async def get_scripts(merchant_id: int = 1):
    """返回指定店铺的 AI 智能体配置"""
    config = _load_agent_config(merchant_id)
    return config

@app.post("/api/scripts")
async def save_scripts(request: Request):
    """保存指定店铺的 AI 智能体配置"""
    data = await request.json()
    merchant_id = data.get("merchant_id", 1)
    config = {
        "nickname": data.get("nickname", "小橙"),
        "persona": data.get("persona", ""),
        "knowledge_base": data.get("knowledge_base", ""),
        "keywords": data.get("keywords", []),
    }
    try:
        _save_agent_config(config, merchant_id)
        add_runtime_log("配置", f"店铺{merchant_id} AI配置已保存（昵称: {config['nickname']}）", "success")
        
        # ★ 异步回传到远程数据库（后台线程，不阻塞响应）
        import threading
        def _sync_to_db():
            try:
                db_url = os.getenv("DATABASE_URL", "")
                if not db_url:
                    return
                from db_manager import DatabaseManager
                db = DatabaseManager(db_url, merchant_id)
                db.connect()
                if db.conn:
                    db.save_agent_config(config["nickname"], config["persona"], config["knowledge_base"])
                    db.close()
                    print(f"[RPA] ✅ 店铺{merchant_id}配置已同步到远程数据库")
                else:
                    print(f"[RPA] DB离线，跳过同步（本地配置不受影响）")
            except Exception as e:
                print(f"[RPA] DB同步失败（不影响本地）: {e}")
        threading.Thread(target=_sync_to_db, daemon=True).start()
        
        return {"status": "ok", "message": "配置已保存"}
    except Exception as e:
        print(f"[RPA] 保存配置失败: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/test-chat")
async def test_chat(request: Request):
    """模拟对话测试：调用真实 AI API 获取回复（支持多轮）"""
    data = await request.json()
    message = data.get("message", "").strip()
    user_id = data.get("user_id", "test_user")
    agent_config = data.get("agent_config", {})
    merchant_id = data.get("merchant_id", 1)
    
    if not message:
        return JSONResponse({"error": "消息不能为空"}, status_code=400)
    
    # 如果前端没传 config，从本地文件加载
    if not agent_config.get("nickname"):
        agent_config = _load_agent_config(merchant_id)
    if not agent_config.get("nickname"):
        agent_config["nickname"] = "小橙"
    
    try:
        api_key = os.getenv("COZE_API_KEY", "")
        bot_id = os.getenv("COZE_BOT_ID", "")
        
        if not api_key:
            return {"reply": f"你好！我是{agent_config.get('nickname', '小橙')}，API 密钥未配置，请在 .env 中设置 COZE_API_KEY。", "source": "mock"}
        
        # ★ 使用全局 AI 实例（slot_manager 里的），保持会话上下文
        ai = None
        for mid, slot_data in slot_manager.slots.items():
            if slot_data.get("ai"):
                ai = slot_data["ai"]
                break
        
        if not ai:
            from ai_replier import AIReplier
            ai = AIReplier(api_key, bot_id)
        
        import asyncio
        reply = await asyncio.to_thread(ai.get_reply, message, agent_config, user_id)
        return {"reply": reply, "source": "ai"}
    except Exception as e:
        print(f"[RPA] /api/test-chat error: {e}")
        return {"reply": f"AI 调用出错: {e}", "source": "error"}

@app.get("/api/messages")
async def get_messages(merchant_id: int = 0):
    """返回消息监控数据（★ 按商户隔离）"""
    all_messages = []
    try:
        conn = _get_db_conn()
        if conn:
            with conn.cursor() as cur:
                where_sql = ""
                params = []
                if merchant_id > 0:
                    where_sql = "WHERE cs.merchant_id = %s"
                    params.append(merchant_id)
                cur.execute(f"""
                    SELECT cm.id, cs.merchant_id, cs.slot_id, cs.user_id, cm.sender_type, cm.content, cm.created_at
                    FROM chat_message cm
                    JOIN chat_session cs ON cs.id = cm.session_id
                    {where_sql}
                    ORDER BY cm.created_at DESC
                    LIMIT 200
                """, params)
                rows = cur.fetchall()
            conn.close()
            for row in reversed(rows):
                all_messages.append({
                    "id": row[0],
                    "sender": row[3] or "未知",
                    "text": row[5] or "",
                    "time": row[6].strftime("%H:%M:%S") if row[6] else "",
                    "account": f"店铺 {row[2] or row[1]}",
                    "account_id": row[2] or row[1],
                    "owner_merchant_id": row[1],
                    "is_ai": row[4] == "ai",
                })
            if all_messages:
                return all_messages
    except Exception as e:
        print(f"[RPA] /api/messages DB error: {e}")

    for mid, slot_data in slot_manager.slots.items():
        # ★ 只返回该商户的消息
        owner = int(slot_data.get("owner_merchant_id") or mid)
        if merchant_id > 0 and owner != merchant_id:
            continue
        runtime_msgs = slot_data.get("runtime_messages", [])
        for msg in runtime_msgs[-50:]:
            all_messages.append({
                "id": msg.get("id", 0),
                "sender": msg.get("sender", "未知"),
                "text": msg.get("text", ""),
                "time": msg.get("time", ""),
                "account": f"店铺 {mid}",
                "account_id": mid,
                "owner_merchant_id": owner,
                "is_ai": msg.get("is_ai", False),
            })
    return all_messages

_account_cache = {}       # { merchant_id: result_dict }
_account_cache_ts = {}    # { merchant_id: timestamp }
_ACCOUNT_CACHE_TTL = 5    # 余额扣费后需要尽快反馈到客户界面

@app.get("/api/account")
async def get_account(merchant_id: int = 0):
    """返回当前商户的真实账户信息（带 30s 缓存）"""
    now = _time.time()
    cached = _account_cache.get(merchant_id)
    cached_ts = _account_cache_ts.get(merchant_id, 0)
    if cached and (now - cached_ts) < _ACCOUNT_CACHE_TTL:
        return cached

    try:
        conn = _get_db_conn()
        if not conn:
            return cached or {"plan": "离线测试", "balance": 1000.0, "status": 1}
        with conn.cursor() as cur:
            if merchant_id > 0:
                cur.execute("""
                    SELECT id, phone, balance, status, created_at 
                    FROM merchant 
                    WHERE id = %s
                """, (merchant_id,))
            else:
                cur.execute("""
                    SELECT id, phone, balance, status, created_at 
                    FROM merchant 
                    ORDER BY id LIMIT 1
                """)
            row = cur.fetchone()
            if row:
                result = {
                    "merchant_id": row[0],
                    "phone": row[1],
                    "balance": float(row[2]) if row[2] else 0,
                    "status": row[3],
                    "created_at": row[4].strftime("%Y-%m-%d") if row[4] else "",
                }
            else:
                result = {"merchant_id": 0, "phone": "", "balance": 0, "status": 0, "created_at": ""}
            
            # ★ 查询该商户的 slot 数量（按商户隔离）
            try:
                if merchant_id > 0:
                    cur.execute("SELECT COUNT(id) FROM rpa_slot WHERE merchant_id = %s", (merchant_id,))
                else:
                    cur.execute("SELECT COUNT(id) FROM rpa_slot")
                result["slot_count"] = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                result["slot_count"] = 0
            
            # ★ 查询线索总数（按商户隔离）
            try:
                if merchant_id > 0:
                    cur.execute("SELECT COUNT(id) FROM customer_lead WHERE merchant_id = %s", (merchant_id,))
                else:
                    cur.execute("SELECT COUNT(id) FROM customer_lead")
                result["total_leads"] = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                result["total_leads"] = 0
                
        conn.close()
        _account_cache[merchant_id] = result
        _account_cache_ts[merchant_id] = now
        return result
    except Exception as e:
        print(f"[RPA] /api/account DB error: {e}")
        return cached or {"merchant_id": 0, "balance": 0, "status": 0, "error": str(e)}


# ================= 管理员后台 API =================

_ADMIN_ACCOUNT = os.getenv("ADMIN_ACCOUNT", "admin")
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

@app.post("/api/admin/login")
async def admin_login(request: Request):
    """管理员登录 — 优先查数据库，fallback 到 .env"""
    data = await request.json()
    account = data.get("account", "").strip()
    password = data.get("password", "").strip()
    
    # 1. 先查数据库
    try:
        conn = _get_db_conn()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, role, password FROM admin_user WHERE username = %s", (account,))
                row = cur.fetchone()
                if row and _verify_password(password, row[2]):
                    token = _create_admin_token(row[0], account, row[1] or "admin")
                    conn.close()
                    add_runtime_log("管理员", f"管理员 {account} 登录成功", "success")
                    return {"status": "ok", "role": row[1] or "admin", "admin_id": row[0], "admin_token": token}
            conn.close()
    except Exception as e:
        print(f"[ADMIN] DB login check failed: {e}")
    
    # 2. Fallback: .env 中的超级管理员
    if _ADMIN_PASSWORD and account == _ADMIN_ACCOUNT and password == _ADMIN_PASSWORD:
        token = _create_admin_token(0, account, "super_admin")
        add_runtime_log("管理员", "超级管理员登录成功", "success")
        return {"status": "ok", "role": "super_admin", "admin_id": 0, "admin_token": token}
    
    return JSONResponse({"error": "账号或密码错误"}, status_code=401)

@app.post("/api/admin/logout")
async def admin_logout(request: Request):
    token = _get_bearer_token(request)
    if token:
        _ADMIN_TOKENS.pop(token, None)
    return {"status": "ok"}

@app.get("/api/admin/admins")
async def admin_list_admins(request: Request):
    """获取管理员列表"""
    if not _require_admin(request):
        return _admin_unauthorized()
    try:
        conn = _get_db_conn()
        if not conn:
            return []
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, role, created_at FROM admin_user ORDER BY id")
            admins = []
            for row in cur.fetchall():
                admins.append({
                    "id": row[0], "username": row[1], "role": row[2],
                    "created_at": row[3].strftime("%Y-%m-%d %H:%M") if row[3] else ""
                })
        conn.close()
        return admins
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/admin/admins")
async def admin_add_admin(request: Request):
    """新增管理员"""
    if not _require_admin(request):
        return _admin_unauthorized()
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "admin")
    
    if not username or not password:
        return JSONResponse({"error": "用户名和密码不能为空"}, status_code=400)
    
    try:
        conn = _get_db_conn()
        if not conn:
            return JSONResponse({"error": "数据库未连接"}, status_code=500)
        with conn.cursor() as cur:
            cur.execute("INSERT INTO admin_user (username, password, role) VALUES (%s, %s, %s)", (username, _hash_password(password), role))
            conn.commit()
        conn.close()
        return {"status": "ok", "message": f"管理员 {username} 创建成功"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/admin/merchants")
async def admin_get_merchants(request: Request):
    """管理员：获取全部商家列表"""
    if not _require_admin(request):
        return _admin_unauthorized()
    try:
        conn = _get_db_conn()
        if not conn:
            return []
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.phone, m.balance, m.status, m.created_at,
                       (SELECT COUNT(*) FROM customer_lead cl WHERE cl.merchant_id = m.id) as lead_count
                FROM merchant m
                ORDER BY m.id DESC
            """)
            merchants = []
            for row in cur.fetchall():
                merchants.append({
                    "id": row[0],
                    "phone": row[1],
                    "balance": float(row[2]) if row[2] else 0,
                    "status": row[3],
                    "created_at": row[4].strftime("%Y-%m-%d %H:%M") if row[4] else "",
                    "lead_count": row[5],
                })
        conn.close()
        return merchants
    except Exception as e:
        print(f"[RPA] /api/admin/merchants error: {e}")
        return []

@app.post("/api/admin/balance")
async def admin_set_balance(request: Request):
    """管理员：设置商家余额"""
    if not _require_admin(request):
        return _admin_unauthorized()
    data = await request.json()
    merchant_id = data.get("merchant_id")
    balance = data.get("balance")
    
    if merchant_id is None or balance is None:
        return JSONResponse({"error": "缺少参数"}, status_code=400)
    
    try:
        conn = _get_db_conn()
        if not conn:
            return JSONResponse({"error": "数据库未连接"}, status_code=500)
        with conn.cursor() as cur:
            cur.execute("UPDATE merchant SET balance = %s WHERE id = %s", (float(balance), int(merchant_id)))
            conn.commit()
        conn.close()
        add_runtime_log("管理员", f"设置商户 #{merchant_id} 余额为 ¥{balance}", "success")
        return {"status": "ok", "message": f"余额已设置为 {balance}"}
    except Exception as e:
        print(f"[RPA] /api/admin/balance error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/recharge")
async def simulate_recharge(request: Request):
    """商家：模拟充值测试（每次固定充值100元）"""
    if os.getenv("ENABLE_TEST_RECHARGE", "0") != "1":
        return JSONResponse({"error": "测试充值功能已关闭"}, status_code=403)
    data = await request.json()
    merchant_id = data.get("merchant_id")
    
    if not merchant_id:
        return JSONResponse({"error": "缺少merchant_id"}, status_code=400)
    
    try:
        conn = _get_db_conn()
        if not conn:
            return JSONResponse({"error": "数据库未连接"}, status_code=500)
        with conn.cursor() as cur:
            cur.execute("UPDATE merchant SET balance = balance + 100 WHERE id = %s", (int(merchant_id),))
            conn.commit()
        conn.close()
        add_runtime_log("充值", f"商户 #{merchant_id} 成功充值 ¥100.00", "success")
        return {"status": "ok", "message": "模拟充值成功，余额已增加 100 元"}
    except Exception as e:
        print(f"[RPA] /api/recharge error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/admin/toggle")
async def admin_toggle_merchant(request: Request):
    """管理员：启用/停用商家"""
    if not _require_admin(request):
        return _admin_unauthorized()
    data = await request.json()
    merchant_id = data.get("merchant_id")
    status = data.get("status")  # 1=启用, 0=停用
    
    if merchant_id is None or status is None:
        return JSONResponse({"error": "缺少参数"}, status_code=400)
    
    try:
        conn = _get_db_conn()
        if not conn:
            return JSONResponse({"error": "数据库未连接"}, status_code=500)
        with conn.cursor() as cur:
            cur.execute("UPDATE merchant SET status = %s WHERE id = %s", (int(status), int(merchant_id)))
            conn.commit()
        conn.close()
        action = "启用" if status == 1 else "停用"
        add_runtime_log("管理员", f"{action}商户 #{merchant_id}", "warning" if status == 0 else "success")
        return {"status": "ok", "message": f"商户已{action}"}
    except Exception as e:
        print(f"[RPA] /api/admin/toggle error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/screenshot/{merchant_id}")
async def take_screenshot(merchant_id: int):
    """Take a clean screenshot of the page"""
    slot = slot_manager.slots.get(merchant_id)
    if not slot:
        return {"error": "no slot"}
    page = slot["page"]
    import base64
    ss = base64.b64encode(await page.screenshot(type="png")).decode("utf-8")
    return {"screenshot": ss}


@app.get("/click_dm/{merchant_id}")
async def click_dm(merchant_id: int):
    """Use CDP mouse to click 私信 button and screenshot"""
    slot = slot_manager.slots.get(merchant_id)
    if not slot:
        return {"error": "no slot"}
    page = slot["page"]
    cdp = slot.get("_cdp")
    import base64, asyncio
    
    # 先用 JS 找到 私信 按钮的精确坐标
    find_js = '''() => {
        const all = document.querySelectorAll('*');
        const results = [];
        for (const el of all) {
            const t = el.textContent.trim();
            if (t === '私信' && el.offsetWidth > 0 && el.childElementCount === 0) {
                const r = el.getBoundingClientRect();
                results.push({tag: el.tagName, x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height, text: t});
            }
        }
        return JSON.stringify(results);
    }'''
    r = await cdp.send("Runtime.evaluate", {"expression": f'({find_js})()', "returnByValue": True})
    import json
    found = json.loads(r.get("result", {}).get("value", "[]"))
    
    click_result = "no_target"
    if found:
        target = found[0]
        x, y = target["x"], target["y"]
        # CDP mouse click
        await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.1)
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        click_result = f"clicked at ({x},{y})"
        await asyncio.sleep(2)
    
    ss = base64.b64encode(await page.screenshot(type="png")).decode("utf-8")
    return {"found": found, "click": click_result, "screenshot": ss}


@app.post("/test_reply/{merchant_id}")
async def test_reply(merchant_id: int, request: Request):
    """直接测试发送：跳过消息监听，直接调 _cdp_reply"""
    data = await request.json()
    text = data.get("text", "这是测试消息")
    sender = data.get("sender", "")
    
    slot = slot_manager.slots.get(merchant_id)
    if not slot:
        return {"error": "no slot"}
    
    cdp = slot.get("_cdp")
    if not cdp:
        return {"error": "no CDP session"}
    
    import base64
    # 先截图（发送前）
    page = slot["page"]
    before = base64.b64encode(await page.screenshot(type="png")).decode("utf-8")
    
    # 调用 _cdp_reply
    result = await slot_manager._cdp_reply(cdp, page, sender, text)
    
    # 再截图（发送后）
    import asyncio
    await asyncio.sleep(1)
    after = base64.b64encode(await page.screenshot(type="png")).decode("utf-8")
    
    return {"result": result, "screenshot_before": before, "screenshot_after": after}


@app.post("/eval/{merchant_id}")
async def eval_js(merchant_id: int, request: Request):
    """Execute JS via CDP"""
    data = await request.json()
    js = data.get("js", "1+1")
    slot = slot_manager.slots.get(merchant_id)
    if not slot:
        return {"error": "no slot"}
    cdp = slot.get("_cdp")
    r = await cdp.send("Runtime.evaluate", {
        "expression": js,
        "returnByValue": True, "timeout": 5000
    })
    return {"result": r.get("result", {}).get("value")}

@app.get("/api_captures/{merchant_id}")
async def get_api_captures(merchant_id: int):
    """Get captured IM API request details"""
    slot = slot_manager.slots.get(merchant_id)
    if not slot:
        return {"error": "no slot"}
    return {"captures": slot.get("im_captures", [])}

@app.get("/debug/{merchant_id}")
async def debug_slot(merchant_id: int):
    """Debug: take screenshot and dump sidebar DOM"""
    slot = slot_manager.slots.get(merchant_id)
    if not slot:
        return {"error": "no slot"}
    page = slot["page"]
    try:
        # screenshot
        import base64
        ss = base64.b64encode(await page.screenshot(type="png")).decode("utf-8")

        # click DM button first
        await page.evaluate('''() => {
            const els = document.querySelectorAll('a, button, span, div');
            for (const el of els) {
                if (el.textContent.trim() === '私信' && el.offsetWidth > 0) {
                    el.click(); return true;
                }
            }
            return false;
        }''')
        import asyncio
        await asyncio.sleep(2)

        # screenshot after DM opened
        ss2 = base64.b64encode(await page.screenshot(type="png")).decode("utf-8")

        # dump DOM structure of any visible popover/sidebar
        dom = await page.evaluate('''() => {
            function dumpEl(el, depth) {
                if (depth > 4) return '';
                let cls = el.className ? (typeof el.className === 'string' ? el.className.substring(0, 80) : '') : '';
                let tag = el.tagName;
                let text = '';
                if (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3) {
                    text = el.textContent.trim().substring(0, 40);
                }
                let line = '  '.repeat(depth) + tag + (cls ? '.' + cls.split(' ')[0] : '') + (text ? ' "' + text + '"' : '');
                let result = line + '\\n';
                for (let child of el.children) {
                    result += dumpEl(child, depth + 1);
                }
                return result;
            }
            // Find the DM sidebar/popover - look for anything that appeared recently (high z-index or position fixed)
            let containers = [];
            document.querySelectorAll('div').forEach(d => {
                const style = window.getComputedStyle(d);
                const z = parseInt(style.zIndex) || 0;
                if ((z > 100 || style.position === 'fixed') && d.offsetHeight > 200 && d.innerHTML.includes('私信')) {
                    containers.push(d);
                }
            });
            if (containers.length === 0) {
                // fallback - any element containing 私信
                document.querySelectorAll('div').forEach(d => {
                    if (d.offsetHeight > 300 && d.textContent.includes('私信') && d.children.length > 3) {
                        containers.push(d);
                    }
                });
            }
            let result = 'Found ' + containers.length + ' potential DM containers\\n';
            for (let c of containers.slice(0, 2)) {
                result += dumpEl(c, 0);
                result += '---\\n';
            }
            return result;
        }''')

        return {"url": page.url, "dom_dump": dom, "screenshot_before": ss[:100] + "...", "screenshot_after_len": len(ss2)}
    except Exception as e:
        return {"error": str(e)}


# ================= OTA 热更新 API =================

# ★ 可热更新的文件列表（核心业务逻辑文件）
_UPDATABLE_FILES = ["rpa_server.py", "slot_manager.py", "ai_replier.py", "lead_extractor.py", "db_manager.py"]

def _file_hash(filepath: str) -> str:
    """计算文件 MD5"""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""

@app.get("/api/version")
async def get_version():
    """★ 返回当前版本号和所有可更新文件的 MD5 哈希"""
    # ★ OTA 急停：用于处理客户端更新重启循环等线上事故。
    # 在服务端设置环境变量 OTA_PAUSED=1，或在服务目录放置 ota_paused.flag，
    # 旧客户端会收到“无可更新内容”，从而停止反复 relaunch。
    if os.getenv("OTA_PAUSED", "0") == "1" or (_script_dir / "ota_paused.flag").exists():
        return {
            "version": APP_VERSION,
            "build": APP_BUILD,
            "files": {},
            "dist_zip": None,
            "ota_paused": True,
        }

    files = {}
    for fname in _UPDATABLE_FILES:
        fpath = _script_dir / fname
        if fpath.exists():
            files[fname] = {
                "hash": _file_hash(str(fpath)),
                "size": fpath.stat().st_size,
            }
    
    # ★ 前端 dist.zip 哈希
    dist_zip_path = _script_dir / "dist.zip"
    dist_info = None
    if dist_zip_path.exists():
        dist_info = {
            "hash": _file_hash(str(dist_zip_path)),
            "size": dist_zip_path.stat().st_size,
        }
    
    return {
        "version": APP_VERSION,
        "build": APP_BUILD,
        "files": files,
        "dist_zip": dist_info,
    }

@app.get("/api/update/file/{filename}")
async def download_update_file(filename: str):
    """★ 下载单个更新文件（仅限白名单内的文件）"""
    from fastapi.responses import FileResponse

    if filename not in _UPDATABLE_FILES:
        return JSONResponse({"error": "file not allowed"}, status_code=403)
    
    fpath = _script_dir / filename
    if not fpath.exists():
        return JSONResponse({"error": "file not found"}, status_code=404)
    
    return FileResponse(str(fpath), media_type="text/x-python", filename=filename)

@app.get("/api/update/dist")
async def download_dist_zip():
    """★ 下载前端 dist.zip（整包替换）"""
    from fastapi.responses import FileResponse
    dist_zip_path = _script_dir / "dist.zip"
    if not dist_zip_path.exists():
        return JSONResponse({"error": "dist.zip not found"}, status_code=404)
    return FileResponse(str(dist_zip_path), media_type="application/zip", filename="dist.zip")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
