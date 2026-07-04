"""
Luồng 2 (Search Cascade) cho Module 4.
=========================================
Dùng lại `shared/search_cascade.py` (Playwright + stealth, giống Module 2)
với 1 nhóm từ khóa mồi xoay vòng (module4_comedy/keywords.py). Sau khi có
link, tải nội dung bằng `shared.fetch.fetch_article` (logic generic, không
đặc thù module nào — trước đây import thẳng từ `module2_events.fetch`,
tạo coupling ngầm giữa 2 module lẽ ra độc lập; đã chuyển hàm sang `shared/`
để gỡ coupling đó, xem `shared/fetch.py`).
Punchline được rút ra bằng `extractive_summary` (câu điểm cao nhất, đã ưu
tiên câu chứa từ khóa mồi khớp với bài).
"""
import logging

from config import comedy
from shared.search_cascade import SearchCascade
from shared.summarizer import extractive_summary

from shared.fetch import fetch_article
from module4_comedy.keywords import get_next_keyword_group, commit as commit_keyword_group

logger = logging.getLogger(__name__)


def fetch_via_search() -> list[dict]:
    group_name, seed_keywords = get_next_keyword_group()
    cascade = SearchCascade()

    all_links = []
    batch_results = cascade.search_batch(seed_keywords, max_links_per_query=comedy.LINKS_PER_SEARCH)
    for kw in seed_keywords:
        links = batch_results.get(kw, [])
        for link in links:
            link["matched_keyword"] = kw
        all_links.extend(links)
        logger.info(f"   -> '{kw}': {len(links)} link")

    results = []
    seen_urls = set()
    for link in all_links:
        url = link["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        article = fetch_article(url)
        if article is None:
            cascade.mark_result(link["domain"], success=False)
            continue

        if len(article["text"]) < comedy.MIN_CONTEXT_CHARS:
            cascade.mark_result(link["domain"], success=False)
            continue

        cascade.mark_result(link["domain"], success=True)

        summary = extractive_summary(
            article["text"],
            domain_keywords=[link["matched_keyword"]],
            max_sentences=3,
            prefer_punchy=True,
        )
        key_facts = summary["key_facts"]
        if not key_facts:
            continue

        # Câu điểm cao nhất làm "punchline", phần còn lại (nếu có) làm context
        punchline = key_facts[0]
        context = link.get("title", "") or (key_facts[1] if len(key_facts) > 1 else punchline)

        results.append({"context": context, "punchline": punchline, "source_url": url})

    logger.info(f"   -> Search cascade nhóm '{group_name}': {len(results)} tình huống")

    if results:
        commit_keyword_group(group_name)
    else:
        logger.warning(f"   ⚠️ Nhóm '{group_name}' không thu được kết quả nào — không advance vòng xoay.")

    return results
