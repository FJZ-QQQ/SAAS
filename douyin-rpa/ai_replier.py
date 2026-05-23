import requests
import json
import time
import random
import re
import os


class AIReplier:
    """通义千问 API — 带双链路容灾 + 智能重试 + 阶梯留资"""
    def __init__(self, api_key: str, bot_id: str = ""):
        self.api_key = api_key
        self.bot_id = bot_id
        self._reply_count = {}    # user_id -> count
        self._lead_saved = {}     # user_id -> True (已留资)
        self._history = {}        # user_id -> [{"role":..., "content":...}, ...]
        self._api_stats = {"success": 0, "fail": 0, "fallback": 0}  # API 调用统计
        self._last_success_time = time.time()  # 上次 API 成功时间
        self._sensitive_words = []  # 敏感词列表
        self._load_sensitive_words()

    def _load_sensitive_words(self):
        """从 JSON 文件加载敏感词列表"""
        try:
            sw_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_configs", "sensitive_words.json")
            if os.path.exists(sw_file):
                with open(sw_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._sensitive_words = data.get("words", [])
                print(f"[AI] 已加载 {len(self._sensitive_words)} 个敏感词")
        except Exception as e:
            print(f"[AI] 敏感词加载失败: {e}")

    def _filter_sensitive(self, reply: str, agent_config: dict) -> str:
        """检查并过滤敏感词，命中则替换为安全回复"""
        # 每次检查前重新加载（支持热更新）
        self._load_sensitive_words()
        if not self._sensitive_words:
            return reply
        for word in self._sensitive_words:
            if word and word in reply:
                nickname = agent_config.get('nickname', '小橙')
                print(f"[AI] ⚠ 敏感词拦截: '{word}' in '{reply[:50]}'")
                return f"感谢您的咨询！{nickname}为您服务，有什么具体问题我可以帮您解答的吗？"  
        return reply

    def get_stats(self):
        """获取 API 调用统计"""
        return {
            **self._api_stats,
            "success_rate": round(self._api_stats["success"] / max(1, self._api_stats["success"] + self._api_stats["fail"]) * 100, 1),
            "last_success": self._last_success_time
        }

    def get_reply(self, user_text: str, agent_config: dict, user_id: str = "default_user") -> str:
        # 记录该用户的对话轮次
        self._reply_count[user_id] = self._reply_count.get(user_id, 0) + 1
        turn = self._reply_count[user_id]
        
        if user_id not in self._history:
            self._history[user_id] = []
        
        # ★ 仅检测联系方式（手机号/微信号）— 留资核心逻辑，必须优先
        contact_reply = self._check_contact(user_text, agent_config, user_id)
        if contact_reply:
            print(f"[AI] 留资检测命中: {contact_reply[:60]}")
            return contact_reply
        
        # ★ 调用 AI API（带重试 + 容灾）
        ai_reply = self._call_with_retry(user_text, agent_config, user_id)
        if ai_reply:
            # ★ 敏感词过滤
            ai_reply = self._filter_sensitive(ai_reply, agent_config)
            return ai_reply
        
        # ★ 所有 API 都失败时的兜底 — 绝不静默
        self._api_stats["fallback"] += 1
        print(f"[AI] 所有 API 失败，使用兜底回复 (累计兜底: {self._api_stats['fallback']})")
        return self._fallback(agent_config, user_text, user_id, turn)

    async def get_reply_async(self, user_text: str, agent_config: dict, user_id: str = "default_user") -> str:
        """异步版本：将阻塞的 HTTP 请求放入线程池，不阻塞事件循环"""
        import asyncio
        return await asyncio.to_thread(self.get_reply, user_text, agent_config, user_id)

    def _call_with_retry(self, user_text: str, agent_config: dict, user_id: str) -> str:
        """★ 智能重试 + 双链路容灾"""
        
        # 第1次尝试：主 API（qwen-plus）
        reply = self._call_qwen_api(user_text, agent_config, user_id, model="qwen-plus", timeout=10)
        if reply:
            return reply
        
        print("[AI] ⚠ 主 API 失败，启动重试（降级模型）...")
        time.sleep(0.5)
        
        # 第2次尝试：降级模型（qwen-turbo 更快更稳定）
        reply = self._call_qwen_api(user_text, agent_config, user_id, model="qwen-turbo", timeout=8)
        if reply:
            print("[AI] ✅ 降级模型成功")
            return reply
        
        print("[AI] ✗ 所有 API 链路均失败")
        return None

    def _call_qwen_api(self, user_text: str, agent_config: dict, user_id: str, 
                       model: str = "qwen-plus", timeout: int = 10) -> str:
        """调用阿里云通义千问 API（OpenAI 兼容模式）"""
        if not self.api_key:
            print("[AI] ⚠ API 密钥未配置")
            return None
        
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # ★ 构建 system prompt
        nickname = agent_config.get('nickname', '小橙')
        persona = agent_config.get('persona', '')
        knowledge = agent_config.get('knowledge_base', '')
        turn = self._reply_count.get(user_id, 1)
        
        system_parts = [f"你是一个名叫\u300c{nickname}\u300d的AI客服助手\uff0c\u5fc5\u987b\u7528\u300c{nickname}\u300d\u8fd9\u4e2a\u540d\u5b57\u81ea\u79f0\u3002"]
        if persona:
            system_parts.append(f"\u4f60\u7684\u4eba\u8bbe\u548c\u884c\u4e3a\u51c6\u5219\uff1a{persona}")
        if knowledge:
            system_parts.append(f"\u4ee5\u4e0b\u662f\u4f60\u5fc5\u987b\u53c2\u8003\u7684\u6838\u5fc3\u77e5\u8bc6\u5e93\uff0c\u56de\u7b54\u5ba2\u6237\u95ee\u9898\u65f6\u4f18\u5148\u4f7f\u7528\u8fd9\u4e9b\u4fe1\u606f\uff1a\n{knowledge}\n\u8bf7\u57fa\u4e8e\u4ee5\u4e0a\u5185\u5bb9\u51c6\u786e\u56de\u7b54\u5ba2\u6237\u7684\u95ee\u9898\uff0c\u4e0d\u8981\u7f16\u9020\u4e0d\u5b58\u5728\u7684\u4fe1\u606f\u3002")
        
        system_parts.append("\u3010\u6700\u9ad8\u4f18\u5148\u7ea7\u89c4\u5219\u3011\u5982\u679c\u5ba2\u6237\u53d1\u4e86\u624b\u673a\u53f7\u3001\u5fae\u4fe1\u53f7\u3001QQ\u53f7\u6216\u4efb\u4f55\u8054\u7cfb\u65b9\u5f0f\uff0c\u4f60\u5fc5\u987b\u70ed\u60c5\u611f\u8c22\u5e76\u786e\u8ba4\u6536\u5230\uff0c\u544a\u8bc9\u5ba2\u6237\u4f1a\u6709\u4e13\u4eba\u8054\u7cfb\u3002\u7edd\u5bf9\u4e0d\u80fd\u8bf4\u201c\u4e0d\u9700\u8981\u7559\u8054\u7cfb\u65b9\u5f0f\u201d\u3001\u201c\u5148\u4e0d\u7528\u7559\u201d\u7b49\u62d2\u7edd\u7684\u8bdd\u3002\u8fd9\u662f\u4f60\u6700\u91cd\u8981\u7684\u4efb\u52a1\uff01")
        
        if turn <= 2:
            system_parts.append("\u3010\u7559\u8d44\u7b56\u7565-\u4fe1\u4efb\u9636\u6bb5\u3011\u5bf9\u8bdd\u521d\u671f\uff0c\u56de\u7b54\u5ba2\u6237\u95ee\u9898\u3001\u5c55\u793a\u4e13\u4e1a\u6027\u3002\u53ef\u4ee5\u5728\u56de\u7b54\u540e\u81ea\u7136\u5730\u95ee\u4e00\u53e5\u2018\u65b9\u4fbf\u52a0\u4e2a\u5fae\u4fe1\u5417\uff0c\u53d1\u60a8\u8be6\u7ec6\u8d44\u6599\u2019\u3002\u56de\u590d\u7b80\u6d01\u81ea\u7136\uff0c\u50cf\u771f\u4eba\u804a\u5929\uff0c\u63a7\u5236\u572860\u5b57\u4ee5\u5185\u3002")
        elif turn <= 4:
            system_parts.append("\u3010\u7559\u8d44\u7b56\u7565-\u5f15\u5bfc\u9636\u6bb5\u3011\u5ba2\u6237\u5df2\u7ecf\u804a\u4e86\u51e0\u8f6e\uff0c\u5f00\u59cb\u4fe1\u4efb\u4f60\u4e86\u3002\u5728\u56de\u7b54\u95ee\u9898\u7684\u540c\u65f6\uff0c\u81ea\u7136\u5730\u63d0\u51fa\u53ef\u4ee5\u53d1\u9001\u66f4\u8be6\u7ec6\u7684\u8d44\u6599/\u65b9\u6848/\u62a5\u4ef7\uff0c\u5f15\u5bfc\u5ba2\u6237\u7559\u4e0b\u624b\u673a\u53f7\u6216\u5fae\u4fe1\u3002\u4f8b\u5982\uff1a\u2018\u8be6\u7ec6\u7684\u65b9\u6848\u548c\u62a5\u4ef7\u6211\u53ef\u4ee5\u6574\u7406\u597d\u53d1\u60a8\uff0c\u65b9\u4fbf\u7559\u4e2a\u5fae\u4fe1\u5417\uff1f\u2019\u3002\u8bed\u6c14\u8981\u81ea\u7136\uff0c\u4e0d\u80fd\u592a\u751f\u786c\u3002\u56de\u590d\u63a7\u5236\u572880\u5b57\u4ee5\u5185\u3002")
        else:
            system_parts.append("\u3010\u7559\u8d44\u7b56\u7565-\u4fc3\u6210\u9636\u6bb5\u3011\u5df2\u7ecf\u804a\u4e86\u5f88\u591a\u8f6e\u4e86\uff0c\u5ba2\u6237\u6709\u660e\u786e\u9700\u6c42\u3002\u6bcf\u6b21\u56de\u590d\u90fd\u8981\u60f3\u529e\u6cd5\u5f15\u5bfc\u7559\u8d44\uff0c\u4f46\u8981\u7528\u4e0d\u540c\u7684\u8bdd\u672f\uff0c\u4e0d\u8981\u91cd\u590d\u3002\u53ef\u4ee5\u8bf4\uff1a\u2018\u6211\u8ba9\u4e13\u4e1a\u987e\u95ee\u7ed9\u60a8\u505a\u4e2a\u4e00\u5bf9\u4e00\u65b9\u6848\uff1f\u7559\u4e2a\u624b\u673a\u53f7\u5c31\u884c\u2019\u3001\u2018\u52a0\u4e2a\u5fae\u4fe1\u6211\u628a\u6848\u4f8b\u548c\u62a5\u4ef7\u4e00\u8d77\u53d1\u60a8\u2019\u7b49\u3002\u8bed\u6c14\u8bda\u6073\u4e0d\u6cb9\u817b\u3002\u56de\u590d\u63a7\u5236\u572860\u5b57\u4ee5\u5185\u3002")
        
        system_parts.append("\u683c\u5f0f\u8981\u6c42\uff1a\u4e0d\u8981\u7528markdown\u683c\u5f0f\uff0c\u4e0d\u8981\u7528emoji\u8868\u60c5\u7b26\u53f7\uff0c\u50cf\u771f\u4eba\u5fae\u4fe1\u804a\u5929\u4e00\u6837\u81ea\u7136\u3002")
        system_prompt = "\n".join(system_parts)
        
        stage = '信任' if turn <= 2 else '引导' if turn <= 4 else '促成'
        print(f"[AI] call: model={model}, nickname={nickname}, turn={turn}, stage={stage}")

        messages = [{"role": "system", "content": system_prompt}]
        if user_id in self._history:
            messages.extend(self._history[user_id][-10:])
        messages.append({"role": "user", "content": user_text})

        data = {
            "model": model,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 150,
            "top_p": 0.9
        }

        t0 = time.time()
        try:
            res = requests.post(url, headers=headers, json=data, timeout=timeout)
            elapsed = round(time.time() - t0, 2)
            
            if res.status_code != 200:
                self._api_stats["fail"] += 1
                print(f"[AI] HTTP {res.status_code} ({elapsed}s): {res.text[:200]}")
                return None

            result = res.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if answer:
                self._api_stats["success"] += 1
                self._last_success_time = time.time()
                
                # 记录到历史
                self._history.setdefault(user_id, [])
                self._history[user_id].append({"role": "user", "content": user_text})
                self._history[user_id].append({"role": "assistant", "content": answer})
                if len(self._history[user_id]) > 20:
                    self._history[user_id] = self._history[user_id][-10:]
                
                # 计算 token 用量
                usage = result.get("usage", {})
                tokens = usage.get("total_tokens", "?")
                print(f"[AI] ✅ {model} ({elapsed}s, {tokens}tok): {answer[:80]}")
                return answer
            
            self._api_stats["fail"] += 1
            print(f"[AI] {model} 响应无内容 ({elapsed}s)")
            return None

        except requests.exceptions.Timeout:
            elapsed = round(time.time() - t0, 2)
            self._api_stats["fail"] += 1
            print(f"[AI] {model} 超时 ({elapsed}s)")
            return None
        except requests.exceptions.ConnectionError:
            self._api_stats["fail"] += 1
            print(f"[AI] {model} 连接失败（网络问题）")
            return None
        except Exception as e:
            self._api_stats["fail"] += 1
            print(f"[AI] {model} 异常: {e}")
            return None

    def _extract_contact(self, text: str) -> dict:
        """从文本中提取手机号或微信号（高容错版）"""
        cleaned = text.strip()
        # 预处理：去掉所有空格和常见分隔符后匹配手机号
        digits_only = re.sub(r'[\s\-\.·•/\\]+', '', cleaned)
        
        # ===== 1. 手机号（高容错） =====
        # 1a. 标准11位手机号
        phone = re.search(r'1[3-9]\d{9}', digits_only)
        if phone:
            return {"type": "phone", "value": phone.group()}
        
        # 1b. 带空格/横线的手机号：139 1234 5678, 139-1234-5678
        phone_spaced = re.search(r'(1[3-9]\d)\s*[-\.]?\s*(\d{4})\s*[-\.]?\s*(\d{4})', cleaned)
        if phone_spaced:
            return {"type": "phone", "value": phone_spaced.group(1) + phone_spaced.group(2) + phone_spaced.group(3)}
        
        # 1c. 带+86前缀
        phone86 = re.search(r'\+?86\s*-?\s*(1[3-9]\d{9})', digits_only)
        if phone86:
            return {"type": "phone", "value": phone86.group(1)}
        
        # ===== 2. 带明确前缀的微信号 =====
        wx_patterns = [
            r'(?:wv|wx|vx|WX|VX|Wx|Vx|微信|weixin|Weixin|WEIXIN|我的微信|我微信|微信号|我的wx|我wx|我的vx|我vx)\s*[：:是]?\s*([a-zA-Z0-9][\w-]{3,25})',
            r'(?:加|＋)\s*(?:我|微信|wx|vx)?\s*([a-zA-Z0-9][\w-]{3,25})',
            r'(?:q|Q|qq|QQ)\s*[：:是]?\s*(\d{5,12})',
        ]
        for pat in wx_patterns:
            m = re.search(pat, cleaned)
            if m:
                val = m.group(1)
                ctype = "qq" if re.match(r'^\d{5,12}$', val) else "wechat"
                return {"type": ctype, "value": val}
        
        # ===== 3. 口语化表达 =====
        oral_patterns = [
            r'(?:这是|我的是|号码是|号是|微信是|我的号|我号)\s*([a-zA-Z0-9][\w-]{3,25})',
            r'(?:给你|发你|告诉你|发给你|给您|发您)\s*([a-zA-Z0-9][\w-]{3,25})',
            r'(?:联系方式|联系我|找我)\s*[：:是]?\s*([a-zA-Z0-9][\w-]{3,25})',
        ]
        for pat in oral_patterns:
            m = re.search(pat, cleaned)
            if m:
                return {"type": "wechat", "value": m.group(1)}
        
        # ===== 4. 纯字母数字串（直接发ID的人）=====
        common_words = {
            'hello', 'thanks', 'sorry', 'please', 'thank', 'welcome', 'good', 'great',
            'follow', 'share', 'video', 'check', 'click', 'reply', 'right', 'wrong',
            'douyin', 'tiktok', 'weixin', 'wechat', 'taobao', 'alipay', 'price',
            'about', 'where', 'there', 'these', 'those', 'which', 'would', 'could',
            'should', 'think', 'first', 'after', 'being', 'while', 'still', 'never',
        }
        # 4a. 纯字母开头的ID（最常见微信号格式）
        if re.match(r'^[a-zA-Z][\w-]{3,25}$', cleaned):
            if cleaned.lower() not in common_words and len(cleaned) >= 5:
                return {"type": "wechat", "value": cleaned}
        
        # 4b. 纯数字5-12位（QQ号）
        if re.match(r'^\d{5,12}$', cleaned):
            return {"type": "qq", "value": cleaned}
        
        # 4c. 数字开头的混合ID
        if re.match(r'^\d[\w-]{4,25}$', cleaned) and not re.match(r'^\d+$', cleaned):
            return {"type": "wechat", "value": cleaned}
        
        # ===== 5. 文本中包含联系方式关键词 + 任意ID =====
        contact_keywords = ['微信', '手机', '电话', '联系', '加我', '加一下', 'wx', 'WX', 'vx', 'VX',
                           'qq', 'QQ', '号码', '号', '打我', '找我', '私我']
        if any(kw in cleaned for kw in contact_keywords):
            id_match = re.search(r'([a-zA-Z0-9][\w-]{3,25})', cleaned)
            if id_match and id_match.group(1).lower() not in common_words:
                return {"type": "wechat", "value": id_match.group(1)}
        
        return None

    def _maybe_contact(self, text: str) -> bool:
        """★ 模糊检测：文本看起来像联系方式但不确定（触发确认话术）"""
        cleaned = text.strip()
        
        # 短字母串（3-4个字符，可能是微信号缩写）
        if re.match(r'^[a-zA-Z][\w]{2,3}$', cleaned):
            return True
        
        # 包含"加"、"号"等但没提取到
        fuzzy_kw = ['加', '号', '联系', '方便', '留', '发', '怎么联系', '怎么找你', '你微信', '你电话',
                    '可以加', '能加', '想加', '留个', '留一个']
        if any(kw in cleaned for kw in fuzzy_kw):
            return True
        
        return False

    def _check_contact(self, user_text: str, agent_config: dict, user_id: str) -> str:
        """★ 留资核心逻辑（确定提取 + 模糊确认）"""
        nickname = agent_config.get('nickname', '小橙')
        text = user_text.strip()
        
        # ★ 确定命中 → 直接收录
        contact = self._extract_contact(text)
        if contact:
            self._lead_saved[user_id] = True
            ctype = contact["type"]
            if ctype == "phone":
                replies = [
                    "收到您的手机号了！我们的专属顾问会在3分钟内联系您，请保持手机畅通",
                    "好的，已记录您的手机号！顾问正在为您准备专属方案，马上就联系您",
                    f"太棒了，手机号已收到！{nickname}这就帮您安排最专业的顾问对接",
                ]
            elif ctype == "qq":
                replies = [
                    "收到您的QQ号了！专属顾问稍后会添加您，请注意通过好友请求",
                    f"QQ号已记录！{nickname}已安排顾问添加您，请留意好友申请",
                ]
            else:
                replies = [
                    "收到您的微信号了！专属顾问稍后会添加您，请注意通过好友请求",
                    "微信号已记录！我们的顾问很快就会加您，到时候会给您发详细资料",
                    f"好的！{nickname}已经把您的微信号转给了我们最专业的顾问，请留意好友申请",
                ]
            return random.choice(replies)
        
        # ★ 模糊命中 → 主动确认（不放过任何留资机会）
        if self._maybe_contact(text):
            confirms = [
                f"请问这是您的联系方式吗？方便的话留个手机号或微信号，我安排顾问直接联系您",
                f"收到！请问方便留个微信号或手机号吗？{nickname}好安排专人跟进您的需求",
                "是要留联系方式吗？直接发手机号或微信号就行，我帮您对接专属顾问",
            ]
            return random.choice(confirms)
        
        # ★ "已经留过了" 类回复
        already_left = ['留了', '留过了', '给了', '发了', '发过了', '我留了', '已经留了', '发过', '给过']
        if any(kw in text for kw in already_left):
            if self._lead_saved.get(user_id):
                return "好的，已经收到您的信息了！专属顾问很快会联系您，感谢您的耐心等待"
            else:
                return "不好意思，可能系统没有识别到，麻烦您再发一次手机号或微信号，我帮您记录"
        
        return None

    def _fallback(self, agent_config: dict, user_text: str = "", user_id: str = "default_user", turn: int = 1) -> str:
        """★ 仅在 API 完全不可用时才使用的兜底回复"""
        nickname = agent_config.get('nickname', '小橙')
        
        first_round = [
            f"你好呀！我是{nickname}，有什么可以帮您的吗？",
            f"Hi！感谢关注，{nickname}为您服务！有任何问题都可以问我哦",
        ]
        
        follow_up = [
            f"感谢您的咨询！有什么具体问题我可以帮您解答的吗？",
            f"您好！请问有什么需要了解的吗？{nickname}随时为您服务",
        ]
        
        if turn <= 1:
            return random.choice(first_round)
        else:
            return random.choice(follow_up)
