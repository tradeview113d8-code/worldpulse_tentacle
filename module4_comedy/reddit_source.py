"""
Luồng 1 (Direct Fetch) — nhánh Reddit.
========================================
Dùng endpoint JSON công khai của Reddit (không cần OAuth cho đọc top posts
công khai): `/r/{sub}/top.json` và `/comments/{id}.json`. HTTP thuần, không
cần Playwright. Reddit yêu cầu User-Agent rõ ràng (không phải UA giả lập
trình duyệt) để tránh bị 429 — dùng UA mô tả bot theo đúng khuyến nghị của
Reddit, tách biệt với `shared/stealth.py` (dành cho browser-like scraping).
"""
import logging

import requests

from config import comedy

logger = logging.getLogger(__name__)

REDDIT_UA = "worldpulse-tentacle-module4/1.0 (personal research bot; contact via repo issues)"
TIMEOUT = 15


def _get_json(url: str, params: dict):
    try:
        resp = requests.get(
            url, params=params, headers={"User-Agent": REDDIT_UA}, timeout=TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"   ⚠️ Reddit fetch lỗi {url}: {e}")
        return None


def _fetch_top_comment(permalink: str) -> str | None:
    """Lấy 1 comment vote cao nhất (không phải AutoModerator/sticky) của bài."""
    url = f"{comedy.REDDIT_BASE_URL}{permalink}.json"
    data = _get_json(url, {"limit": 10, "sort": "top"})
    if not data or len(data) < 2:
        return None

    comments = data[1].get("data", {}).get("children", [])
    for c in comments:
        body = c.get("data", {}).get("body")
        author = (c.get("data", {}).get("author") or "").lower()
        if not body or body in ("[deleted]", "[removed]"):
            continue
        if "automoderator" in author:
            continue
        return body
    return None


def fetch_top_posts(subreddit: str, limit: int) -> list[dict]:
    """
    Trả về list[{"context", "punchline", "source_url"}] cho 1 subreddit —
    context = tiêu đề bài, punchline = comment vote cao nhất.
    Bỏ qua best-effort nếu subreddit riêng tư/không tồn tại/rate-limited.
    """
    url = f"{comedy.REDDIT_BASE_URL}/r/{subreddit}/top.json"
    data = _get_json(url, {"t": comedy.REDDIT_TIME_FILTER, "limit": limit})
    if not data:
        return []

    results = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title", "")
        permalink = post.get("permalink")
        is_self = post.get("is_self", False)
        if not title or not permalink:
            continue
        # Bỏ bài chỉ có link ảnh/video không kèm ngữ cảnh chữ (khó dùng làm
        # "tình huống" cho LLM downstream nếu không có mô tả bằng văn bản).
        selftext = post.get("selftext", "") if is_self else ""
        context = f"{title}. {selftext}".strip(". ").strip()

        punchline = _fetch_top_comment(permalink)
        if not punchline:
            continue

        results.append(
            {
                "context": context,
                "punchline": punchline,
                "source_url": f"{comedy.REDDIT_BASE_URL}{permalink}",
            }
        )
    logger.info(f"   -> r/{subreddit}: {len(results)} tình huống có punchline")
    return results


def fetch_all_configured() -> list[dict]:
    all_results = []
    for sub in comedy.REDDIT_SUBREDDITS:
        all_results.extend(fetch_top_posts(sub, comedy.REDDIT_POSTS_PER_SUB))
    return all_results
