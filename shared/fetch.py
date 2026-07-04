"""
Tải nội dung bài viết (requests + BeautifulSoup, dùng chung stealth headers)
và bóc tách metadata thời gian xuất bản.

Trước đây sống ở `module2_events/fetch.py` — nhưng không có gì đặc thù
Module 2 trong `fetch_article()`/`_extract_published_date()` (generic HTTP
fetch + parse ngày xuất bản). Module 4 (`search_source.py`) từng import
thẳng từ `module2_events.fetch`, tạo coupling ngầm giữa 2 module lẽ ra độc
lập (nếu M2 đổi tên/signature hàm, M4 bị break). Chuyển phần generic vào
đây; `is_fresh_enough()` (dùng `events.MAX_ARTICLE_AGE_HOURS` — đặc thù
Module 2) vẫn ở lại `module2_events/fetch.py`, re-export `fetch_article`
từ đây để không phá code hiện có nào còn import từ module2_events.fetch.
"""
import json
import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from shared.stealth import get_stealth_headers

logger = logging.getLogger(__name__)

DATE_META_NAMES = [
    "article:published_time",
    "article:modified_time",
    "og:updated_time",
    "date",
    "pubdate",
    "publishdate",
    "DC.date.issued",
]

ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def fetch_article(url: str, timeout: int = 15) -> dict | None:
    """
    Trả về {"html", "text", "published_at": datetime|None} hoặc None nếu lỗi.
    KHÔNG dùng Playwright ở bước này (đã có link từ search cascade) — HTTP
    thuần + stealth headers là đủ cho phần lớn trang tin tức.
    """
    try:
        resp = requests.get(url, headers=get_stealth_headers(), timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"   ⚠️ Fetch lỗi {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    published_at = _extract_published_date(soup)

    # Loại bỏ script/style/nav trước khi lấy text thô cho summarizer
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())

    return {"html": resp.text, "text": text, "published_at": published_at}


def _extract_published_date(soup: BeautifulSoup):
    # 1) Meta tags chuẩn (Open Graph / article / Dublin Core)
    for name in DATE_META_NAMES:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            dt = _parse_date_str(tag["content"])
            if dt:
                return dt

    # 2) <time datetime="...">
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        dt = _parse_date_str(time_tag["datetime"])
        if dt:
            return dt

    # 3) JSON-LD (schema.org NewsArticle datePublished)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("datePublished"):
                dt = _parse_date_str(item["datePublished"])
                if dt:
                    return dt

    return None


def _parse_date_str(raw: str):
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        match = ISO_DATE_RE.search(raw)
        if match:
            try:
                return datetime.fromisoformat(match.group(0)).replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None
