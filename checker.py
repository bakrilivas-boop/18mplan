"""
Google One / Jio 18个月 AI Pro 激活链接检测引擎
"""
import os
import sys
import re
import time
from datetime import datetime
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable

import requests

def get_effective_proxy(proxy_str):
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()
    # 如果运行在云端（如 Vercel / Linux 服务器），而代理填了本地 127.0.0.1 或 localhost，则自动转为直连
    if os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or os.environ.get('RENDER'):
        if '127.0.0.1' in proxy_str or 'localhost' in proxy_str:
            return None
    return proxy_str

# 状态常量定义
STATUS_ACTIVE = "ACTIVE"          # 有效未被使用
STATUS_USED = "USED"              # 已失效/已被使用
STATUS_INVALID = "INVALID"        # 链接无效/已过期
STATUS_NEED_AUTH = "NEED_AUTH"    # 需要Cookie或Cookie已失效
STATUS_INELIGIBLE = "INELIGIBLE"  # 账号不符合条件
STATUS_ERROR = "ERROR"            # 网络或请求错误

STATUS_LABELS = {
    STATUS_ACTIVE: {"text": "有效 (未激活)", "color": "green", "badge": "🟢 有效 · 可激活", "tag": "[有效]"},
    STATUS_USED: {"text": "已失效 (已被使用)", "color": "red", "badge": "🔴 已失效 · 已使用", "tag": "[已失效]"},
    STATUS_INVALID: {"text": "链接无效/过期", "color": "orange", "badge": "⚠️ 格式错误/过期", "tag": "[无效]"},
    STATUS_NEED_AUTH: {"text": "需要Google Cookie", "color": "yellow", "badge": "🟡 需配置Cookie", "tag": "[需Cookie]"},
    STATUS_INELIGIBLE: {"text": "账号不符合条件", "color": "purple", "badge": "🟣 不符合资格", "tag": "[不符资格]"},
    STATUS_ERROR: {"text": "网络/请求异常", "color": "gray", "badge": "❌ 检测失败", "tag": "[失败]"},
}


def extract_token_and_normalize_url(raw_input: str) -> tuple[str, str]:
    """
    提取激活Token并规范化为标准的 one.google.com 激活URL（避免 serviceactivation 跨域丢失 Cookie）
    """
    raw_input = raw_input.strip()
    if not raw_input:
        return "", ""

    # 提取可能的URL
    url_match = re.search(r'https?://[^\s]+', raw_input)
    if url_match:
        url = url_match.group(0)
    else:
        url = raw_input

    # 尝试从路径中抽取Token
    token_match = re.search(r'(?:subscription/new/|activate-plan/subscription/new/)([A-Za-z0-9_\-+=]+)', url)
    if token_match:
        token = token_match.group(1)
    else:
        # 如果整段看起来像Token
        if re.match(r'^[A-Za-z0-9_\-+=]{20,}$', url):
            token = url
        else:
            token = url

    # 直接规范化为 one.google.com 激活直达地址
    normalized_url = f"https://one.google.com/activate-plan/subscription/new/{token}"
    return token, normalized_url


def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    """
    将任意格式的Cookie输入（纯Cookie串、带Cookie:前缀、cURL命令等）智能提取并解析为字典
    """
    cookies = {}
    if not cookie_str:
        return cookies

    cleaned = cookie_str.strip()

    # 兼容从 cURL 复制进来的内容: 提取 -H 'cookie: xxx' 或 -H 'Cookie: xxx'
    curl_match = re.search(r'''-[hH]\s+['"](?:[cC]ookie:\s*)?([^'"]+)['"]''', cleaned)
    if curl_match:
        cleaned = curl_match.group(1)

    # 兼容带有 "Cookie: " 或 "cookie: " 前缀
    if cleaned.lower().startswith("cookie:"):
        cleaned = cleaned[7:].strip()

    # 移除首尾可能的多余引号
    cleaned = cleaned.strip("\"'")

    items = cleaned.split(";")
    for item in items:
        if "=" in item:
            k, v = item.strip().split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                cookies[k] = v
    return cookies


def get_token_snippet(token: str) -> str:
    """生成易识别的前后标识片段，例如: AQCpiI...7Fg=="""
    if not token:
        return "-"
    if len(token) <= 20:
        return token
    return f"{token[:10]}...{token[-8:]}"


def extract_expiration_info(html_content: str) -> tuple[str, str, str]:
    """
    从页面 HTML 中提取链接激活截止期限、剩余倒计时及方案权益有效期
    返回: (expire_deadline_text, remaining_time_str, plan_valid_until)
    """
    expire_deadline_text = ""
    expire_date = None
    remaining_time_str = "-"

    # 1. 中文匹配: 优惠酬宾，(\d+) 月 (\d+) 日截止 或 (\d+)月(\d+)日截止
    m1 = re.search(r'(?:优惠[\u4e00-\u9fa5]*[，,]\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日截止', html_content)
    if m1:
        month = int(m1.group(1))
        day = int(m1.group(2))
        year = datetime.now().year
        expire_date = datetime(year, month, day, 23, 59, 59)
        # 若当前时间已过该日期超60天，判断为跨年
        if datetime.now() > expire_date and (datetime.now() - expire_date).days > 60:
            expire_date = datetime(year + 1, month, day, 23, 59, 59)
        expire_deadline_text = f"{month}月{day}日截止"

    # 2. 中文包含年份: (\d{4})年(\d{1,2})月(\d{1,2})日
    if not expire_date:
        m2 = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:[前到至]|截止)', html_content)
        if m2:
            year = int(m2.group(1))
            month = int(m2.group(2))
            day = int(m2.group(3))
            expire_date = datetime(year, month, day, 23, 59, 59)
            expire_deadline_text = f"{year}年{month}月{day}日截止"

    # 3. 英文匹配: Offer ends (?:on )?October 26
    if not expire_date:
        m3 = re.search(r'Offer ends (?:on )?([A-Za-z]+)\s+(\d{1,2})(?:,?\s*(\d{4}))?', html_content, re.IGNORECASE)
        if m3:
            month_str, day_str, year_str = m3.group(1), m3.group(2), m3.group(3)
            expire_deadline_text = f"{month_str} {day_str} 截止"
            # 将英文月份名转为数字
            month_names = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            month_num = month_names.get(month_str.lower())
            if month_num:
                day = int(day_str)
                year = int(year_str) if year_str else datetime.now().year
                try:
                    expire_date = datetime(year, month_num, day, 23, 59, 59)
                    if not year_str and datetime.now() > expire_date and (datetime.now() - expire_date).days > 60:
                        expire_date = datetime(year + 1, month_num, day, 23, 59, 59)
                except ValueError:
                    pass

    # 计算剩余倒计时
    if expire_date:
        now = datetime.now()
        delta = expire_date - now
        if delta.total_seconds() > 0:
            days = delta.days
            hours = int((delta.total_seconds() % 86400) // 3600)
            if days > 0:
                remaining_time_str = f"还剩 {days} 天 {hours} 小时"
            else:
                remaining_time_str = f"还剩 {hours} 小时"
        else:
            remaining_time_str = "已到期失效"

    # 4. 提取方案激活后的到期时间（例如：方案将于 28 2月 2028到期）
    plan_expire_match = re.search(r'方案将于\s*([0-9\u4e00-\u9fa5A-Za-z\s]+)\s*到期', html_content)
    plan_valid_until = plan_expire_match.group(1).strip() if plan_expire_match else "18个月 (至2028年)"

    return expire_deadline_text, remaining_time_str, plan_valid_until


class LinkChecker:
    def __init__(self, proxy=None, cookie=None, timeout=15):
        self.proxy = get_effective_proxy(proxy)
        self.cookie_str = cookie or ""
        self.timeout = timeout
        self.cookies_dict = parse_cookie_string(self.cookie_str)

    def _get_proxies_dict(self) -> Optional[dict]:
        if not self.proxy:
            return None
        proxy_url = self.proxy.strip()
        if not proxy_url:
            return None
        if not (proxy_url.startswith("http://") or proxy_url.startswith("https://") or proxy_url.startswith("socks5://") or proxy_url.startswith("socks5h://")):
            proxy_url = "http://" + proxy_url
        return {"http": proxy_url, "https": proxy_url}

    def check_single_link(self, raw_input: str, original_index: int = 1) -> dict:
        """
        检测单个链接的活性状态与时效性
        """
        token, url = extract_token_and_normalize_url(raw_input)
        snippet = get_token_snippet(token)

        if not token:
            return {
                "index": original_index,
                "raw_input": raw_input,
                "token": "",
                "token_snippet": "-",
                "url": "",
                "status": STATUS_INVALID,
                "status_label": STATUS_LABELS[STATUS_INVALID]["text"],
                "status_badge": STATUS_LABELS[STATUS_INVALID]["badge"],
                "details": "输入内容为空或无法识别有效激活链接",
                "plan_info": "-",
                "expire_deadline": "-",
                "remaining_time": "-",
                "plan_valid_until": "-",
                "duration_ms": 0,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        start_time = time.time()
        proxies = self._get_proxies_dict()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        if self.cookie_str:
            clean_cookie = "; ".join([f"{k}={v}" for k, v in self.cookies_dict.items()]) if self.cookies_dict else self.cookie_str
            headers["Cookie"] = clean_cookie

        try:
            session = requests.Session()
            session.headers.update(headers)
            if proxies:
                session.proxies = proxies

            if self.cookies_dict:
                for k, v in self.cookies_dict.items():
                    session.cookies.set(k, v, domain=".google.com")
                    session.cookies.set(k, v, domain="one.google.com")

            response = session.get(url, timeout=self.timeout, allow_redirects=True)
            status_code = response.status_code
            final_url = str(response.url)
            html_text = response.text
            duration_ms = int((time.time() - start_time) * 1000)

            res = self._analyze_response(raw_input, token, url, status_code, final_url, html_text, duration_ms)
            res["index"] = original_index
            res["token_snippet"] = snippet
            return res

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            err_msg = str(e)
            if "ProxyError" in err_msg or "ConnectTimeout" in err_msg or "ConnectionRefused" in err_msg or "proxy" in err_msg.lower():
                details = f"网络代理连接失败: {err_msg[:80]} (请确认代理软件 7890 端口已开启)"
            else:
                details = f"请求异常: {err_msg[:100]}"

            return {
                "index": original_index,
                "raw_input": raw_input,
                "token": token,
                "token_snippet": snippet,
                "url": url,
                "status": STATUS_ERROR,
                "status_label": STATUS_LABELS[STATUS_ERROR]["text"],
                "status_badge": STATUS_LABELS[STATUS_ERROR]["badge"],
                "details": details,
                "plan_info": "-",
                "expire_deadline": "-",
                "remaining_time": "-",
                "plan_valid_until": "-",
                "duration_ms": duration_ms,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

    def _analyze_response(self, raw_input: str, token: str, url: str, status_code: int, final_url: str, html: str, duration_ms: int) -> dict:
        """
        根据返回的最终URL和HTML内容智能判定活性状态及提取剩余有效时间
        """
        # 1. 判定是否被重定向到 Google 登录页
        if "accounts.google.com/ServiceLogin" in final_url or "accounts.google.com/v3/signin" in final_url:
            return {
                "raw_input": raw_input,
                "token": token,
                "url": url,
                "status": STATUS_NEED_AUTH,
                "status_label": STATUS_LABELS[STATUS_NEED_AUTH]["text"],
                "status_badge": STATUS_LABELS[STATUS_NEED_AUTH]["badge"],
                "details": "请在右上角设置中填入 Google 账号 Cookie（未登录状态无法直接解析激活权益）",
                "plan_info": "需 Google Cookie",
                "expire_deadline": "-",
                "remaining_time": "-",
                "plan_valid_until": "-",
                "duration_ms": duration_ms,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        # 提取时效信息
        expire_deadline, remaining_time, plan_valid_until = extract_expiration_info(html)

        # 2. 判定是否已失效（已被使用） - 对应截图2
        used_keywords = [
            "订阅已在使用中",
            "此订阅链接已被使用",
            "已被使用",
            "探索 Google One 提供的福利和其他优惠",
            "探索 Google One",
            "Subscription is already in use",
            "This subscription link has already been used",
            "This subscription link has been used",
            "already been used",
            "already in use"
        ]
        for kw in used_keywords:
            if kw in html:
                return {
                    "raw_input": raw_input,
                    "token": token,
                    "url": url,
                    "status": STATUS_USED,
                    "status_label": STATUS_LABELS[STATUS_USED]["text"],
                    "status_badge": STATUS_LABELS[STATUS_USED]["badge"],
                    "details": "订阅已在使用中 / 此订阅链接已被兑换失效",
                    "plan_info": "已失效 (已使用)",
                    "expire_deadline": "已使用失效",
                    "remaining_time": "已失效",
                    "plan_valid_until": "-",
                    "duration_ms": duration_ms,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }

        # 3. 判定是否有效（未被使用，可激活） - 对应截图1
        active_keywords = [
            "激活Jio提供的Google AI Pro方案",
            "Jio提供的Google AI Pro方案",
            "Google AI Pro方案",
            "免费畅享 18 个月",
            "免费畅享 18",
            "18 个月",
            "18 months",
            "₹35,100",
            "35,100",
            "Nano Banana Pro",
            "5 TB",
            "切换方案",
            "立即激活",
            "Jio",
            "Activate the Google AI Pro plan",
            "Google AI Pro plan provided by Jio",
            "free for 18 months"
        ]
        match_count = sum(1 for kw in active_keywords if kw in html)
        if match_count >= 1:
            plan_info = "Jio 赠送 18个月 Google AI Pro (5TB + Gemini Pro)"
            deadline_str = f"（截止: {expire_deadline}）" if expire_deadline else ""
            return {
                "raw_input": raw_input,
                "token": token,
                "url": url,
                "status": STATUS_ACTIVE,
                "status_label": STATUS_LABELS[STATUS_ACTIVE]["text"],
                "status_badge": STATUS_LABELS[STATUS_ACTIVE]["badge"],
                "details": f"链接有效！尚未激活，可免费畅享 18 个月方案 {deadline_str}",
                "plan_info": plan_info,
                "expire_deadline": expire_deadline or "10月26日截止",
                "remaining_time": remaining_time if remaining_time != "-" else "有效",
                "plan_valid_until": plan_valid_until,
                "duration_ms": duration_ms,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        # 4. 判定是否链接格式错误或已过期
        if status_code in (404, 410):
            return {
                "raw_input": raw_input,
                "token": token,
                "url": url,
                "status": STATUS_INVALID,
                "status_label": STATUS_LABELS[STATUS_INVALID]["text"],
                "status_badge": STATUS_LABELS[STATUS_INVALID]["badge"],
                "details": f"激活链接已过期或不存在 (HTTP {status_code})",
                "plan_info": "无效/过期",
                "expire_deadline": "已过期",
                "remaining_time": "已过期",
                "plan_valid_until": "-",
                "duration_ms": duration_ms,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        invalid_keywords = [
            "优惠已过期",
            "此优惠已失效",
            "找不到页面",
            "页面不存在",
            "404 Not Found",
            "Invalid offer",
            "Offer expired",
            "This link is no longer valid"
        ]
        for kw in invalid_keywords:
            if kw in html:
                return {
                    "raw_input": raw_input,
                    "token": token,
                    "url": url,
                    "status": STATUS_INVALID,
                    "status_label": STATUS_LABELS[STATUS_INVALID]["text"],
                    "status_badge": STATUS_LABELS[STATUS_INVALID]["badge"],
                    "details": "激活链接已过期或不存在",
                    "plan_info": "无效/过期",
                    "expire_deadline": "已过期",
                    "remaining_time": "已过期",
                    "plan_valid_until": "-",
                    "duration_ms": duration_ms,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }

        # 5. 账号资格不符
        ineligible_keywords = ["不符合条件", "不符合此优惠的条件", "Not eligible"]
        for kw in ineligible_keywords:
            if kw in html:
                return {
                    "raw_input": raw_input,
                    "token": token,
                    "url": url,
                    "status": STATUS_INELIGIBLE,
                    "status_label": STATUS_LABELS[STATUS_INELIGIBLE]["text"],
                    "status_badge": STATUS_LABELS[STATUS_INELIGIBLE]["badge"],
                    "details": "当前检测账号不符合此方案资格（但链接可能仍然有效）",
                    "plan_info": "资格限制",
                    "expire_deadline": expire_deadline or "-",
                    "remaining_time": remaining_time,
                    "plan_valid_until": "-",
                    "duration_ms": duration_ms,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }

        # 6. 未知返回内容（带有 Google One 特征）
        if "one.google.com" in html or "Google One" in html:
            return {
                "raw_input": raw_input,
                "token": token,
                "url": url,
                "status": STATUS_ACTIVE,
                "status_label": STATUS_LABELS[STATUS_ACTIVE]["text"],
                "status_badge": STATUS_LABELS[STATUS_ACTIVE]["badge"],
                "details": "检测到 Google One 激活页面（有效）",
                "plan_info": "Google AI 方案",
                "expire_deadline": expire_deadline or "-",
                "remaining_time": remaining_time,
                "plan_valid_until": "-",
                "duration_ms": duration_ms,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        return {
            "raw_input": raw_input,
            "token": token,
            "url": url,
            "status": STATUS_ERROR,
            "status_label": STATUS_LABELS[STATUS_ERROR]["text"],
            "status_badge": STATUS_LABELS[STATUS_ERROR]["badge"],
            "details": f"返回页面未匹配到特征，HTTP状态码: {status_code}",
            "plan_info": "未知状态",
            "expire_deadline": "-",
            "remaining_time": "-",
            "plan_valid_until": "-",
            "duration_ms": duration_ms,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }


def check_google_cookie_validity(cookie_str: str, proxy: Optional[str] = None) -> tuple[bool, str]:
    """
    测试提供的 Google Cookie 是否有效能够访问 Google One 页面
    """
    if not cookie_str or not cookie_str.strip():
        return False, "Cookie 为空"

    proxies = None
    proxy = get_effective_proxy(proxy)
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    test_url = "https://one.google.com/"
    cookies_dict = parse_cookie_string(cookie_str)
    clean_cookie = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()]) if cookies_dict else cookie_str.strip()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Cookie": clean_cookie
    }

    try:
        s = requests.Session()
        s.headers.update(headers)
        if proxies:
            s.proxies = proxies
        if cookies_dict:
            for k, v in cookies_dict.items():
                s.cookies.set(k, v, domain=".google.com")
                s.cookies.set(k, v, domain="one.google.com")

        r = s.get(test_url, timeout=12, allow_redirects=True)
        final_url = str(r.url)
        if "accounts.google.com/ServiceLogin" in final_url or "accounts.google.com/v3/signin" in final_url:
            return False, "Cookie 已失效或未登录（已被重定向至登录页）"
        if r.status_code == 200:
            return True, "Cookie 有效！已成功连通 Google One 登录态"
        return True, f"Cookie 连接成功 (HTTP {r.status_code})"
    except Exception as e:
        return False, f"测试连接异常: {str(e)[:80]}"


class BatchChecker:
    """
    多线程批量链接检测器（严格保证返回结果与原始输入顺序 100% 一致）
    """
    def __init__(self, proxy: Optional[str] = None, cookie: Optional[str] = None, max_workers: int = 5, timeout: int = 15):
        self.checker = LinkChecker(proxy=proxy, cookie=cookie, timeout=timeout)
        self.max_workers = max_workers
        self.timeout = timeout
        self.is_running = False
        self.stop_requested = False

    def run(self, raw_lines: List[str], progress_callback: Optional[Callable[[int, int, dict], None]] = None) -> List[dict]:
        """
        执行批量检测任务，保证严格按输入原始顺序排序输出
        """
        indexed_inputs = []
        for idx, line in enumerate(raw_lines, start=1):
            line = line.strip()
            if line:
                indexed_inputs.append((idx, line))

        total = len(indexed_inputs)
        if total == 0:
            return []

        ordered_results = [None] * total
        self.is_running = True
        self.stop_requested = False
        completed_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_info = {
                executor.submit(self.checker.check_single_link, line, orig_idx): (arr_idx, orig_idx, line)
                for arr_idx, (orig_idx, line) in enumerate(indexed_inputs)
            }

            for future in as_completed(future_to_info):
                if self.stop_requested:
                    break
                arr_idx, orig_idx, line = future_to_info[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {
                        "index": orig_idx,
                        "raw_input": line,
                        "token": "",
                        "token_snippet": "-",
                        "url": line,
                        "status": STATUS_ERROR,
                        "status_label": STATUS_LABELS[STATUS_ERROR]["text"],
                        "status_badge": STATUS_LABELS[STATUS_ERROR]["badge"],
                        "details": f"执行异常: {str(e)}",
                        "plan_info": "-",
                        "expire_deadline": "-",
                        "remaining_time": "-",
                        "plan_valid_until": "-",
                        "duration_ms": 0,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                ordered_results[arr_idx] = res
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total, res)

        self.is_running = False
        final_results = [r for r in ordered_results if r is not None]
        return final_results
