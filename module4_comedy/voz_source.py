"""
Luồng 1 (Direct Fetch) — nhánh Voz.
=====================================
Voz (nền tảng XenForo) không có API JSON công khai như Reddit, nên phải
scrape HTML thuần (requests + BeautifulSoup, dùng stealth headers chung).

⚠️ RỦI RO ĐÃ BIẾT (giống caveat NCHMF/JTWC ở Module 1 — xem README): các
selector dưới đây dựa trên cấu trúc XenForo phổ biến nhưng CHƯA được kiểm
chứng trên DOM thật của voz.vn (có thể đổi theo phiên bản diễn đàn). Lỗi ở
đây là best-effort — không được để crash toàn Module 4, luôn try/except và
trả về [] nếu selector không khớp.
"""
import logging

import requests
from bs4 import BeautifulSoup

from config import comedy
from shared.stealth import get_stealth_headers

logger = logging.getLogger(__name__)
TIMEOUT = 15


def _get_soup(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=get_stealth_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning(f"   ⚠️ Voz fetch lỗi {url}: {e}")
        return None


def _list_thread_urls(limit: int) -> list[str]:
    soup = _get_soup(comedy.VOZ_THREAD_LIST_URL)
    if soup is None:
        return []

    urls = []
    for a in soup.select(comedy.VOZ_THREAD_LIST_SELECTOR)[:limit]:
        href = a.get("href")
        if not href:
            continue
        if href.startswith("/"):
            href = "https://voz.vn" + href
        urls.append(href)
    return urls


def _extract_thread_context_and_punchline(thread_url: str) -> dict | None:
    soup = _get_soup(thread_url)
    if soup is None:
        return None

    # Mỗi post là 1 <article class="message">, chứa content (bbWrapper) và
    # reaction links (reactionsBar-link) riêng của post đó. Trước đây code
    # lấy reaction_links từ soup.select() toàn trang (BUG-1: trộn lẫn
    # reaction của mọi post), giờ scope selector vào từng post_element để
    # đảm bảo 1 post ↔ đúng reaction score của chính nó.
    post_elements = soup.select(comedy.VOZ_POST_SELECTOR)
    if len(post_elements) < 2:
        return None

    op_content = post_elements[0].select_one(comedy.VOZ_POST_CONTENT_SELECTOR)
    op_text = (op_content or post_elements[0]).get_text(separator=" ", strip=True)

    reply_candidates = post_elements[1:]
    best_text = None
    best_score = -1

    for reply_post in reply_candidates:
        content_el = reply_post.select_one(comedy.VOZ_POST_CONTENT_SELECTOR)
        text = (content_el or reply_post).get_text(separator=" ", strip=True)

        score_el = reply_post.select_one(comedy.VOZ_REACTION_SCORE_SELECTOR)
        score = 0
        if score_el is not None:
            raw = score_el.get_text(strip=True)
            try:
                score = int("".join(ch for ch in raw if ch.isdigit()) or 0)
            except ValueError:
                score = 0

        if text and score >= best_score:
            best_score = score
            best_text = text

    if not best_text:
        first_content = reply_candidates[0].select_one(comedy.VOZ_POST_CONTENT_SELECTOR)
        best_text = (first_content or reply_candidates[0]).get_text(separator=" ", strip=True)

    return {"context": op_text, "punchline": best_text, "source_url": thread_url}


def fetch_top_threads() -> list[dict]:
    thread_urls = _list_thread_urls(comedy.VOZ_THREADS_PER_RUN)
    results = []
    for url in thread_urls:
        item = _extract_thread_context_and_punchline(url)
        if item:
            results.append(item)
    logger.info(f"   -> Voz (thư giãn): {len(results)} tình huống có punchline")
    return results
