"""
Search Cascade dùng chung — trích xuất & tổng quát hoá từ t0_search.py của
rulesworldsimulator (Playwright thật, anti-ban, cascade nhiều engine).

Chỉ Module 2 (Sự kiện) và bước 2 của Module 3 (ngữ cảnh nhân vật) dùng file
này. Module 1 (thời tiết) KHÔNG dùng — đó là luồng API sạch, không cần giả
lập trình duyệt.
"""
import json
import logging
import os
import random
import urllib.parse

from playwright.sync_api import sync_playwright

from config import shared
from shared.stealth import get_random_ua, human_delay
from shared.domain_ban import is_banned, record_failure, record_success

logger = logging.getLogger(__name__)

MAX_ENGINE_ATTEMPTS = 2
RETRY_DELAY_RANGE_MS = (1500, 3500)


def _load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _unwrap_redirect(href: str) -> str:
    if href.startswith("/url?") or "google.com/url?" in href:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "q" in qs and qs["q"]:
            href = qs["q"][0]
    parsed = urllib.parse.urlparse(href)
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def _domain_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.replace("www.", "")


class SearchCascade:
    """
    Dùng: SearchCascade().search(query, max_links=20)
    Trả về list[{"url", "title", "engine"}], đã lọc banned_domains +
    domain đang trong cooldown ban, ưu tiên priority_sources nếu có cấu hình.
    """

    def __init__(self):
        self.engines_config = _load_json(shared.ENGINES_FILE, {"engines": [], "banned_domains": [], "priority_sources": []})
        self.blackbook = _load_json(shared.BLACKBOOK_FILE, {})

    def _save_blackbook(self):
        _save_json(shared.BLACKBOOK_FILE, self.blackbook)

    def _fetch_links_from_engine(self, page, engine: dict, query: str) -> list[dict]:
        engine_name = engine.get("name", "Engine")
        link_selector = engine.get("link_selector", "a[href]")
        exclude_domain = engine.get("exclude_domain_in_href", "")
        timeout_ms = 20000

        encoded = urllib.parse.quote_plus(query)
        if engine.get("method", "GET").upper() == "POST":
            search_url = engine["url_template"] + "?query=" + encoded + "&cat=web"
        else:
            search_url = engine["url_template"].format(query=encoded)

        last_error = None
        for attempt in range(1, MAX_ENGINE_ATTEMPTS + 1):
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(random.randint(1200, 2500))

                found, seen = [], set()
                for a in page.locator(link_selector).all():
                    href = a.get_attribute("href") or ""
                    href = _unwrap_redirect(href)
                    title = (a.inner_text() or "").strip()

                    if not href.startswith("http"):
                        continue
                    if exclude_domain and exclude_domain in href.lower():
                        continue
                    if href in seen:
                        continue

                    seen.add(href)
                    found.append({"url": href, "title": title[:100], "engine": engine_name.lower()})

                return found
            except Exception as e:
                last_error = e
                logger.warning(f"   {engine_name} attempt {attempt}/{MAX_ENGINE_ATTEMPTS} lỗi: {e}")
                page.wait_for_timeout(random.randint(*RETRY_DELAY_RANGE_MS))

        logger.warning(f"   {engine_name} bỏ cuộc sau {MAX_ENGINE_ATTEMPTS} lần ({last_error})")
        return []

    def _launch_page(self, p):
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=get_random_ua(),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        return browser, context.new_page()

    def _search_with_page(self, page, query: str, max_links: int) -> list[dict]:
        all_links = []
        seen_urls = set()
        banned_domains = set(self.engines_config.get("banned_domains", []))
        priority_sources = self.engines_config.get("priority_sources", [])
        engines = sorted(self.engines_config.get("engines", []), key=lambda x: x.get("priority", 99))

        for engine in engines:
            if len(all_links) >= max_links:
                break

            logger.info(f"   🔍 Thử {engine.get('name')} cho: {query!r}")
            engine_links = self._fetch_links_from_engine(page, engine, query)

            for link in engine_links:
                if len(all_links) >= max_links:
                    break
                url = link["url"]
                domain = _domain_of(url)

                if domain in banned_domains:
                    continue
                if is_banned(self.blackbook, domain):
                    continue
                if url in seen_urls:
                    continue

                seen_urls.add(url)
                link["domain"] = domain
                link["is_priority_source"] = domain in priority_sources
                all_links.append(link)

            human_delay(shared.MIN_REQUEST_DELAY, shared.MAX_REQUEST_DELAY)

        return all_links

    def search(self, query: str, max_links: int = 20) -> list[dict]:
        """Tìm 1 query. Launch + đóng browser riêng cho lần gọi này.

        Dùng khi chỉ cần 1 query độc lập (vd. Module 2/3, mỗi lần gọi cách
        nhau bởi công việc khác). Nếu cần gọi nhiều query liên tiếp trong
        cùng 1 lần chạy, dùng `search_batch()` để tái sử dụng 1 browser
        instance thay vì launch lại mỗi lần (xem BUG-2 trong review).
        """
        with sync_playwright() as p:
            browser, page = self._launch_page(p)
            try:
                links = self._search_with_page(page, query, max_links)
            finally:
                browser.close()

        self._save_blackbook()
        return links

    def search_batch(self, queries: list[str], max_links_per_query: int = 20) -> dict[str, list[dict]]:
        """Tìm nhiều query, tái sử dụng 1 browser instance duy nhất.

        Tránh launch Chromium (~2-5s) riêng cho mỗi query — quan trọng khi
        có nhiều keyword cần tìm trong 1 lần chạy (vd. Module 4 search
        cascade), nơi launch-per-query có thể đẩy tổng runtime vượt
        timeout của CI job.
        """
        results: dict[str, list[dict]] = {}
        with sync_playwright() as p:
            browser, page = self._launch_page(p)
            try:
                for query in queries:
                    results[query] = self._search_with_page(page, query, max_links_per_query)
            finally:
                browser.close()

        self._save_blackbook()
        return results

    def mark_result(self, domain: str, success: bool):
        """Ghi nhận kết quả scrape thật sự (sau khi tải nội dung trang) để
        cập nhật domain_ban — gọi từ tầng scrape/downstream, không phải ở
        đây, vì search cascade chỉ tìm link chứ không tải nội dung."""
        if success:
            record_success(self.blackbook, domain)
        else:
            record_failure(self.blackbook, domain)
        self._save_blackbook()
