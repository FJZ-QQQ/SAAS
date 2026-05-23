"""
橙子AI - 多商户坑位管理器 v10
核心架构:
- CDP Network.enable 监听 WebSocket 帧（实时私信）
- 监听循环在独立 Python 线程中运行（完全脱离 Playwright 事件循环）
- 所有 print 使用 flush=True 确保在子进程中可见
- 绝不在循环中调用任何 Playwright API（page.goto/evaluate/reload 全部会 hang）
"""
import asyncio
import base64
import os
import sys
import re
import time
import threading
from datetime import datetime
from playwright.async_api import async_playwright
from ai_replier import AIReplier
from lead_extractor import LeadExtractor
from db_manager import DatabaseManager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(SCRIPT_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


def log(msg):
    """确保所有输出立即刷新 + 写入日志文件（带自动轮转）"""
    print(msg, flush=True)
    try:
        log_file = os.path.join(SCRIPT_DIR, "debug.log")
        # ★ 日志轮转：超过 5MB 自动归档
        if os.path.exists(log_file) and os.path.getsize(log_file) > 5 * 1024 * 1024:
            old_file = os.path.join(SCRIPT_DIR, "debug.log.old")
            try:
                if os.path.exists(old_file):
                    os.remove(old_file)
                os.rename(log_file, old_file)
            except:
                pass
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass


class SlotManager:
    def __init__(self):
        self.slots = {}
        self.playwright = None
        self._pw_lock = asyncio.Lock()
        # ★ 今日统计
        self._today_stats = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "messages": 0,      # 今日处理消息数
            "leads": 0,         # 今日留资数
            "ai_success": 0,    # AI回复成功次数
            "ai_fail": 0,       # AI回复失败次数
            "response_times": [],  # 响应时间列表（秒）
        }

    def _check_day_reset(self):
        """零点自动重置今日统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._today_stats["date"] != today:
            log(f"[STATS] 日期变更 {self._today_stats['date']} → {today}，统计已重置")
            self._today_stats = {
                "date": today, "messages": 0, "leads": 0,
                "ai_success": 0, "ai_fail": 0, "response_times": [],
            }

    def get_today_stats(self):
        """获取今日统计数据"""
        self._check_day_reset()
        s = self._today_stats
        total_ai = s["ai_success"] + s["ai_fail"]
        avg_time = round(sum(s["response_times"][-100:]) / max(1, len(s["response_times"][-100:])), 2)
        lead_rate = round(s["leads"] / max(1, s["messages"]) * 100, 1)
        ai_rate = round(s["ai_success"] / max(1, total_ai) * 100, 1)
        return {
            "date": s["date"],
            "today_messages": s["messages"],
            "today_leads": s["leads"],
            "lead_rate": lead_rate,
            "ai_success_rate": ai_rate,
            "avg_response_time": avg_time,
        }

    async def _ensure_playwright(self):
        async with self._pw_lock:
            if self.playwright is None:
                self.playwright = await async_playwright().start()

    def _session_dir(self, mid: int) -> str:
        path = os.path.join(SESSIONS_DIR, f"merchant_{mid}")
        os.makedirs(path, exist_ok=True)
        return path

    def _get_db(self, mid: int) -> DatabaseManager:
        db_url = os.getenv("DATABASE_URL", "")
        db = DatabaseManager(db_url, mid)
        db.connect()
        return db

    async def load_session_metadata(self):
        """★ 启动时只加载已有会话的元数据（不打开浏览器）"""
        if not os.path.exists(SESSIONS_DIR):
            return
        
        loaded = 0
        for entry in os.listdir(SESSIONS_DIR):
            if not entry.startswith("merchant_"):
                continue
            try:
                mid = int(entry.replace("merchant_", ""))
            except ValueError:
                continue
            
            session_dir = os.path.join(SESSIONS_DIR, entry)
            if not os.path.isdir(session_dir):
                continue
            if mid in self.slots:
                continue
            
            # ★ 只注册元数据，不启动浏览器
            self.slots[mid] = {
                "context": None, "page": None,
                "status": "bound",  # 标记为已绑定但未启动
                "nickname": None,
                "created_at": datetime.now(),
                "im_messages": [], "runtime_messages": [],
                "_last_heartbeat": datetime.now().isoformat(),
                "_last_error": None,
                "_error_time": None,
                "_recovery_count": 0,
            }
            loaded += 1
            log(f"[METADATA] 加载已有会话记录: merchant_{mid}")
        
        if loaded > 0:
            log(f"[METADATA] ★ 共加载 {loaded} 个账号记录（浏览器未启动）")

    async def _restore_browser_for_slot(self, merchant_id: int):
        """★ 按需恢复单个 slot 的浏览器会话（用户点「启动」时调用）"""
        session_dir = os.path.join(SESSIONS_DIR, f"merchant_{merchant_id}")
        if not os.path.isdir(session_dir):
            raise Exception(f"会话目录不存在: merchant_{merchant_id}")
        
        await self._ensure_playwright()
        
        # ★ 优先使用系统默认浏览器（从注册表读取）
        browser_exe = None
        try:
            import winreg
            # 读取默认浏览器的 ProgId
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]
            log(f"[BROWSER] 系统默认浏览器 ProgId: {prog_id}")
            
            # 从 ProgId 找到 exe 路径
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
                    cmd = winreg.QueryValueEx(key, "")[0]
                    # 提取 exe 路径（去掉引号和参数）
                    import shlex
                    if cmd.startswith('"'):
                        default_exe = cmd.split('"')[1]
                    else:
                        default_exe = cmd.split(' ')[0]
                    
                    # 检查是否是 Chromium 内核浏览器（Playwright 只支持 Chromium）
                    chromium_keywords = ['chrome', 'msedge', 'edge', 'brave', 'chromium', 'vivaldi', 'opera']
                    if any(kw in default_exe.lower() for kw in chromium_keywords) and os.path.exists(default_exe):
                        browser_exe = default_exe
                        log(f"[BROWSER] ✅ 使用默认浏览器: {browser_exe}")
                    else:
                        log(f"[BROWSER] 默认浏览器 {default_exe} 不是 Chromium 内核，跳过")
            except Exception as e:
                log(f"[BROWSER] 读取默认浏览器路径失败: {e}")
        except Exception as e:
            log(f"[BROWSER] 注册表读取失败: {e}")
        
        # 如果默认浏览器不可用，按优先级搜索已安装的 Chromium 浏览器
        if not browser_exe:
            fallback_paths = [
                # Edge（Windows 10/11 自带，保证存在）
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                # Chrome
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
            for p in fallback_paths:
                if os.path.exists(p):
                    browser_exe = p
                    log(f"[BROWSER] ✅ 使用备选浏览器: {browser_exe}")
                    break
        
        if not browser_exe:
            log("[BROWSER] ⚠ 未找到任何浏览器，将使用 Playwright 内置 Chromium")
        
        stealth_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run", "--no-default-browser-check", "--disable-infobars",
            f"--window-size=1280,800",
            f"--window-position={100 + merchant_id * 50},{100 + merchant_id * 50}",
        ]
        launch_kwargs = {
            "user_data_dir": session_dir,
            "headless": False,
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "locale": "zh-CN", "timezone_id": "Asia/Shanghai",
            "args": stealth_args,
            "ignore_default_args": ["--enable-automation"],
        }
        if browser_exe:
            launch_kwargs["executable_path"] = browser_exe
        
        context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 导航到私信页
        try:
            await page.goto("https://creator.douyin.com/creator-micro/data/following/chat", wait_until="commit", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)
        
        # 更新 slot
        self.slots[merchant_id]["context"] = context
        self.slots[merchant_id]["page"] = page
        log(f"[RESTORE] ✅ merchant_{merchant_id} 浏览器已恢复")

    async def auto_restore_sessions(self):
        """★ 启动时自动恢复已有的登录会话（免重新扫码）"""
        if not os.path.exists(SESSIONS_DIR):
            return
        
        restored = 0
        for entry in os.listdir(SESSIONS_DIR):
            if not entry.startswith("merchant_"):
                continue
            try:
                mid = int(entry.replace("merchant_", ""))
            except ValueError:
                continue
            
            session_dir = os.path.join(SESSIONS_DIR, entry)
            # 检查是否有 cookies 目录（Chromium 的 session 标志）
            if not os.path.isdir(session_dir):
                continue
            # 如果已经在 slots 中，跳过
            if mid in self.slots:
                continue
            
            log(f"[RESTORE] 发现已有会话: merchant_{mid}，正在恢复...")
            try:
                await self._ensure_playwright()
                
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
                ]
                chrome_exe = None
                for p in chrome_paths:
                    if os.path.exists(p):
                        chrome_exe = p
                        break
                
                stealth_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run", "--no-default-browser-check", "--disable-infobars",
                    f"--window-size=1280,800",
                    f"--window-position={100 + mid * 50},{100 + mid * 50}",
                ]
                launch_kwargs = {
                    "user_data_dir": session_dir,
                    "headless": False,
                    "viewport": {"width": 1280, "height": 800},
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "locale": "zh-CN", "timezone_id": "Asia/Shanghai",
                    "args": stealth_args,
                    "ignore_default_args": ["--enable-automation"],
                }
                if chrome_exe:
                    launch_kwargs["executable_path"] = chrome_exe
                
                context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
                page = context.pages[0] if context.pages else await context.new_page()
                
                # 导航到私信页
                try:
                    await page.goto("https://creator.douyin.com/creator-micro/data/following/chat", wait_until="commit", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(3)
                
                # 检查登录状态
                real = await self._verify_real_login(page, context)
                
                self.slots[mid] = {
                    "context": context, "page": page,
                    "status": "bound" if real else "login_expired",
                    "nickname": "douyin_user" if real else None,
                    "created_at": datetime.now(),
                    "im_messages": [], "runtime_messages": [],
                    "_last_heartbeat": datetime.now().isoformat(),
                    "_last_error": None if real else "登录已过期，请重新扫码",
                    "_error_time": None if real else datetime.now().isoformat(),
                    "_recovery_count": 0,
                }
                
                if real:
                    log(f"[RESTORE] ✅ merchant_{mid} 登录有效，已恢复为 bound 状态")
                    restored += 1
                else:
                    log(f"[RESTORE] ⚠ merchant_{mid} 登录已过期")
                    
            except Exception as e:
                log(f"[RESTORE] ✗ merchant_{mid} 恢复失败: {e}")
        
        if restored > 0:
            log(f"[RESTORE] ★ 共恢复 {restored} 个已登录会话")

    # ========== BIND ==========

    async def create_bind_slot(self, merchant_id: int) -> dict:
        await self._ensure_playwright()

        if merchant_id in self.slots:
            try:
                old = self.slots[merchant_id]
                old["status"] = "stopped"
                await old["context"].close()
            except Exception:
                pass
            del self.slots[merchant_id]

        session_dir = self._session_dir(merchant_id)
        try:
            db = self._get_db(merchant_id)
            db.upsert_rpa_slot("binding", session_path=session_dir)
            db.close()
        except Exception as e:
            log(f"[SLOT] DB write failed: {e}")

        # ★ 每个商户使用完全独立的 Playwright 浏览器实例
        import subprocess
        
        # 查找系统 Chrome 可执行文件路径
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        chrome_exe = None
        for p in chrome_paths:
            if os.path.exists(p):
                chrome_exe = p
                break
        
        # 通用反检测参数
        stealth_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            f"--window-size=1280,800",
            f"--window-position={100 + merchant_id * 50},{100 + merchant_id * 50}",  # 每个窗口错开位置
        ]
        
        launch_kwargs = {
            "user_data_dir": session_dir,
            "headless": False,
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "args": stealth_args,
            "ignore_default_args": ["--enable-automation"],
        }
        
        if chrome_exe:
            launch_kwargs["executable_path"] = chrome_exe
            # launch_kwargs["channel"] = "chrome"
            log(f"[SLOT {merchant_id}] Using system Chrome: {chrome_exe}")
        else:
            log(f"[SLOT {merchant_id}] Using Playwright built-in Chromium")
        
        try:
            context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            log(f"[SLOT {merchant_id}] Chrome launch failed: {e}. Trying built-in...")
            launch_kwargs.pop("executable_path", None)
            context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        
        log(f"[SLOT {merchant_id}] ✅ Independent browser instance created (session: {session_dir})")

        page = context.pages[0] if context.pages else await context.new_page()
        self.slots[merchant_id] = {
            "context": context, "page": page, "status": "binding",
            "nickname": None, "created_at": datetime.now(),
            "im_messages": [], "runtime_messages": [],
        }

        # 导航到抖音创作者中心私信页
        try:
            await page.goto("https://creator.douyin.com/creator-micro/data/following/chat", wait_until="commit", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)

        real = await self._verify_real_login(page, context)
        if real:
            nickname = "douyin_user"
            self.slots[merchant_id]["status"] = "bound"
            self.slots[merchant_id]["nickname"] = nickname
            log(f"[SLOT {merchant_id}] login confirmed")
            try:
                db = self._get_db(merchant_id)
                db.upsert_rpa_slot("running", douyin_nickname=nickname, session_path=session_dir)
                db.close()
            except Exception:
                pass
            return {"status": "already_logged_in", "nickname": nickname}

        await self._trigger_login(page)
        await asyncio.sleep(2)
        qr = await self._capture_qr_screenshot(page)
        return {"status": "waiting_scan", "qr_image": qr}

    async def check_bind_status(self, merchant_id: int) -> dict:
        slot = self.slots.get(merchant_id)
        if not slot:
            return {"status": "not_found"}
        if slot["status"] in ("bound", "running"):
            return {"status": "success", "nickname": slot.get("nickname", "")}
        if slot["status"] != "binding":
            return {"status": slot["status"]}

        page, context = slot["page"], slot["context"]
        try:
            real = await self._verify_real_login(page, context)
        except Exception:
            return {"status": "error", "message": "browser error"}

        if real:
            nickname = "douyin_user"
            slot["status"] = "bound"
            slot["nickname"] = nickname
            try:
                db = self._get_db(merchant_id)
                db.upsert_rpa_slot("running", douyin_nickname=nickname, session_path=self._session_dir(merchant_id))
                db.close()
            except Exception:
                pass
            return {"status": "success", "nickname": nickname}

        elapsed = (datetime.now() - slot["created_at"]).total_seconds()
        if elapsed > 180:
            return {"status": "timeout"}
        qr = await self._capture_qr_screenshot(page)
        return {"status": "waiting", "qr_image": qr}

    async def _verify_real_login(self, page, context) -> bool:
        """真正验证抖音是否已登录（不能只看 cookie，要看页面内容）"""
        try:
            # 第1步：检查页面内容，确认不是登录页面
            check_js = '''() => {
                const body = document.body ? document.body.innerText : '';
                const isLoginPage = body.includes('扫码登录') || body.includes('验证码登录') 
                    || body.includes('密码登录') || body.includes('登录/注册');
                const hasChat = body.includes('私信') || body.includes('消息') 
                    || body.includes('全部') || body.includes('陌生人');
                return JSON.stringify({isLoginPage, hasChat, bodyLen: body.length});
            }'''
            result = await page.evaluate(check_js)
            import json as _json2
            info = _json2.loads(result) if isinstance(result, str) else result
            
            if info.get("isLoginPage"):
                log(f"[LOGIN] ✗ page shows login form (session expired)")
                return False
            
            if info.get("hasChat"):
                log(f"[LOGIN] ✓ page has chat elements, login valid")
                return True
            
            # 有 cookie 但页面不确定（可能 session 已过期或页面还在跳转），保守返回 false
            log(f"[LOGIN] ? has cookie but no chat elements (bodyLen={info.get('bodyLen')}), treating as NOT logged in")
            return False
            
        except Exception as e:
            log(f"[LOGIN] error: {e}")
            return False

    # ========== MONITORING ==========

    async def start_monitoring(self, merchant_id: int):
        slot = self.slots.get(merchant_id)
        if not slot:
            raise Exception("not bound")
        if slot["status"] == "running" and slot.get("_monitor_thread"):
            return

        # ★ 如果是从元数据加载的（没有浏览器），先恢复浏览器会话
        if slot.get("context") is None:
            log(f"[SLOT {merchant_id}] 浏览器未启动，正在恢复会话...")
            await self._restore_browser_for_slot(merchant_id)
            slot = self.slots[merchant_id]  # 重新获取更新后的 slot

        context = slot["context"]
        page = slot["page"]

        if not context or not page:
            raise Exception("浏览器启动失败，请尝试重新绑定账号")

        # ★ 启动前验证：抖音是否真的已登录？
        real_login = await self._verify_real_login(page, context)
        if not real_login:
            log(f"[SLOT {merchant_id}] ✗ cannot start: Douyin not logged in!")
            slot["status"] = "login_expired"
            slot["_last_error"] = "登录已过期，请重新扫码"
            slot["_error_time"] = datetime.now().isoformat()
            raise Exception("抖音登录已过期，请删除账号后重新扫码绑定")

        # ★ 关键：先导航到私信页面！不管当前在哪个页面
        CHAT_URL = "https://creator.douyin.com/creator-micro/data/following/chat"
        try:
            current_url = page.url
            if "/following/chat" not in current_url:
                log(f"[SLOT {merchant_id}] navigating to chat page...")
                await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                log(f"[SLOT {merchant_id}] ✅ now on chat page")
        except Exception as e:
            log(f"[SLOT {merchant_id}] chat navigation error: {e}")

        # 建立 CDP 会话
        cdp = await context.new_cdp_session(page)
        slot["_cdp"] = cdp

        # 启用 Network 域
        await cdp.send("Network.enable")

        # 设置 CDP 事件监听
        self._setup_cdp_listeners(cdp, slot, merchant_id)

        # 页面已经在 douyin.com（bind 阶段已导航）
        log(f"[SLOT {merchant_id}] CDP ready, starting monitor thread...")

        # ★ 保存主事件循环引用（Playwright 对象必须在此循环上运行）
        slot["_event_loop"] = asyncio.get_running_loop()

        # 由于使用的是创作者平台的独立私信页，无需再“寻找悬浮窗”预打开面板
        slot["_im_opened"] = True



        slot["status"] = "running"
        try:
            db = self._get_db(merchant_id)
            db.update_slot_status("running")
            db.close()
        except Exception:
            pass

        # 在独立线程中启动监听循环
        t = threading.Thread(
            target=self._monitor_thread_entry,
            args=(merchant_id,),
            daemon=True,
            name=f"monitor-{merchant_id}"
        )
        t.start()
        slot["_monitor_thread"] = t
        log(f"[SLOT {merchant_id}] MONITORING STARTED")

    def _setup_cdp_listeners(self, cdp, slot, merchant_id):
        """设置 CDP 事件监听器"""

        # HTTP 响应 URL 记录
        def on_response_received(params):
            url = params.get("response", {}).get("url", "")
            if "imapi.douyin.com" in url:
                path = url.split("?")[0].split("douyin.com")[-1]
                log(f"[IM-HTTP] {path}")

        cdp.on("Network.responseReceived", on_response_received)

        # ★ 捕获完整请求信息（headers, body）用于 API 逆向
        def on_request_will_be_sent(params):
            url = params.get("request", {}).get("url", "")
            if "imapi.douyin.com" in url:
                req = params.get("request", {})
                path = url.split("?")[0].split("douyin.com")[-1]
                
                if any(k in url for k in ["/v1/message/send", "/v1/message/get_user_message", 
                                           "/v1/conversation/list", "/v1/stranger/get_conversation"]):
                    capture = {
                        "url": url,
                        "path": path,
                        "method": req.get("method"),
                        "headers": req.get("headers", {}),
                        "postData": req.get("postData", ""),
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    if "im_captures" not in slot:
                        slot["im_captures"] = []
                    slot["im_captures"].append(capture)
                    if len(slot["im_captures"]) > 10:
                        slot["im_captures"] = slot["im_captures"][-10:]
                    
                    log(f"[IM-CAPTURE] {req.get('method')} {path} headers={len(req.get('headers',{}))} body={len(req.get('postData',''))}")

        cdp.on("Network.requestWillBeSent", on_request_will_be_sent)

        # WebSocket 帧（核心实时消息通道）
        ws_count = [0]

        def on_ws_frame(params):
            try:
                payload = params.get("response", {}).get("payloadData", "")
                if not payload:
                    return

                ws_count[0] += 1

                # 提取中文文本
                chinese = re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]{2,}', payload)

                # base64 解码尝试
                if not chinese:
                    try:
                        decoded = base64.b64decode(payload).decode("utf-8", errors="ignore")
                        chinese = re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]{2,}', decoded)
                    except Exception:
                        pass

                if chinese:
                    useful = [t for t in chinese if len(t) >= 2 and t not in
                              {"抖音", "下载", "客户端", "更多", "关注", "已关注"}]
                    if useful:
                        # 提取发送者（"X 私信了你 Y" 模式）
                        sender = None
                        for i, t in enumerate(useful):
                            if "私信了你" in t and i > 0:
                                sender = useful[i - 1]
                                break
                        
                        # ★ 只在有 sender 信息时才加入队列（跳过无 sender 的回声帧）
                        if sender:
                            log(f"[WS] #{ws_count[0]}: {useful[:5]} (from: {sender})")
                            slot["im_messages"].append({
                                "source": "websocket",
                                "texts": useful,
                                "sender": sender,
                                "timestamp": datetime.now().isoformat()
                            })
                        elif ws_count[0] % 50 == 0:
                            log(f"[WS] #{ws_count[0]}: {useful[:3]} (no sender, skipped)")

                # 周期性 debug
                if ws_count[0] % 200 == 1:
                    log(f"[WS-DBG] #{ws_count[0]}, len={len(payload)}")

            except Exception:
                pass

        cdp.on("Network.webSocketFrameReceived", on_ws_frame)

        def on_ws_created(params):
            url = params.get("url", "")
            if "frontier" in url or "im" in url:
                log(f"[WS] connected: {url[:80]}")

        cdp.on("Network.webSocketCreated", on_ws_created)
        log(f"[SLOT {merchant_id}] CDP listeners ready")

    # ========== THREAD LOOP ==========

    def _monitor_thread_entry(self, merchant_id: int):
        """监听循环入口（在独立线程中运行）— 每个商户拥有自己的独立事件循环！"""
        slot = self.slots.get(merchant_id)
        if not slot:
            return

        coze_key = os.getenv("COZE_API_KEY", "")
        coze_bot = os.getenv("COZE_BOT_ID", "")
        log(f"[LOOP-{merchant_id}] COZE keys: key={'YES' if coze_key else 'MISSING!!!'}, bot={'YES' if coze_bot else 'MISSING!!!'}")

        ai = AIReplier(coze_key, coze_bot)
        
        # ★ 配置实时加载函数（每次回复时重新读取，确保修改立即生效）
        def _load_live_config():
            cfg = {"nickname": "小橙", "persona": "", "knowledge_base": ""}
            try:
                config_dir = os.path.join(SCRIPT_DIR, "agent_configs")
                config_file = os.path.join(config_dir, f"store_{merchant_id}.json")
                if not os.path.exists(config_file):
                    config_file = os.path.join(SCRIPT_DIR, "agent_config.json")
                if os.path.exists(config_file):
                    import json as _json
                    with open(config_file, "r", encoding="utf-8") as f:
                        local_config = _json.load(f)
                        cfg = {**cfg, **local_config}
                    log(f"[LOOP-{merchant_id}] Config: nickname={cfg.get('nickname')}, persona={bool(cfg.get('persona'))}, kb_len={len(cfg.get('knowledge_base',''))}")
                else:
                    log(f"[LOOP-{merchant_id}] No config file found, using defaults")
            except Exception as e:
                log(f"[LOOP-{merchant_id}] config load error: {e}")
            return cfg
        
        # 初始加载一次（用于日志确认）
        config = _load_live_config()

        # 初始化消息记录数组，用于前端的消息监控页面
        if "runtime_messages" not in slot:
            slot["runtime_messages"] = []

        # processed: dict[sender_name -> last_known_msg] 记录每个会话最后已知的消息
        processed = {}
        preview_cache = {}  # 记录左侧列表的预览文本，防止盲目点击跳来跳去
        sent_messages = set()
        sender_cooldown = {}
        warmup_done = False
        loop_count = 0
        send_count_hour = 0  # 每小时发送计数
        hour_start = time.time()
        log(f"[LOOP-{merchant_id}] ★ started (thread={threading.current_thread().name})")
        # ★ 初始化健康状态字段
        slot["_last_heartbeat"] = datetime.now().isoformat()
        slot["_last_error"] = None
        slot["_error_time"] = None
        slot["_recovery_count"] = slot.get("_recovery_count", 0)

        # ★ Playwright 对象必须在创建它们的事件循环上运行！
        main_loop = slot.get("_event_loop")
        if not main_loop:
            log(f"[LOOP-{merchant_id}] ✗ FATAL: no event loop!")
            return

        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 5
        HEALTH_CHECK_INTERVAL = 6  # 每 6 个循环做一次健康检测

        try:
            while slot.get("status") in ("running", "login_expired"):
                # ★ 如果状态是 login_expired，只做健康检查等待用户重新登录
                if slot.get("status") == "login_expired":
                    time.sleep(10)
                    try:
                        page = slot.get("page")
                        cdp = slot.get("_cdp")
                        if page and cdp:
                            hf = asyncio.run_coroutine_threadsafe(
                                self._health_check(page, cdp, merchant_id), main_loop
                            )
                            health = hf.result(timeout=10)
                            if health == 'ok':
                                log(f"[LOOP-{merchant_id}] ✅ login restored! resuming monitoring")
                                slot["status"] = "running"
                                slot["_last_error"] = None
                                consecutive_errors = 0
                    except Exception:
                        pass
                    continue

                loop_count += 1

                # ★ 定期健康检测（轻量，不会明显影响轮询速度）
                if loop_count % HEALTH_CHECK_INTERVAL == 0:
                    try:
                        page = slot.get("page")
                        cdp = slot.get("_cdp")
                        if page and cdp:
                            hf = asyncio.run_coroutine_threadsafe(
                                self._health_check(page, cdp, merchant_id), main_loop
                            )
                            health = hf.result(timeout=10)
                            
                            if health == 'login_expired':
                                slot["status"] = "login_expired"
                                slot["_last_error"] = "抖音登录已过期，请重新扫码"
                                slot["_error_time"] = datetime.now().isoformat()
                                log(f"[LOOP-{merchant_id}] ⚠ LOGIN EXPIRED! Pausing until re-login...")
                                continue
                            
                            elif health in ('page_crashed', 'page_blank'):
                                log(f"[LOOP-{merchant_id}] ⚠ {health.upper()}, attempting full recovery...")
                                slot["_last_error"] = f"页面异常({health})，正在自动恢复..."
                                slot["_error_time"] = datetime.now().isoformat()
                                try:
                                    rf = asyncio.run_coroutine_threadsafe(
                                        self._full_recovery(merchant_id), main_loop
                                    )
                                    ok = rf.result(timeout=60)
                                    if ok:
                                        log(f"[LOOP-{merchant_id}] ✅ full recovery success!")
                                        slot["_last_error"] = None
                                        consecutive_errors = 0
                                        # 更新 page/cdp 引用
                                        main_loop = slot.get("_event_loop", main_loop)
                                    else:
                                        log(f"[LOOP-{merchant_id}] ✗ full recovery failed, will retry...")
                                        time.sleep(10)
                                except Exception as re:
                                    log(f"[LOOP-{merchant_id}] ✗ recovery error: {re}")
                                    time.sleep(10)
                                continue
                    except Exception as he:
                        log(f"[LOOP-{merchant_id}] health check error: {he}")

                if loop_count % 12 == 0:
                    log(f"[LOOP-{merchant_id}] heartbeat #{loop_count} (errs={consecutive_errors}, recoveries={slot.get('_recovery_count', 0)})")

                try:
                    page = slot.get("page")
                    cdp = slot.get("_cdp")
                    if main_loop and page and cdp:
                        future = asyncio.run_coroutine_threadsafe(
                            self._poll_unread_conversations(page, cdp, merchant_id, ai, config, processed, preview_cache, sent_messages, sender_cooldown, warmup_done),
                            main_loop
                        )
                        # ★ 延长 timeout：如果有多个未读消息，每个请求 API 都可能耗时 10-20 秒
                        future.result(timeout=180)
                        consecutive_errors = 0
                        slot["_last_heartbeat"] = datetime.now().isoformat()
                        slot["_last_error"] = None
                        if not warmup_done:
                            warmup_done = True
                            log(f"[LOOP-{merchant_id}] ✅ warmup done, recorded {len(processed)} conversations.")
                    else:
                        log(f"[LOOP-{merchant_id}] ⚠ missing page/cdp/loop, waiting...")
                        time.sleep(3)
                        continue
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    consecutive_errors += 1
                    err_msg = str(e) or repr(e)
                    if "LOOP" not in err_msg:
                        log(f"[POLL-{merchant_id}] error #{consecutive_errors}: {err_msg[:120]}")
                    slot["_last_error"] = err_msg[:200]
                    slot["_error_time"] = datetime.now().isoformat()
                    
                    # ★ 分级恢复：先 CDP 重建，再完整重建
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log(f"[LOOP-{merchant_id}] ⚠ {consecutive_errors} errors, attempting full recovery...")
                        try:
                            rf = asyncio.run_coroutine_threadsafe(
                                self._full_recovery(merchant_id), main_loop
                            )
                            ok = rf.result(timeout=60)
                            if ok:
                                consecutive_errors = 0
                                main_loop = slot.get("_event_loop", main_loop)
                                log(f"[LOOP-{merchant_id}] ✅ full recovery after errors!")
                            else:
                                log(f"[LOOP-{merchant_id}] ✗ full recovery failed")
                                time.sleep(10)
                        except Exception as re:
                            log(f"[LOOP-{merchant_id}] ✗ recovery error: {re}")
                            time.sleep(5)
                    elif consecutive_errors >= 3:
                        # 先尝试轻量 CDP 重建
                        try:
                            recovery_future = asyncio.run_coroutine_threadsafe(
                                self._recover_cdp(merchant_id), main_loop
                            )
                            recovery_future.result(timeout=20)
                            consecutive_errors = 0
                            log(f"[LOOP-{merchant_id}] ✅ CDP recovery successful")
                        except Exception as re:
                            log(f"[LOOP-{merchant_id}] ✗ CDP recovery failed: {re}")

                import random
                time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            log(f"[LOOP-{merchant_id}] CRASHED: {e}")
            import traceback
            traceback.print_exc()
            slot["_last_error"] = f"监控线程崩溃: {e}"
            slot["_error_time"] = datetime.now().isoformat()
        finally:
            log(f"[LOOP-{merchant_id}] ended")

    async def _recover_cdp(self, merchant_id: int):
        """★ 兜底机制：重建 CDP 会话 + 刷新页面"""
        slot = self.slots.get(merchant_id)
        if not slot:
            return
        
        page = slot.get("page")
        context = slot.get("context")
        if not page or not context:
            log(f"[RECOVER-{merchant_id}] no page/context, cannot recover")
            return
        
        # 1. 尝试重新导航到私信页面
        CHAT_URL = "https://creator.douyin.com/creator-micro/data/following/chat"
        try:
            await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
        except Exception as e:
            log(f"[RECOVER-{merchant_id}] goto failed: {e}")
        
        # 2. 重建 CDP 会话
        try:
            old_cdp = slot.get("_cdp")
            if old_cdp:
                try:
                    await old_cdp.detach()
                except Exception:
                    pass
            
            new_cdp = await context.new_cdp_session(page)
            slot["_cdp"] = new_cdp
            await new_cdp.send("Network.enable")
            self._setup_cdp_listeners(new_cdp, slot, merchant_id)
            log(f"[RECOVER-{merchant_id}] new CDP session established")
        except Exception as e:
            log(f"[RECOVER-{merchant_id}] CDP rebuild failed: {e}")

    async def _health_check(self, page, cdp, merchant_id) -> str:
        """★ 快速健康检测（< 500ms），返回 'ok' / 'page_crashed' / 'login_expired' / 'page_blank'"""
        try:
            # 1. 页面 URL 是否正常？
            url = page.url
            if not url or url == 'about:blank' or url.startswith('chrome-error'):
                return 'page_crashed'
            
            # 2. 能否执行 JS？（测试 CDP 是否正常）
            r = await cdp.send("Runtime.evaluate", {
                "expression": "document.readyState",
                "returnByValue": True, "timeout": 3000
            })
            state = r.get("result", {}).get("value", "")
            if not state:
                return 'page_crashed'
            
            # 3. 页面是否为空白？
            r2 = await cdp.send("Runtime.evaluate", {
                "expression": "document.body ? document.body.innerText.length : 0",
                "returnByValue": True, "timeout": 3000
            })
            body_len = r2.get("result", {}).get("value", 0)
            if body_len < 10:
                return 'page_blank'
            
            # 4. 是否跳转到了登录页面？（抖音 session 过期）
            r3 = await cdp.send("Runtime.evaluate", {
                "expression": "(document.body.innerText.includes('扫码登录') || document.body.innerText.includes('验证码登录') || document.body.innerText.includes('登录/注册')) && !document.body.innerText.includes('私信')",
                "returnByValue": True, "timeout": 3000
            })
            if r3.get("result", {}).get("value") == True:
                return 'login_expired'
            
            return 'ok'
        except Exception as e:
            log(f"[HEALTH-{merchant_id}] check error: {e}")
            return 'page_crashed'

    async def _full_recovery(self, merchant_id) -> bool:
        """★ 完整恢复：关闭旧浏览器 → 重新启动 → 导航到私信页 → 重建 CDP"""
        slot = self.slots.get(merchant_id)
        if not slot:
            return False
        
        session_dir = self._session_dir(merchant_id)
        log(f"[FULL-RECOVER-{merchant_id}] starting full browser recovery (session: {session_dir})")
        
        # 1. 关闭旧资源
        try:
            old_cdp = slot.get("_cdp")
            if old_cdp:
                try:
                    await old_cdp.detach()
                except Exception:
                    pass
            old_ctx = slot.get("context")
            if old_ctx:
                try:
                    await old_ctx.close()
                except Exception:
                    pass
        except Exception as e:
            log(f"[FULL-RECOVER-{merchant_id}] cleanup error (ok): {e}")
        
        # 2. 重新启动浏览器（使用相同 session 目录保留 cookies）
        try:
            await self._ensure_playwright()
            
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
            chrome_exe = None
            for p in chrome_paths:
                if os.path.exists(p):
                    chrome_exe = p
                    break
            
            stealth_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run", "--no-default-browser-check", "--disable-infobars",
                f"--window-size=1280,800",
                f"--window-position={100 + merchant_id * 50},{100 + merchant_id * 50}",
            ]
            
            launch_kwargs = {
                "user_data_dir": session_dir,
                "headless": False,
                "viewport": {"width": 1280, "height": 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "locale": "zh-CN", "timezone_id": "Asia/Shanghai",
                "args": stealth_args,
                "ignore_default_args": ["--enable-automation"],
            }
            if chrome_exe:
                launch_kwargs["executable_path"] = chrome_exe
            
            context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else await context.new_page()
            
            slot["context"] = context
            slot["page"] = page
            log(f"[FULL-RECOVER-{merchant_id}] ✅ new browser launched")
        except Exception as e:
            log(f"[FULL-RECOVER-{merchant_id}] ✗ browser launch failed: {e}")
            return False
        
        # 3. 导航到私信页面
        CHAT_URL = "https://creator.douyin.com/creator-micro/data/following/chat"
        try:
            await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
        except Exception as e:
            log(f"[FULL-RECOVER-{merchant_id}] navigation error: {e}")
        
        # 4. 验证是否登录
        real = await self._verify_real_login(page, context)
        if not real:
            log(f"[FULL-RECOVER-{merchant_id}] ⚠ login expired after recovery")
            slot["status"] = "login_expired"
            slot["_last_error"] = "抖音登录已过期，请重新扫码登录"
            slot["_error_time"] = datetime.now().isoformat()
            return False
        
        # 5. 重建 CDP
        try:
            new_cdp = await context.new_cdp_session(page)
            slot["_cdp"] = new_cdp
            await new_cdp.send("Network.enable")
            self._setup_cdp_listeners(new_cdp, slot, merchant_id)
            slot["_event_loop"] = asyncio.get_running_loop()
            log(f"[FULL-RECOVER-{merchant_id}] ✅ CDP rebuilt, recovery complete!")
            slot["_recovery_count"] = slot.get("_recovery_count", 0) + 1
            return True
        except Exception as e:
            log(f"[FULL-RECOVER-{merchant_id}] ✗ CDP rebuild failed: {e}")
            return False

    async def _scan_conv_list(self, cdp):
        """扫描左侧会话列表，返回会话列表（含未读标记和预览文本）"""
        import json as _json
        scan_js = '''(() => {
            const results = [];
            const seen = new Set();
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const rr = el.getBoundingClientRect();
                if (rr.x > 0 && rr.x < 350 && rr.height > 50 && rr.height < 120 && rr.width > 200) {
                    const nameEls = el.querySelectorAll('*');
                    let name = '';
                    let previewText = '';
                    let hasUnread = false;
                    
                    for (const ne of nameEls) {
                        const ns = window.getComputedStyle(ne);
                        const nr = ne.getBoundingClientRect();
                        const nt = (ne.innerText || '').trim();
                        
                        if (nr.width > 0 && nr.width < 25 && nr.height > 0 && nr.height < 25) {
                            const bg = ns.backgroundColor;
                            if (bg && (bg.includes('255, 0') || bg.includes('255,0') || 
                                bg.includes('239, 68') || bg.includes('234, 67') ||
                                bg.includes('rgb(255') || bg.includes('rgba(255, 77') ||
                                bg.includes('rgb(254') || bg.includes('rgb(246'))) {
                                hasUnread = true;
                            }
                            if (/^\\d{1,3}\\+?$/.test(nt) && nr.width < 25) {
                                hasUnread = true;
                            }
                        }
                        
                        if (ne.childElementCount === 0 && nt && nt.length >= 2) {
                            if (!name && nt.length <= 20 
                                && nr.height >= 14 && nr.height <= 30
                                && !/^\\d{1,3}\\+?$/.test(nt)
                                && !['全部','朋友私信','陌生人私信','群消息','全选'].includes(nt)) {
                                name = nt;
                            } else if (name && !previewText && nt !== name && nt.length <= 50) {
                                previewText = nt;
                            }
                        }
                    }
                    
                    if (name && !seen.has(name)) {
                        seen.add(name);
                        results.push({ name, x: rr.x + rr.width/2, y: rr.y + rr.height/2, unread: hasUnread, preview_text: previewText });
                        if (results.length >= 10) break;
                    }
                }
            }
            return JSON.stringify(results);
        })()'''
        r = await cdp.send("Runtime.evaluate", {"expression": scan_js, "returnByValue": True, "timeout": 5000})
        return _json.loads(r.get("result", {}).get("value", "[]"))

    async def _click_tab(self, cdp, tab_name):
        """点击标签页（全部/朋友私信/陌生人私信/群消息）— 三级匹配"""
        max_len = len(tab_name) + 5
        js = f'''(() => {{
            const tabs = document.querySelectorAll('*');
            let cands = [];
            for (const t of tabs) {{
                const text = (t.innerText || '').trim();
                const r = t.getBoundingClientRect();
                if (r.x <= 0 || r.x >= 400 || r.y <= 50 || r.y >= 200) continue;
                if (r.height <= 10 || r.height >= 50) continue;
                if (text === '{tab_name}') {{
                    if (t.childElementCount === 0) {{ t.click(); return 'ok'; }}
                    cands.push(t);
                }}
            }}
            if (cands.length > 0) {{ cands[0].click(); return 'ok2'; }}
            for (const t of tabs) {{
                const text = (t.innerText || '').trim();
                const r = t.getBoundingClientRect();
                if (r.x <= 0 || r.x >= 400 || r.y <= 50 || r.y >= 200) continue;
                if (r.height <= 10 || r.height >= 50) continue;
                if (text.includes('{tab_name}') && text.length <= {max_len}) {{
                    t.click(); return 'ok_fuzzy';
                }}
            }}
            return 'no';
        }})()'''
        r = await cdp.send("Runtime.evaluate", {"expression": js, "returnByValue": True})
        result = r.get("result", {}).get("value", "no")
        if result == "no":
            log(f"[TAB] ⚠ tab '{tab_name}' not found")
        return result != "no"

    async def _poll_unread_conversations(self, page, cdp, merchant_id, ai, config, processed, preview_cache, sent_messages, sender_cooldown, warmup_done):
        """★ 新版轮询：只扫描红点，有红点才点击进入回复，无红点安静等待"""
        
        CHAT_URL = "https://creator.douyin.com/creator-micro/data/following/chat"
        
        # ★ 兜底机制：只在完全跑出抖音域名时才用 goto（极端情况）
        try:
            current_url = page.url
            if 'creator.douyin.com' not in current_url:
                log(f"[POLL] ⚠ Not on Douyin! url={current_url[:50]}, emergency goto...")
                await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
        except Exception as e:
            log(f"[POLL] recovery error: {e}")

        # 等待页面稳定
        await asyncio.sleep(0.3)
        
        conv_list = await self._scan_conv_list(cdp)
        if not conv_list:
            return
        
        # ★ 双重检测机制：红点 + 预览文本变化
        # 红点检测
        unread_targets = [c for c in conv_list if c.get("unread", False)]
        
        # ★ 预览文本变化检测（即使没有红点，如果预览文本变了且不是自己发的，也要处理）
        for c in conv_list:
            name = c.get("name", "")
            preview = c.get("preview", "")
            if not name or not preview or name in [n["name"] for n in unread_targets]:
                continue
            # 检查预览文本是否有变化
            cached_preview = preview_cache.get(name, "")
            if preview != cached_preview and preview not in sent_messages:
                # 预览变了且不是自己发的 → 当成未读处理
                log(f"[POLL] 📝 preview changed for {name}: '{cached_preview[:20]}' → '{preview[:20]}'")
                unread_targets.append(c)
            preview_cache[name] = preview
        
        if not unread_targets:
            return
        
        names = [c['name'] for c in unread_targets]
        log(f"[POLL] 🔴 targets: {names}")
        
        for target in unread_targets:
            name = target["name"]
            
            now = time.time()
            if name in sender_cooldown and (now - sender_cooldown[name]) < 3:
                log(f"[POLL] ⏳ skipping {name} due to short cooldown")
                continue
            
            log(f"[POLL] 🟢 processing {name} (reason: has_unread)")
            
            # 重新扫描获取最新坐标
            fresh = await self._scan_conv_list(cdp)
            conv = next((c for c in fresh if c["name"] == name), target)
            
            try:
                await self._process_one_conversation(page, cdp, conv, merchant_id, ai, config, processed, sent_messages, sender_cooldown, True)
            except Exception as e:
                log(f"[POLL] error processing {name}: {e}")
            
            await asyncio.sleep(0.3)

    async def _handle_stranger_messages(self, page, cdp, merchant_id, ai, config, processed, sent_messages, sender_cooldown):
        """处理陌生人消息：点击进入→扫描→逐个处理→返回全部"""
        log("[POLL] checking stranger messages...")
        
        # 点击"陌生人消息"入口
        conv_list = await self._scan_conv_list(cdp)
        stranger_entry = next((c for c in conv_list if c["name"] == "陌生人消息"), None)
        if not stranger_entry:
            return
        
        await page.mouse.click(stranger_entry["x"], stranger_entry["y"])
        await asyncio.sleep(1.2)
        
        # 扫描陌生人子列表（前3个，不依赖红点检测）
        stranger_convs = await self._scan_conv_list(cdp)
        targets = [c for c in stranger_convs if c["name"] != "陌生人消息"][:3]
        
        for conv in targets:
            sender = conv["name"]
            now = time.time()
            if sender in sender_cooldown and (now - sender_cooldown[sender]) < 3:
                continue
            
            # 重新扫描获取最新坐标
            fresh = await self._scan_conv_list(cdp)
            conv = next((c for c in fresh if c["name"] == sender), None)
            if not conv:
                continue
            
            try:
                await self._process_one_conversation(page, cdp, conv, merchant_id, ai, config, processed, sent_messages, sender_cooldown, True)
            except Exception as e:
                log(f"[POLL] stranger error {sender}: {e}")
    async def _navigate_back_to_list(self, page, cdp, chat_url=None):
        """★ 新版：用坐标点击 < 返回箭头 → 点击"全部"标签 → 回到全屏列表待机"""
        import random
        try:
            await asyncio.sleep(random.uniform(0.2, 0.4))
            
            # 第1步：精确定位 < 返回箭头的坐标并点击
            # 用 JS 找到"全部私信"文字左边的 < 箭头的精确坐标
            find_back_arrow_js = '''(() => {
                const allEls = document.querySelectorAll('*');
                
                // 找到"全部私信"文字元素
                for (const el of allEls) {
                    const text = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    if (text === '全部私信' && el.childElementCount === 0 
                        && r.y > 50 && r.y < 250 && r.x > 100 && r.x < 400
                        && r.height > 10 && r.height < 60) {
                        // 返回箭头在"全部私信"文字的左边，大约偏移 30-50px
                        return JSON.stringify({x: r.x - 30, y: r.y + r.height / 2});
                    }
                }
                
                // 备用：找 class 包含 back 的按钮
                const backBtns = document.querySelectorAll('button[class*="back"], [class*="back-btn"]');
                for (const btn of backBtns) {
                    const r = btn.getBoundingClientRect();
                    if (r.x >= 0 && r.x < 300 && r.y > 50 && r.y < 250 && r.width > 5) {
                        return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
                    }
                }
                
                return 'not_found';
            })()'''
            
            r = await cdp.send("Runtime.evaluate", {"expression": find_back_arrow_js, "returnByValue": True, "timeout": 3000})
            arrow_pos = r.get("result", {}).get("value", "not_found")
            
            if arrow_pos != 'not_found':
                import json as _json
                pos = _json.loads(arrow_pos)
                log(f"[NAV] clicking back arrow at ({pos['x']:.0f}, {pos['y']:.0f})")
                await page.mouse.click(pos['x'], pos['y'])
                await asyncio.sleep(random.uniform(0.8, 1.2))
            else:
                log("[NAV] ⚠ back arrow not found")
            
            # 第2步：用 Playwright 内置选择器点击"全部"标签（比 JS 遍历 DOM 更可靠）
            try:
                tab = page.locator('text="全部"').first
                if await tab.is_visible(timeout=2000):
                    await tab.click()
                    log("[NAV] clicked '全部' tab via Playwright locator")
                    await asyncio.sleep(random.uniform(0.3, 0.5))
                else:
                    log("[NAV] ⚠ '全部' tab not visible")
            except Exception as tab_err:
                log(f"[NAV] ⚠ '全部' tab click failed: {tab_err}")
                # 兜底：用 page.goto
                if not chat_url:
                    chat_url = "https://creator.douyin.com/creator-micro/data/following/chat"
                await page.goto(chat_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)
        except Exception as e:
            log(f"[NAV] 返回列表错误: {e}")

    async def _soft_return(self):
        import random
        await asyncio.sleep(random.uniform(0.05, 0.15))

    async def _process_one_conversation(self, page, cdp, conv, merchant_id, ai, config, processed, sent_messages, sender_cooldown, warmup_done):
        """处理单个会话：预热模式只记录（不点击），正常模式才点击进入回复"""
        import json as _json
        sender = conv["name"]
        CHAT_URL = "https://creator.douyin.com/creator-micro/data/following/chat"
        
        # ★ 预热模式：只用列表预览文本记录，完全不点击进入会话！
        if not warmup_done:
            preview = conv.get("preview_text", "")
            processed[sender] = preview
            log(f"[WARMUP] recorded {sender}: {preview[:30]}")
            return
        
        # 1. 点击列表中的会话（加随机延迟模拟真人）
        import random
        log(f"[STEP1-{sender}] clicking conv at ({conv['x']}, {conv['y']})")
        await asyncio.sleep(random.uniform(0.05, 0.15))  # ★ 极速点击
        await page.mouse.click(conv["x"], conv["y"])
        await asyncio.sleep(random.uniform(0.3, 0.5))  # ★ 缩短等待
        
        try:
            # 2. 读取右侧聊天区域的消息
            read_msgs_js = '''(() => {
                const msgs = [];
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    if (el.childElementCount > 0) continue;
                    const text = (el.innerText || '').trim();
                    if (!text || text.length < 2 || text.length > 500) continue;
                    const r = el.getBoundingClientRect();
                    if (r.x < 350 || r.y < 130) continue;
                    if (r.width < 10) continue;
                    const tag = el.tagName.toLowerCase();
                    if (['button', 'a', 'label', 'input'].includes(tag)) continue;
                    const noise = ['发送', '输入', '表情', '图片', '更多', '关注', '私信', '设置', 
                                  '通知', '回复', '转发', '点赞', '收藏', '分享', '举报', '发消息',
                                  '请输入', '按Enter', '查看Ta的主页', '群消息', '朋友私信', '陌生人私信',
                                  '全部私信', '互动管理', '私信管理', '粉丝管理', '评论管理', '弹幕管理',
                                  '高清发布', '关注管理', '内容管理', '作品管理', '合集管理', '首页',
                                  '数据中心', '变现中心', '创作中心', '共创中心', '原创保护中心', '活动管理'];
                    if (noise.some(n => text === n || text === n + '...')) continue;
                    if (text.includes('按回车即发送') || text.includes('shift+enter换行') || text.includes('输入私信内容')) continue;
                    if (text.includes('你收到一条新类型消息') || text.includes('请打开抖音app查看')) continue;
                    if (/^\\d{2}:\\d{2}$/.test(text) || /^\\d{2}-\\d{2}$/.test(text) || /^\\d{4}-\\d{2}-\\d{2}/.test(text)) continue;
                    if (/^(昨天|刚刚|前天)$/.test(text) || /^(星期|周)[一二三四五六日]$/.test(text)) continue;
                    if (text.includes('撤回了一条消息')) continue;
                    
                    // 判断是否是自己发的消息（气泡靠右）
                    // 抖音创作者后台，右侧聊天框大概占屏幕右半部分，如果 x 超过屏幕宽度的 2/3，或者是靠右侧，基本上就是自己发的
                    const is_right = r.x > (document.body.clientWidth * 0.6);
                    
                    msgs.push({text: text, y: r.y, x: r.x, is_right: is_right});
                }
                msgs.sort((a, b) => a.y - b.y);
                return JSON.stringify(msgs.slice(-5));
            })()'''
            
            r = await cdp.send("Runtime.evaluate", {
                "expression": read_msgs_js,
                "returnByValue": True, "timeout": 5000
            })
            messages = _json.loads(r.get("result", {}).get("value", "[]"))
            log(f"[STEP2-{sender}] read {len(messages)} msgs, last={messages[-1]['text'][:30] if messages else 'NONE'}")
            
            if not messages:
                log(f"[STEP2-{sender}] ❌ NO messages read, returning")
                await self._soft_return()
                return
                
            last_msg = messages[-1]["text"]
            
            # ★ 核心去重逻辑：不仅比较最后一条，而是比较最近5条消息的整体状态
            current_state = "|".join([m["text"] for m in messages])
            prev_state = processed.get(sender)
            if prev_state == current_state:
                log(f"[STEP3-{sender}] ❌ state unchanged, skipping")
                await self._soft_return()
                return
            log(f"[STEP3-{sender}] ✅ state changed, proceeding")
            
            # 更新记录并备份旧状态以便在出错时回滚
            old_processed_state = processed.get(sender)
            processed[sender] = current_state
            
            # 检查是否是自己发的消息（防回声）
            for sent in sent_messages:
                if last_msg == sent or (len(last_msg) >= 5 and (last_msg in sent or sent in last_msg)):
                    log(f"[STEP4-{sender}] ❌ self echo match: '{last_msg[:20]}' == '{sent[:20]}'")
                    await self._soft_return()
                    return
            
            # 过滤：如果最后一条消息是自己发的（右侧气泡），跳过
            is_right = messages[-1].get("is_right", False)
            msg_x = messages[-1].get("x", 0)
            log(f"[STEP4-{sender}] last msg is_right={is_right}, x={msg_x}, text='{last_msg[:30]}'")
            if is_right:
                log(f"[STEP4-{sender}] ❌ last msg is from bot (right side x={msg_x}), skipping")
                await self._soft_return()
                return
            log(f"[STEP4-{sender}] ✅ passed all filters")
            
            log(f"[POLL] ★ new message from {sender}: {last_msg[:50]}")
            # ★ 统计：今日消息数 +1
            self._check_day_reset()
            self._today_stats["messages"] += 1
            _msg_start_time = time.time()
            
            # ★★★ 记录用户消息到 runtime_messages（供前端消息监控页面显示）★★★
            slot = self.slots.get(merchant_id)
            if slot and "runtime_messages" in slot:
                slot["runtime_messages"].append({
                    "id": int(time.time() * 1000),
                    "sender": sender,
                    "text": last_msg,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "account": f"商户 {merchant_id}",
                    "is_ai": False,
                })
            
            # 3. 计费检查
            try:
                # ★ DB 操作也走线程池，不阻塞事件循环
                def _db_check():
                    db = self._get_db(merchant_id)
                    can = db.can_serve()
                    if can:
                        lead = LeadExtractor.extract_all(last_msg)
                        if lead["phone"] or lead["wechat"]:
                            log(f"[LEAD] extracted: {lead}")
                            saved = db.save_lead(phone=lead["phone"], wechat=lead["wechat"], douyin_user_id=sender)
                            if saved:
                                db.deduct_balance(1.0)
                                log(f"[BILLING] Deducted 1.0 for lead from {sender}")
                                self._today_stats["leads"] += 1
                    db.close()
                    return can
                
                can_serve = await asyncio.to_thread(_db_check)
                if not can_serve:
                    log(f"[BILLING] Merchant {merchant_id} cannot serve")
                    if old_processed_state is not None:
                        processed[sender] = old_processed_state
                    else:
                        processed.pop(sender, None)
                    await self._soft_return()
                    return
            except Exception as e:
                log(f"[DB] billing check error (ignored, proceeding): {e}")
            
            # 4. AI 回复 — ★ 每次回复前重新加载配置 + 超时保护
            try:
                import json as _json2
                config_dir = os.path.join(SCRIPT_DIR, "agent_configs")
                config_file = os.path.join(config_dir, f"store_{merchant_id}.json")
                if not os.path.exists(config_file):
                    config_file = os.path.join(SCRIPT_DIR, "agent_config.json")
                if os.path.exists(config_file):
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = _json2.load(f)
                    log(f"[STEP5-{sender}] config loaded: nickname={config.get('nickname')}, persona={bool(config.get('persona'))}")
                else:
                    log(f"[STEP5-{sender}] no config file, using defaults")
            except Exception as e:
                log(f"[STEP5-{sender}] config load error: {e}")
            nickname = config.get('nickname', '小橙')
            try:
                reply = await asyncio.wait_for(
                    ai.get_reply_async(last_msg, config, f"dy_{merchant_id}"),
                    timeout=10  # 最多等10秒，超时就用兜底
                )
                log(f"[AI] reply ({nickname}): {reply[:80]}")
                self._today_stats["ai_success"] += 1
            except asyncio.TimeoutError:
                log(f"[AI] API 超时（>10s），使用兜底回复")
                reply = f"你好！{nickname}为您服务，有什么可以帮您的吗？"
                self._today_stats["ai_fail"] += 1
            except Exception as e:
                log(f"[AI] error: {e}, using fallback")
                reply = f"你好！{nickname}为您服务，有什么可以帮您的吗？"
                self._today_stats["ai_fail"] += 1
            # ★ 统计响应时间
            if '_msg_start_time' in dir():
                self._today_stats["response_times"].append(round(time.time() - _msg_start_time, 2))
            
            # 5. 用 JS 直接写入文字并发送（确保 React 状态同步）
            escaped_reply = reply.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
            
            send_all_js = f'''(() => {{
                // 找到编辑器 — 三级查找
                const allEls = document.querySelectorAll('textarea, [contenteditable="true"], input[type="text"], div[contenteditable]');
                let editor = null;
                
                // 第1级：通过 placeholder 精确匹配
                for (const el of allEls) {{
                    const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                    if (ph.includes('回车') || ph.includes('发送') || ph.includes('私信') || ph.includes('输入') || ph.includes('enter')) {{
                        const r = el.getBoundingClientRect();
                        if (r.width > 30 && r.height > 10) {{
                            editor = el;
                            break;
                        }}
                    }}
                }}
                
                // 第2级：通过位置查找（右侧面板下方的可编辑区域）
                if (!editor) {{
                    for (const el of allEls) {{
                        const r = el.getBoundingClientRect();
                        if (r.x > 300 && r.y > 300 && r.width > 50 && r.height > 10 && r.height < 200) {{
                            editor = el;
                        }}
                    }}
                }}
                
                // 第3级：查找所有 contenteditable 或 textarea（最宽松）
                if (!editor) {{
                    const editors = document.querySelectorAll('[contenteditable="true"], textarea');
                    for (const el of editors) {{
                        const r = el.getBoundingClientRect();
                        if (r.x > 300 && r.width > 30 && r.height > 5) {{
                            editor = el;
                            break;
                        }}
                    }}
                }}
                if (!editor) return 'no_editor';
                
                // 聚焦并清空
                editor.focus();
                
                const text = '{escaped_reply}';
                
                if (editor.tagName.toLowerCase() === 'textarea' || editor.tagName.toLowerCase() === 'input') {{
                    // textarea/input: 直接设置 value 并触发事件
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    )?.set || Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set;
                    if (nativeInputValueSetter) {{
                        nativeInputValueSetter.call(editor, text);
                    }} else {{
                        editor.value = text;
                    }}
                    editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    editor.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }} else {{
                    // contenteditable: 用 execCommand 写入
                    editor.innerHTML = '';
                    editor.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, text);
                    editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                
                // 等一下再点发送按钮
                return 'text_inserted';
            }})()'''
            
            r = await cdp.send("Runtime.evaluate", {
                "expression": send_all_js,
                "returnByValue": True
            })
            insert_result = r.get("result", {}).get("value", "error")
            
            if insert_result == 'no_editor':
                log(f"[POLL] editor not found for {sender}")
                if old_processed_state is not None:
                    processed[sender] = old_processed_state
                else:
                    processed.pop(sender, None)
                await self._soft_return()
                return
            
            log(f"[POLL] text inserted via JS for {sender}")
            import random
            await asyncio.sleep(0.15)  # ★ 极速等 React 状态更新
            
            # 点击发送按钮
            send_btn_js = '''(() => {
                const btns = document.querySelectorAll('*');
                for (const b of btns) {
                    const t = (b.innerText || '').trim();
                    const r = b.getBoundingClientRect();
                    if (t === '发送' && r.x > 500 && r.y > 500 && r.width < 100) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            })()'''
            
            r2 = await cdp.send("Runtime.evaluate", {
                "expression": send_btn_js,
                "returnByValue": True
            })
            btn_result = r2.get("result", {}).get("value", "error")
            
            if btn_result == 'clicked':
                log(f"[POLL] ✅ sent reply to {sender} (JS+button): {reply[:40]}")
            else:
                # 兜底：用 Enter
                await page.keyboard.press("Enter")
                log(f"[POLL] ✅ sent reply to {sender} (JS+Enter): {reply[:40]}")
            
            # 记录防回声 + 冷却
            sent_messages.add(reply[:30])
            sent_messages.add(reply)
            
            # ★★★ 修复状态重写 BUG：将 AI 的回复追加到当前的对话状态之后，而不是直接覆盖！
            # 这样下一次轮询如果没新消息，当前截取的 last 5 messages 正好包含了这个 reply，状态就能严格匹配上，避免重复处理
            current_state = processed.get(sender, "")
            processed[sender] = current_state + "|" + reply
            
            now = time.time()
            sender_cooldown[sender] = now
            
            # ★★★ 记录 AI 回复到 runtime_messages（供前端显示）★★★
            slot = self.slots.get(merchant_id)
            if slot and "runtime_messages" in slot:
                slot["runtime_messages"].append({
                    "id": int(time.time() * 1000) + 1,
                    "sender": sender,
                    "text": reply,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "account": f"商户 {merchant_id}",
                    "is_ai": True,
                })
            
        finally:
            # ★ 回复完毕 → 点击返回箭头 → 点击"全部"标签 → 回到列表待机
            log(f"[POLL] ✅ done with {sender}, navigating back...")
            await self._navigate_back_to_list(page, cdp, CHAT_URL)

    def _handle_message(self, data, merchant_id, processed, ai, config, sent_messages, sender_cooldown):
        """处理单条消息"""
        texts = data.get("texts", [])
        source = data.get("source", "")
        sender = data.get("sender")  # 发送者名字

        # 去重
        key = f"{source}_{'_'.join(sorted(set(texts[:3])))}"
        if key in processed:
            return
        processed.add(key)

        # 过滤噪音
        noise = {"冯志泉", "抖音", "更多", "已关注", "关注", "发送", "输入", "图片", "表情",
                 "消息", "通知", "设置", "退出", "频道", "群聊", "视频", "直播", "精选",
                 "私信", "下载", "客户端", "涨知识", "科普", "捂脸", "可爱卡通", "长草团子",
                 "新星计划", "人民日报", "抱抱你", "晚上好", "比心", "玫瑰", "发送消息",
                 "梦琪爱吃", "职业素人"}
        user_msgs = [t for t in texts if len(t) >= 2 and t not in noise
                    and not any(n in t for n in ["抖音", "下载", "客户端", "科普", "人民日报",
                                                  "已互相关注", "开始聊天了", "卡通", "团子",
                                                  "私信了你", "点赞了你", "关注了你",
                                                  "收藏了你", "评论了你", "添加了你"])]
        if not user_msgs:
            return

        best = max(user_msgs, key=lambda t: len(t) + (10 if "?" in t or "？" in t else 0))
        
        # ★ 防止自己消息循环：过滤掉最近发送过的文本
        # 短消息只精确匹配，长消息(>=5字)才做子串匹配
        for sent in sent_messages:
            if best == sent:  # 精确匹配
                log(f"[MSG] skip self echo (exact): {best[:30]}")
                return
            if len(best) >= 5 and (best in sent or sent in best):  # 长消息子串匹配
                log(f"[MSG] skip self echo (substr): {best[:30]}")
                return
        
        # ★ 过滤包含机器人昵称/常见回复关键词的消息
        bot_nickname = config.get('nickname', '小橙')
        bot_phrases = [bot_nickname, "手机号或微信号", "留下你的", "为你服务", "专属服务", "专属客服"]
        if any(phrase in best for phrase in bot_phrases):
            log(f"[MSG] skip bot msg: {best[:30]}")
            return
        
        # ★ 发送者冷却 + 消息内容冷却：防止重复回复
        import time as _time
        now = _time.time()
        # 检查消息内容冷却（同样的消息30秒内不重复处理）
        content_key = f"msg_{best[:20]}"
        if content_key in sender_cooldown:
            elapsed = now - sender_cooldown[content_key]
            if elapsed < 15:
                log(f"[MSG] skip content cooldown ({elapsed:.0f}s): {best[:20]}")
                return
        # 检查发送者冷却（同一个人30秒内不重复回复）
        if sender:
            if sender in sender_cooldown:
                elapsed = now - sender_cooldown[sender]
                if elapsed < 15:
                    log(f"[MSG] skip sender cooldown ({elapsed:.0f}s): {sender}")
                    return
        # 全局冷却（至少间隔10秒才回复下一条消息）
        if "_global" in sender_cooldown:
            elapsed = now - sender_cooldown["_global"]
            if elapsed < 10:
                log(f"[MSG] skip global cooldown ({elapsed:.0f}s)")
                return
        
        log(f"[MSG] ★ {best} (from: {sender or 'unknown'})")
        
        slot_obj = self.slots.get(merchant_id)
        if slot_obj and "runtime_messages" in slot_obj:
            slot_obj["runtime_messages"].append({
                "id": int(_time.time() * 1000),
                "sender": sender or "unknown",
                "text": best,
                "time": datetime.now().strftime("%H:%M:%S"),
                "is_ai": False
            })

        db = None
        try:
            db = self._get_db(merchant_id)
            
            # 1. 检查是否可以服务（余额充足且开启状态）
            if not db.can_serve():
                log(f"[BILLING] Merchant {merchant_id} cannot serve (insufficient balance or disabled)")
                self._schedule_cdp_reply(merchant_id, sender, "由于系统服务到期，暂时无法自动回复，请联系客服。")
                return

            # 2. 提取客资并扣费
            for text in user_msgs:
                lead = LeadExtractor.extract_all(text)
                if lead["phone"] or lead["wechat"]:
                    log(f"[LEAD] extracted: {lead}")
                    saved = db.save_lead(phone=lead["phone"], wechat=lead["wechat"], douyin_user_id=sender)
                    if saved:
                        db.deduct_balance(1.0)
                        log(f"[BILLING] Deducted 1.0 balance for lead from {sender}")
        except Exception as e:
            log(f"[DB] error in message handling: {e}")
        finally:
            if db:
                db.close()

        # AI 回复
        try:
            reply = ai.get_reply(best, config, f"dy_{merchant_id}")  # WebSocket handler uses sync version
            log(f"[AI] {reply[:80]}")
            if slot_obj and "runtime_messages" in slot_obj:
                slot_obj["runtime_messages"].append({
                    "id": int(_time.time() * 1000) + 1,
                    "sender": config.get('nickname', '小橙'),
                    "text": reply,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "is_ai": True
                })
        except Exception as e:
            log(f"[AI] error: {e}")
            return

        # 记录发送的消息（防止回声循环）
        sent_messages.add(reply[:30])  # 只记前30字
        sent_messages.add(reply)  # 完整文本也记
        sender_cooldown[content_key] = now  # 消息内容冷却
        sender_cooldown["_global"] = now  # 全局冷却
        if sender:
            sender_cooldown[sender] = now  # 发送者冷却
        
        # 发送回复到抖音
        self._schedule_cdp_reply(merchant_id, sender, reply)

    # ========== REPLY SENDING ==========

    def _schedule_cdp_reply(self, merchant_id, sender, reply_text):
        """从线程中安全调度 CDP 回复"""
        slot = self.slots.get(merchant_id)
        if not slot:
            return

        cdp = slot.get("_cdp")
        loop = slot.get("_event_loop")
        if not cdp or not loop:
            log(f"[REPLY] no CDP/loop available")
            return

        page = slot.get("page")
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._cdp_reply(cdp, page, sender, reply_text),
                loop
            )
            result = future.result(timeout=60)
            log(f"[REPLY] {result}")
        except Exception as e:
            log(f"[REPLY] failed: {e}")

    async def _cdp_reply(self, cdp, page, sender, text):
        """通过 Playwright 在抖音私信中发送回复"""
        import json as _json
        try:
            # 第一步：在左侧列表中找到发信人并点击
            sender_safe = (sender or '').replace("'", "\\'").replace("\\", "\\\\")
            find_conv_js = f'''(() => {{
                const senderName = '{sender_safe}';
                const all = document.querySelectorAll('*');
                for (const el of all) {{
                    if (el.childElementCount === 0) {{
                        const text = (el.innerText || '').trim();
                        if (text && (text === senderName || text.includes(senderName) || senderName.includes(text))) {{
                            const r = el.getBoundingClientRect();
                            // 左侧列表区域：x < 600
                            if (r.x < 600 && r.width > 0 && r.height > 0) {{
                                let clickTarget = el;
                                let parent = el.parentElement;
                                for (let i = 0; i < 4 && parent; i++) {{
                                    const pr = parent.getBoundingClientRect();
                                    if (pr.height > 40 && pr.height < 100) {{
                                        clickTarget = parent;
                                        break;
                                    }}
                                    parent = parent.parentElement;
                                }}
                                const cr = clickTarget.getBoundingClientRect();
                                return JSON.stringify({{ok: true, x: cr.x + cr.width / 2, y: cr.y + cr.height / 2, name: text}});
                            }}
                        }}
                    }}
                }}
                return JSON.stringify({{ok: false}});
            }})()'''
            
            r = await cdp.send("Runtime.evaluate", {
                "expression": find_conv_js,
                "returnByValue": True, "timeout": 5000
            })
            conv = _json.loads(r.get("result", {}).get("value", '{"ok":false}'))
            if conv.get("ok"):
                await page.mouse.click(conv["x"], conv["y"])
                log(f"[REPLY] clicked creator conv '{conv.get('name','')}' ({conv['x']:.0f},{conv['y']:.0f})")
            else:
                log(f"[REPLY] no conv found for '{sender}' on creator platform")
                return "FAIL: no conv"
            await asyncio.sleep(2)

            # 第1.5步：验证聊天头部是否显示了正确的发送者名字
            if sender:
                verify_js = f'''(() => {{
                    const senderName = '{sender_safe}';
                    const all = document.querySelectorAll('*');
                    for (const el of all) {{
                        if (el.childElementCount === 0) {{
                            const text = (el.innerText || '').trim();
                            if (text && (text === senderName || text.includes(senderName) || senderName.includes(text))) {{
                                const r = el.getBoundingClientRect();
                                // 聊天头部区域：右侧顶部
                                if (r.x > 300 && r.y < 200 && r.width > 0) {{
                                    return JSON.stringify({{match: true, header: text}});
                                }}
                            }}
                        }}
                    }}
                    return JSON.stringify({{match: false}});
                }})()'''
                vr = await cdp.send("Runtime.evaluate", {
                    "expression": verify_js,
                    "returnByValue": True, "timeout": 3000
                })
                verify = _json.loads(vr.get("result", {}).get("value", '{"match":false}'))
                if not verify.get("match"):
                    log(f"[REPLY] ❌ creator header mismatch! Expected '{sender}', not found.")
                    return f"FAIL: header mismatch for {sender}"
                log(f"[REPLY] ✓ creator header verified: {verify.get('header')}")

            # 第二步：找到输入框，点击聚焦，清空，输入文字
            # 创作者平台的输入框可能是 textarea 或 [contenteditable]
            editor = page.locator('textarea, [contenteditable="true"]').last
            try:
                await editor.wait_for(state="visible", timeout=5000)
            except:
                return "FAIL: editor not visible"
            
            await editor.click()
            await asyncio.sleep(0.3)
            
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.1)
            
            await page.keyboard.type(text, delay=50)
            log(f"[REPLY] typed: {text[:30]}")
            await asyncio.sleep(0.8)

            # 第三步：直接按 Enter 发送
            await page.keyboard.press("Enter")
            log(f"[REPLY] pressed Enter to send")
            await asyncio.sleep(1)
            
            # ★ 发完信息后，点击返回按钮回到列表（不刷新页面）
            log("[REPLY] returning to chat list...")
            await self._navigate_back_to_list(page, cdp)


            
            return "SENT"

        except asyncio.TimeoutError:
            return "TIMEOUT"
        except Exception as e:
            return f"ERROR: {e}"

    # ========== CONTROL ==========

    async def stop_monitoring(self, merchant_id: int):
        slot = self.slots.get(merchant_id)
        if not slot:
            return
        slot["status"] = "stopped"
        try:
            cdp = slot.get("_cdp")
            if cdp:
                await cdp.detach()
        except Exception:
            pass
        try:
            db = self._get_db(merchant_id)
            db.update_slot_status("stopped")
            db.close()
        except Exception:
            pass
        try:
            await slot["context"].close()
        except Exception:
            pass
        del self.slots[merchant_id]

    # ========== UTILS ==========

    async def _trigger_login(self, page):
        try:
            await page.evaluate('''() => {
                const els = document.querySelectorAll('button, a, span, div');
                for (const el of els) {
                    if (el.textContent.trim() === '登录' && el.offsetWidth > 0) {
                        el.click(); return true;
                    }
                }
                return false;
            }''')
            await asyncio.sleep(1)
        except Exception:
            pass

    async def _capture_qr_screenshot(self, page) -> str:
        try:
            screenshot_bytes = await page.screenshot(
                type="png", 
                clip={"x": 340, "y": 100, "width": 600, "height": 450}
            )
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            log(f"Screenshot error: {e}")
            return ""

    async def shutdown_all(self):
        for mid in list(self.slots.keys()):
            try:
                s = self.slots[mid]
                s["status"] = "stopped"
                if s.get("_cdp"):
                    await s["_cdp"].detach()
                await s["context"].close()
            except Exception:
                pass
        self.slots.clear()
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    # ★ leads 缓存：避免每 2 秒轮询都连接远程数据库
    _leads_cache = {}       # { merchant_id: lead_count }
    _leads_cache_ts = 0     # 上次刷新时间戳
    _LEADS_CACHE_TTL = 30   # 缓存 30 秒

    async def get_all_status(self) -> dict:
        import time as _t
        now = _t.time()
        # 仅当缓存过期时才查询数据库
        if now - self._leads_cache_ts > self._LEADS_CACHE_TTL:
            for m in self.slots:
                try:
                    db = self._get_db(m)
                    leads = db.get_leads()
                    self._leads_cache[m] = len(leads) if leads else 0
                    db.close()
                except Exception:
                    pass  # 保留旧缓存值
            self._leads_cache_ts = now

        result = {}
        for m, s in self.slots.items():
            status = s["status"]
            
            # ★ 自动检测 binding 状态：如果 slot 还在 binding，检查是否已经登录成功
            if status == "binding":
                try:
                    page = s.get("page")
                    context = s.get("context")
                    if page and context:
                        real = await self._verify_real_login(page, context)
                        if real:
                            s["status"] = "bound"
                            s["nickname"] = "douyin_user"
                            status = "bound"
                            log(f"[STATUS] merchant {m} auto-detected login success!")
                except Exception as e:
                    log(f"[STATUS] auto-detect error for {m}: {e}")
            
            # ★ 看门狗：如果状态是 running 但监控线程已死，自动重启
            if status == "running":
                thread = s.get("_monitor_thread")
                if thread and not thread.is_alive():
                    log(f"[WATCHDOG] merchant {m} monitor thread DIED! Restarting...")
                    s["_last_error"] = "监控线程意外退出，正在自动重启..."
                    s["_error_time"] = datetime.now().isoformat()
                    try:
                        import threading
                        t = threading.Thread(
                            target=self._monitor_thread_entry,
                            args=(m,),
                            daemon=True,
                            name=f"monitor-{m}"
                        )
                        t.start()
                        s["_monitor_thread"] = t
                        log(f"[WATCHDOG] merchant {m} monitor thread restarted!")
                    except Exception as e:
                        log(f"[WATCHDOG] merchant {m} restart failed: {e}")
                        s["status"] = "error"
                        s["_last_error"] = f"线程重启失败: {e}"
            
            msgs = s.get("runtime_messages", [])
            ai_count = sum(1 for msg in msgs if msg.get("is_ai"))
            
            # ★ 使用智能体配置中的昵称作为显示名称
            display_name = s.get("nickname")
            try:
                import json as _json
                cfg_file = os.path.join(self._script_dir, "agent_configs", f"store_{m}.json")
                if os.path.exists(cfg_file):
                    with open(cfg_file, "r", encoding="utf-8") as _f:
                        cfg = _json.load(_f)
                        if cfg.get("nickname"):
                            display_name = cfg["nickname"]
            except Exception:
                pass
            
            result[str(m)] = {
                "status": status,
                "nickname": display_name,
                "total_messages": ai_count,
                "total_leads": self._leads_cache.get(m, 0),
                # ★ 健康信息
                "last_heartbeat": s.get("_last_heartbeat"),
                "last_error": s.get("_last_error"),
                "error_time": s.get("_error_time"),
                "recovery_count": s.get("_recovery_count", 0),
            }
        return result

    async def delete_slot(self, merchant_id: int):
        log(f"[SLOT {merchant_id}] Deleting slot...")
        await self.stop_monitoring(merchant_id)
        if merchant_id in self.slots:
            try:
                s = self.slots[merchant_id]
                if s.get("_cdp"):
                    await s["_cdp"].detach()
                await s["context"].close()
            except Exception:
                pass
            del self.slots[merchant_id]
        
        # 删除数据库中的记录
        try:
            db = self._get_db(merchant_id)
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM rpa_slot WHERE merchant_id = %s", (merchant_id,))
                conn.commit()
            db.close()
        except Exception as e:
            log(f"[SLOT {merchant_id}] Failed to delete from DB: {e}")

        # 清除浏览器缓存文件
        session_dir = self._session_dir(merchant_id)
        import shutil
        import threading
        
        def _delayed_delete():
            import time
            time.sleep(2)
            try:
                if os.path.exists(session_dir):
                    shutil.rmtree(session_dir, ignore_errors=True)
            except Exception:
                pass
                
        threading.Thread(target=_delayed_delete, daemon=True).start()
        log(f"[SLOT {merchant_id}] Slot deleted.")
