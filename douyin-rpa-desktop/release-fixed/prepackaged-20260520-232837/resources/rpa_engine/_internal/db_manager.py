"""
橙子AI - 数据库对接模块
"""
import psycopg2
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime


class DatabaseManager:
    """与橙子AI系统的Supabase数据库对接"""

    POSTGRES_PARAMS = {
        "sslmode", "sslcert", "sslkey", "sslrootcert",
        "application_name", "options", "keepalives",
        "keepalives_idle", "keepalives_interval", "keepalives_count",
        "target_session_attrs",
    }

    def __init__(self, database_url: str, merchant_id: int):
        self.database_url = self._clean_url(database_url)
        self.merchant_id = merchant_id
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

    def get_agent_config(self) -> dict | None:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    'SELECT nickname, persona, knowledge_base FROM ai_agent WHERE merchant_id = %s',
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
            with self.conn.cursor() as cur:
                cur.execute('SELECT id FROM ai_agent WHERE merchant_id = %s', (self.merchant_id,))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        'UPDATE ai_agent SET nickname = %s, persona = %s, knowledge_base = %s WHERE id = %s',
                        (nickname, persona, knowledge_base, row[0])
                    )
                else:
                    cur.execute(
                        'INSERT INTO ai_agent (merchant_id, nickname, persona, knowledge_base, created_at) VALUES (%s, %s, %s, %s, %s)',
                        (self.merchant_id, nickname, persona, knowledge_base, datetime.now())
                    )
            print(f"[DB] ✅ agent config synced to DB for merchant {self.merchant_id}")
            return True
        except Exception as e:
            print(f"[DB] save_agent_config failed: {e}")
            return False

    def save_lead(self, phone=None, wechat=None, douyin_user_id=None, source="douyin_dm"):
        try:
            with self.conn.cursor() as cur:
                contact = phone or wechat
                contact_type = 1 if phone else 2
                cur.execute(
                    'SELECT id FROM customer_lead WHERE merchant_id = %s AND contact = %s',
                    (self.merchant_id, contact)
                )
                if cur.fetchone():
                    return False
                cur.execute(
                    '''INSERT INTO customer_lead (merchant_id, douyin_nickname, contact, contact_type, is_charged, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, 0, %s, %s)''',
                    (self.merchant_id, douyin_user_id or '', contact, contact_type, datetime.now(), datetime.now())
                )
                print(f"[LEAD] saved: {contact}")
                return True
        except Exception as e:
            print(f"[LEAD] save failed: {e}")
            return False

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
                return True
        except Exception:
            return False

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
                cur.execute('SELECT id FROM rpa_slot WHERE merchant_id = %s', (self.merchant_id,))
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
                    values.append(self.merchant_id)
                    cur.execute(f'UPDATE rpa_slot SET {", ".join(fields)} WHERE merchant_id = %s', values)
                else:
                    cur.execute(
                        '''INSERT INTO rpa_slot (merchant_id, status, douyin_nickname, session_path, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s)''',
                        (self.merchant_id, status, douyin_nickname or '', session_path or '', datetime.now(), datetime.now())
                    )
                print(f"[SLOT] DB updated: merchant {self.merchant_id} -> {status}")
        except Exception as e:
            print(f"[SLOT] DB update failed: {e}")

    def update_slot_status(self, status, error_message=None):
        try:
            with self.conn.cursor() as cur:
                if error_message:
                    cur.execute(
                        'UPDATE rpa_slot SET status = %s, error_message = %s, updated_at = %s WHERE merchant_id = %s',
                        (status, error_message, datetime.now(), self.merchant_id)
                    )
                else:
                    cur.execute(
                        'UPDATE rpa_slot SET status = %s, updated_at = %s WHERE merchant_id = %s',
                        (status, datetime.now(), self.merchant_id)
                    )
        except Exception:
            pass

    def update_slot_heartbeat(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    'UPDATE rpa_slot SET last_active_at = %s, updated_at = %s WHERE merchant_id = %s',
                    (datetime.now(), datetime.now(), self.merchant_id)
                )
        except Exception:
            pass
