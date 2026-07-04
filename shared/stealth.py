"""
Stealth utilities: Giả lập trình duyệt thật
- Rotate User-Agent
- Full Chrome/Firefox headers
- Random human-like delays
"""
import time
import random
import logging

logger = logging.getLogger(__name__)

# Danh sách User-Agent thực tế (cập nhật 2024)
USER_AGENTS = [
    # Chrome 120+ trên Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome trên Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Firefox 121+ trên Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Safari 17 trên Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge 120
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Headers giả lập Chrome thật (bắt buộc phải có sec-ch-ua, sec-fetch...)
CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

FIREFOX_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def get_random_ua() -> str:
    """Lấy 1 User-Agent ngẫu nhiên"""
    return random.choice(USER_AGENTS)


def get_stealth_headers() -> dict:
    """Trả về bộ headers ngụy trang hoàn chỉnh"""
    ua = get_random_ua()
    
    if "Firefox" in ua:
        headers = FIREFOX_HEADERS.copy()
    else:
        headers = CHROME_HEADERS.copy()
        # Cập nhật sec-ch-ua version khớp với UA
        if "Chrome/121" in ua:
            headers["Sec-Ch-Ua"] = '"Not A(Brand";v="99", "Chromium";v="121", "Google Chrome";v="121"'
        elif "Chrome/122" in ua:
            headers["Sec-Ch-Ua"] = '"Not A(Brand";v="99", "Chromium";v="122", "Google Chrome";v="122"'
        elif "Edg/" in ua:
            headers["Sec-Ch-Ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"'
    
    headers["User-Agent"] = ua
    return headers


def human_delay(min_sec: float = 8.0, max_sec: float = 15.0):
    """
    Delay giả lập con người
    - Random giữa min và max
    - Log thời gian chờ
    """
    delay = random.uniform(min_sec, max_sec)
    logger.info(f"   ⏳ Chờ {delay:.1f}s (giả lập con người)...")
    time.sleep(delay)


def keyword_break(min_sec: float = 30.0, max_sec: float = 60.0):
    """
    Nghỉ dài giữa các keyword
    Giúp tránh rate limit khi đổi từ khóa
    """
    delay = random.uniform(min_sec, max_sec)
    logger.info(f"\n   ☕ Nghỉ giữa keyword: {delay:.1f}s...")
    time.sleep(delay)
