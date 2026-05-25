"""
橙子AI - 数据库对接模块
"""
import psycopg2
import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime

DEFAULT_CLOUD_API = "http://124.223.99.238:8100"


def is_client_proxy_mode() -> bool:
    return os.getenv("GUANGCHEN_CLIENT_MODE") == "1"


def get_cloud_api_base() -> str:
    return (os.getenv("GUANGCHEN_BACKEND_API") or os.getenv("GUANGCHEN_CLOUD_API") or DEFAULT_CLOUD_API).rstrip("/")


def _client_session_file() -> Path:
    base = os.getenv("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "光宸智能客服" / "client-session.json"


def save_client_auth_token(token: str) -> None:
    if not token:
        return
    path = _client_session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": token}, ensure_ascii=False), encoding="utf-8")


def clear_client_auth_token() -> None:
    try:
        _client_session_file().unlink()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[CloudDB] clear token failed: {e}")


def get_client_auth_token() -> str:
    try:
        data = json.loads(_client_session_file().read_text(encoding="utf-8"))
        return data.get("token", "") or ""
    except Exception:
        return ""


def cloud_request(method: str, path: str, *, params=None, json_data=None, timeout: int = 8):
    url = f"{get_cloud_api_base()}{path}"
    headers = {"Content-Type": "application/json"}
    token = get_client_auth_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(
        method,
        url,
        params=params,
        json=json_data,
        headers=headers,
        timeout=timeout,
    )


class CloudDatabaseManager:
    """Client-side DB adapter: never connects to Postgres; it calls cloud APIs."""

    def __init__(self, merchant_id: int, slot_id: int | None = None):
        self.merchant_id = merchant_id
        self.slot_id = slot_id
        self.conn = True

    def connect(self):
        self.conn = True

    def close(self):
        pass

    def _params(self, extra=None):
        params = {"merchant_id": self.merchant_id}
        if self.slot_id is not None:
            params["slot_id"] = self.slot_id
        if extra:
            params.update(extra)
        return params

    def _post(self, path: str, payload: dict, timeout: int = 8) -> dict:
        try:
            res = cloud_request("POST", path, json_data=payload, timeout=timeout)
            if res.status_code == 401:
                clear_client_auth_token()
                raise PermissionError("商户登录已过期，请退出后重新登录")
            if not res.ok:
                print(f"[CloudDB] POST {path} failed: {res.status_code} {res.text[:200]}")
                return {}
            return res.json() if res.content else {}
        except PermissionError:
            raise
        except Exception as e:
            print(f"[CloudDB] POST {path} error: {e}")
            return {}

    def _get(self, path: str, params=None, timeout: int = 8) -> dict:
        try:
            res = cloud_request("GET", path, params=params, timeout=timeout)
            if res.status_code == 401:
                clear_client_auth_token()
                raise PermissionError("商户登录已过期，请退出后重新登录")
            if not res.ok:
                print(f"[CloudDB] GET {path} failed: {res.status_code} {res.text[:200]}")
                return {}
            return res.json() if res.content else {}
        except PermissionError:
            raise
        except Exception as e:
            print(f"[CloudDB] GET {path} error: {e}")
            return {}

    def get_merchant_balance(self) -> float:
        data = self._get("/api/account", {"merchant_id": self.merchant_id})
        try:
            return float(data.get("balance", 0) or 0)
        except Exception:
            return 0.0

    def get_agent_config(self) -> dict | None:
        data = self._get("/api/rpa/agent-config", self._params())
        config = data.get("config") if isinstance(data, dict) else None
        return config if config else None

    def save_agent_config(self, nickname: str, persona: str, knowledge_base: str):
        data = self._post("/api/rpa/agent-config", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
            "nickname": nickname,
            "persona": persona,
            "knowledge_base": knowledge_base,
        })
        return data.get("status") == "ok"

    def save_chat_message(self, douyin_user_id=None, content="", sender_type="user"):
        if not content:
            return False
        data = self._post("/api/rpa/chat-message", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
            "douyin_user_id": douyin_user_id,
            "content": content,
            "sender_type": sender_type,
        })
        return data.get("status") == "ok"

    def save_lead(self, phone=None, wechat=None, douyin_user_id=None, source="douyin_dm"):
        return self.save_lead_and_deduct(phone=phone, wechat=wechat, douyin_user_id=douyin_user_id, amount=0)

    def save_lead_and_deduct(self, phone=None, wechat=None, douyin_user_id=None, amount=1.0):
        data = self._post("/api/rpa/lead-and-deduct", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
            "phone": phone,
            "wechat": wechat,
            "douyin_user_id": douyin_user_id,
            "amount": amount,
        }, timeout=12)
        return bool(data.get("saved"))

    def deduct_balance(self, amount=1.0):
        return False

    def count_leads(self, by_slot: bool = False) -> int:
        data = self._get("/api/rpa/lead-count", self._params({"by_slot": int(bool(by_slot))}))
        try:
            return int(data.get("count", 0) or 0)
        except Exception:
            return 0

    def can_serve(self) -> bool:
        data = self._get("/api/rpa/can-serve", self._params())
        return bool(data.get("can_serve"))

    def upsert_rpa_slot(self, status, douyin_nickname=None, session_path=None):
        self._post("/api/rpa/slot/upsert", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
            "status": status,
            "douyin_nickname": douyin_nickname,
            "session_path": session_path,
        })

    def update_slot_status(self, status, error_message=None):
        self._post("/api/rpa/slot/status", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
            "status": status,
            "error_message": error_message,
        })

    def update_slot_heartbeat(self):
        self._post("/api/rpa/slot/heartbeat", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
        })

    def delete_rpa_slot(self):
        data = self._post("/api/rpa/slot/delete", {
            "merchant_id": self.merchant_id,
            "slot_id": self.slot_id,
        })
        return data.get("status") == "ok"


def get_database_manager(database_url: str, merchant_id: int, slot_id: int | None = None):
    if is_client_proxy_mode():
        return CloudDatabaseManager(merchant_id, slot_id)
    return DatabaseManager(database_url, merchant_id, slot_id)


class DatabaseManager:
    """与橙子AI系统的Supabase数据库对接"""

    POSTGRES_PARAMS = {
        "sslmode", "sslcert", "sslkey", "sslrootcert",
        "application_name", "options", "keepalives",
        "keepalives_idle", "keepalives_interval", "keepalives_count",
        "target_session_attrs",
    }

    def __init__(self, database_url: str, merchant_id: int, slot_id: int | None = None):
        self.database_url = self._clean_url(database_url)
        self.merchant_id = merchant_id
        self.slot_id = slot_id
        self.conn = None

    def _clean_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            clean_params = {
                k: v[0] for k, v in params.items()
                if k in self.POSTGRES_PARAMS
            }
            clean_query = urlencode(clean_params) if clean_params else ""
            cleaned = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, clean_query, parsed.fragment
            ))
            return cleaned
        return url

    def connect(self):
        if not self.database_url:
            print("[DB] DATABASE_URL 为空，跳过连接（离线模式）")
            return
        try:
            self.conn = psycopg2.connect(self.database_url, connect_timeout=3)
            self.conn.autocommit = True
            print("[DB] connected OK")
        except Exception as e:
            print(f"[DB] connect FAILED: {e}")
            self.conn = None  # 确保 conn 为 None，不再 raise

    def close(self):
        if self.conn:
            self.conn.close()

    def get_merchant_balance(self) -> float:
        try:
            with self.conn.cursor() as cur:
                cur.execute('SELECT balance FROM merchant WHERE id = %s', (self.merchant_id,))
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def _ensure_ai_agent_slot_schema(self) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'ai_agent' AND column_name = 'slot_id'
                       LIMIT 1"""
                )
                if cur.fetchone():
                    return True
                cur.execute('ALTER TABLE ai_agent ADD COLUMN IF NOT EXISTS slot_id INTEGER')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_ai_agent_merchant_slot ON ai_agent(merchant_id, slot_id)')
            return True
        except Exception as e:
            print(f"[DB] ensure ai_agent slot schema failed: {e}")
            return False

    def get_agent_config(self) -> dict | None:
        try:
            has_slot = self._ensure_ai_agent_slot_schema() if self.slot_id is not None else False
            with self.conn.cursor() as cur:
                if has_slot:
                    cur.execute(
                        '''SELECT nickname, persona, knowledge_base FROM ai_agent
                           WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0)
                           ORDER BY id DESC LIMIT 1''',
                        (self.merchant_id, self.slot_id)
                    )
                else:
                    cur.execute(
                        'SELECT nickname, persona, knowledge_base FROM ai_agent WHERE merchant_id = %s ORDER BY id DESC LIMIT 1',
                        (self.merchant_id,)
                    )
                row = cur.fetchone()
                if row:
                    return {"nickname": row[0], "persona": row[1], "knowledge_base": row[2]}
                return None
        except Exception as e:
            print(f"[DB] get_agent_config failed: {e}")
            return None

    def save_agent_config(self, nickname: str, persona: str, knowledge_base: str):
        """★ 将本地配置回传到远程数据库（异步调用，失败不影响本地）"""
        if not self.conn:
            return False
        try:
            has_slot = self._ensure_ai_agent_slot_schema() if self.slot_id is not None else False
            with self.conn.cursor() as cur:
                if has_slot:
                    cur.execute(
                        'SELECT id FROM ai_agent WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0) ORDER BY id DESC LIMIT 1',
                        (self.merchant_id, self.slot_id)
                    )
                else:
                    cur.execute('SELECT id FROM ai_agent WHERE merchant_id = %s ORDER BY id DESC LIMIT 1', (self.merchant_id,))
                row = cur.fetchone()
                if row:
                    if has_slot:
                        cur.execute(
                            'UPDATE ai_agent SET slot_id = %s, nickname = %s, persona = %s, knowledge_base = %s WHERE id = %s',
                            (self.slot_id, nickname, persona, knowledge_base, row[0])
                        )
                    else:
                        cur.execute(
                            'UPDATE ai_agent SET nickname = %s, persona = %s, knowledge_base = %s WHERE id = %s',
                            (nickname, persona, knowledge_base, row[0])
                        )
                else:
                    if has_slot:
                        cur.execute(
                            'INSERT INTO ai_agent (merchant_id, slot_id, nickname, persona, knowledge_base, created_at) VALUES (%s, %s, %s, %s, %s, %s)',
                            (self.merchant_id, self.slot_id, nickname, persona, knowledge_base, datetime.now())
                        )
                    else:
                        cur.execute(
                            'INSERT INTO ai_agent (merchant_id, nickname, persona, knowledge_base, created_at) VALUES (%s, %s, %s, %s, %s)',
                            (self.merchant_id, nickname, persona, knowledge_base, datetime.now())
                        )
            print(f"[DB] agent config synced to DB for merchant {self.merchant_id}, slot {self.slot_id}")
            return True
        except Exception as e:
            print(f"[DB] save_agent_config failed: {e}")
            return False

    def save_chat_message(self, douyin_user_id=None, content="", sender_type="user"):
        """保存消息监管记录到正式库，供前端刷新/重启后继续查看。"""
        if not self.conn or not content:
            return False
        try:
            user_id = douyin_user_id or "unknown"
            now = datetime.now()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM chat_session
                    WHERE merchant_id = %s
                      AND COALESCE(slot_id, 0) = COALESCE(%s, 0)
                      AND user_id = %s
                    """,
                    (self.merchant_id, self.slot_id, user_id)
                )
                row = cur.fetchone()
                if row:
                    session_id = row[0]
                    cur.execute(
                        "UPDATE chat_session SET updated_at = %s WHERE id = %s",
                        (now, session_id)
                    )
                else:
                    cur.execute(
                        """INSERT INTO chat_session (merchant_id, slot_id, user_id, status, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                        (self.merchant_id, self.slot_id, user_id, "active", now, now)
                    )
                    session_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO chat_message (session_id, sender_type, content, created_at) VALUES (%s, %s, %s, %s)",
                    (session_id, sender_type, content, now)
                )
            return True
        except Exception as e:
            print(f"[DB] save_chat_message failed: {e}")
            return False

    def save_lead(self, phone=None, wechat=None, douyin_user_id=None, source="douyin_dm"):
        try:
            with self.conn.cursor() as cur:
                contact = phone or wechat
                if not contact:
                    return False
                contact_type = 1 if phone else 2
                cur.execute(
                    'SELECT id FROM customer_lead WHERE merchant_id = %s AND contact = %s',
                    (self.merchant_id, contact)
                )
                if cur.fetchone():
                    return False
                cur.execute(
                    '''INSERT INTO customer_lead (merchant_id, slot_id, douyin_nickname, contact, contact_type, is_charged, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, 0, %s, %s)''',
                    (self.merchant_id, self.slot_id, douyin_user_id or '', contact, contact_type, datetime.now(), datetime.now())
                )
                print(f"[LEAD] saved: {contact}")
                return True
        except Exception as e:
            print(f"[LEAD] save failed: {e}")
            return False

    def save_lead_and_deduct(self, phone=None, wechat=None, douyin_user_id=None, amount=1.0):
        if not self.conn:
            return False

        contact = phone or wechat
        if not contact:
            return False

        old_autocommit = self.conn.autocommit
        try:
            self.conn.autocommit = False
            with self.conn.cursor() as cur:
                cur.execute(
                    'SELECT id FROM customer_lead WHERE merchant_id = %s AND contact = %s',
                    (self.merchant_id, contact)
                )
                if cur.fetchone():
                    self.conn.rollback()
                    return False

                cur.execute(
                    'UPDATE merchant SET balance = balance - %s WHERE id = %s AND balance >= %s AND status = 1',
                    (amount, self.merchant_id, amount)
                )
                if cur.rowcount != 1:
                    self.conn.rollback()
                    return False

                contact_type = 1 if phone else 2
                now = datetime.now()
                cur.execute(
                    '''INSERT INTO customer_lead (merchant_id, slot_id, douyin_nickname, contact, contact_type, is_charged, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, 1, %s, %s)''',
                    (self.merchant_id, self.slot_id, douyin_user_id or '', contact, contact_type, now, now)
                )
            self.conn.commit()
            print(f"[LEAD] saved and charged: {contact}")
            return True
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            print(f"[LEAD] save and charge failed: {e}")
            return False
        finally:
            self.conn.autocommit = old_autocommit

    def deduct_balance(self, amount=1.0):
        try:
            balance = self.get_merchant_balance()
            if balance < amount:
                return False
            with self.conn.cursor() as cur:
                cur.execute(
                    'UPDATE merchant SET balance = balance - %s WHERE id = %s AND balance >= %s',
                    (amount, self.merchant_id, amount)
                )
                return cur.rowcount == 1
        except Exception:
            return False

    def count_leads(self, by_slot: bool = False) -> int:
        if not self.conn:
            return 0
        try:
            with self.conn.cursor() as cur:
                if by_slot and self.slot_id is not None:
                    cur.execute(
                        'SELECT COUNT(id) FROM customer_lead WHERE merchant_id = %s AND slot_id = %s',
                        (self.merchant_id, self.slot_id)
                    )
                else:
                    cur.execute('SELECT COUNT(id) FROM customer_lead WHERE merchant_id = %s', (self.merchant_id,))
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def can_serve(self) -> bool:
        if not self.conn:
            return True # 允许本地离线测试
        try:
            with self.conn.cursor() as cur:
                cur.execute('SELECT balance, status FROM merchant WHERE id = %s', (self.merchant_id,))
                row = cur.fetchone()
                if row:
                    balance, status = float(row[0]), row[1]
                    if status != 1 or balance <= 0:
                        return False
                    return True
                return False
        except Exception:
            return True # 如果查询失败也暂时放行，保证测试顺畅

    # ========== RPA slot ==========

    def upsert_rpa_slot(self, status, douyin_nickname=None, session_path=None):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    '''
                    SELECT id FROM rpa_slot
                    WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0)
                    ORDER BY updated_at DESC NULLS LAST, id DESC
                    LIMIT 1
                    ''',
                    (self.merchant_id, self.slot_id)
                )
                existing = cur.fetchone()
                if existing:
                    fields = ['status = %s', 'updated_at = %s']
                    values = [status, datetime.now()]
                    if douyin_nickname is not None:
                        fields.append('douyin_nickname = %s')
                        values.append(douyin_nickname)
                    if session_path is not None:
                        fields.append('session_path = %s')
                        values.append(session_path)
                    if status == 'running':
                        fields.append('last_active_at = %s')
                        values.append(datetime.now())
                    values.append(existing[0])
                    cur.execute(f'UPDATE rpa_slot SET {", ".join(fields)} WHERE id = %s', values)
                else:
                    cur.execute(
                        '''INSERT INTO rpa_slot (merchant_id, slot_id, status, douyin_nickname, session_path, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                        (self.merchant_id, self.slot_id, status, douyin_nickname or '', session_path or '', datetime.now(), datetime.now())
                    )
                print(f"[SLOT] DB updated: merchant {self.merchant_id}, slot {self.slot_id} -> {status}")
        except Exception as e:
            print(f"[SLOT] DB update failed: {e}")

    def update_slot_status(self, status, error_message=None):
        try:
            with self.conn.cursor() as cur:
                if error_message:
                    cur.execute(
                        '''
                        UPDATE rpa_slot SET status = %s, error_message = %s, updated_at = %s
                        WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0)
                        ''',
                        (status, error_message, datetime.now(), self.merchant_id, self.slot_id)
                    )
                else:
                    cur.execute(
                        '''
                        UPDATE rpa_slot SET status = %s, updated_at = %s
                        WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0)
                        ''',
                        (status, datetime.now(), self.merchant_id, self.slot_id)
                    )
        except Exception:
            pass

    def update_slot_heartbeat(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    '''
                    UPDATE rpa_slot SET last_active_at = %s, updated_at = %s
                    WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0)
                    ''',
                    (datetime.now(), datetime.now(), self.merchant_id, self.slot_id)
                )
        except Exception:
            pass

    def delete_rpa_slot(self):
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM rpa_slot WHERE merchant_id = %s AND COALESCE(slot_id, 0) = COALESCE(%s, 0)",
                    (self.merchant_id, self.slot_id)
                )
            return True
        except Exception as e:
            print(f"[SLOT] DB delete failed: {e}")
            return False
