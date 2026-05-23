import re

class LeadExtractor:
    @staticmethod
    def extract_phone(text: str) -> str | None:
        """提取中国大陆手机号"""
        pattern = r'(?:(?:\+|00)86)?1[3-9]\d{9}'
        match = re.search(pattern, text.replace(' ', '').replace('-', ''))
        return match.group(0) if match else None

    @staticmethod
    def extract_wechat(text: str) -> str | None:
        """提取微信号"""
        # 1. 带前缀的微信号
        pattern = r'(?:微信|v|V|vx|VX|加我|wv|Weixin|weixin)[\s:：]*([a-zA-Z][a-zA-Z0-9_-]{4,19})'
        match = re.search(pattern, text)
        if match:
            return match.group(1)
            
        # 2. 纯微信号（整条消息就是一个纯英文/数字微信号格式）
        cleaned = text.strip()
        common_words = {'hello', 'thanks', 'sorry', 'please', 'thank', 'welcome',
                        'follow', 'share', 'video', 'check', 'click', 'reply'}
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]{5,19}$', cleaned):
            if cleaned.lower() not in common_words:
                return cleaned
                
        return None

    @staticmethod
    def extract_all(text: str) -> dict:
        return {
            "phone": LeadExtractor.extract_phone(text),
            "wechat": LeadExtractor.extract_wechat(text)
        }
