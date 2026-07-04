"""
Module 2: Xúc tu Sự kiện Cực đoan Toàn cầu (cửa sổ 48h qua)
=============================================================
Luồng: chọn nhóm chủ đề round-robin -> search cascade (Playwright thật,
kế thừa toàn vẹn) -> lọc theo priority nguồn (đảo ngược: tin thật > blog)
-> lọc bài quá 48h theo metadata -> tóm tắt bằng summarizer.py (impact
keywords) -> ghi Mongo với TTL 48h.

Chạy 2 lần/ngày (12h/lần). Chỉ thu thập "sự thật khách quan" — KHÔNG để
LLM tại trạm này diễn giải/hư cấu hoá (nhiệm vụ đó thuộc về Chimera).

--- TÁI CẤU TRÚC ENVELOPE (BLUEPRINT_WORLDPULSE_TENTACLE.md, Mục 1) ---
Mọi document ghi vào `extreme_events` giờ đi qua `shared.envelope.build_envelope()`
trước khi `insert_with_ttl()`. impact_weight suy từ source_priority (tin
càng uy tín, số càng nhỏ) kết hợp số matched_impact_keywords. extracted_facts
lọc lại từ key_facts (loại câu không chứa số liệu/thực thể cụ thể) thay vì
copy nguyên toàn bộ (Chỉ thị #5 blueprint).
"""
import logging
import os
import re
from datetime import datetime, timezone

from config import events
from shared.mongo import ensure_ttl_index, insert_with_ttl
from shared.search_cascade import SearchCascade
from shared.summarizer import extractive_summary
from shared.envelope import build_envelope, clamp01, EventType

from module2_events.topics import get_next_topic_group, commit_topic_group
from module2_events.source_priority import sort_by_priority, get_priority
from module2_events.fetch import fetch_article, is_fresh_enough

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAX_ARTICLES_TO_KEEP = 15

# === Ngưỡng suy ra impact_weight từ source_priority + matched_impact_keywords ===
# source_priority: 1 (Reuters/AP/AFP/BBC...) đến ~9 (blog/fandom mặc định 6-9
# theo config.events.SOURCE_PRIORITY). Chuẩn hoá tuyến tính: priority=1 -> 1.0,
# priority=9 -> 0.0.
SOURCE_PRIORITY_FLOOR = 1
SOURCE_PRIORITY_CEILING = 9
# Đủ 5 từ khoá tác động khớp trở lên coi là "bão hoà" điểm keyword (=1.0).
KEYWORD_SATURATION_COUNT = 5
PRIORITY_WEIGHT_IN_SCORE = 0.5
KEYWORD_WEIGHT_IN_SCORE = 0.5

# Câu chứa số liệu (bất kỳ chữ số nào) HOẶC chứa 1 trong IMPACT_KEYWORDS thì
# coi là "factual" (số liệu/thực thể/thời điểm cụ thể) — dùng để lọc lại
# key_facts trước khi đưa vào extracted_facts (Chỉ thị #5 blueprint).
_DIGIT_RE = re.compile(r"\d")


def _priority_norm(source_priority: int) -> float:
    span = SOURCE_PRIORITY_CEILING - SOURCE_PRIORITY_FLOOR
    return clamp01((SOURCE_PRIORITY_CEILING - source_priority) / span)


def _keyword_score(matched_keywords: list[str]) -> float:
    return clamp01(len(matched_keywords) / KEYWORD_SATURATION_COUNT)


def _events_impact_weight(source_priority: int, matched_keywords: list[str]) -> float:
    priority_score = _priority_norm(source_priority)
    keyword_score = _keyword_score(matched_keywords)
    return clamp01(PRIORITY_WEIGHT_IN_SCORE * priority_score + KEYWORD_WEIGHT_IN_SCORE * keyword_score)


def _looks_factual(sentence: str) -> bool:
    """True nếu câu chứa số liệu cụ thể HOẶC 1 từ khoá tác động thực tế đã
    biết — dùng để loại câu mang giọng bình luận/cảm xúc mà extractive_summary
    lỡ chọn (Chỉ thị #5)."""
    if _DIGIT_RE.search(sentence):
        return True
    sentence_lower = sentence.lower()
    return any(kw in sentence_lower for kw in events.IMPACT_KEYWORDS)


def _filter_factual_facts(key_facts: list[str]) -> list[str]:
    filtered = [s for s in key_facts if _looks_factual(s)]
    # Nếu lọc quá tay mất hết câu (bài viết factual nhưng không match từ
    # khoá/số liệu ở đúng câu được Luhn chọn), thà giữ lại key_facts gốc
    # còn hơn ghi extracted_facts rỗng cho 1 bài đã qua kiểm định nguồn.
    return filtered if filtered else key_facts


def _emit_step_summary(status: str, saved: int, topic_name: str, impact_weights: list[float]) -> None:
    """Ghi bảng Markdown Layer-1 (per-run summary) vào GITHUB_STEP_SUMMARY
    (Mục 3.1 blueprint) — bảng màu Pass/Fail/Timeout nền đặc (Mục 3.2)."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    badge = {
        "PASS": "🟢 **PASS**",
        "FAIL": "🔴 **FAIL**",
        "TIMEOUT": "🟠 **TIMEOUT**",
    }.get(status, f"⚪ **{status}**")

    max_iw = max(impact_weights) if impact_weights else 0.0
    avg_iw = (sum(impact_weights) / len(impact_weights)) if impact_weights else 0.0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "## 🌍 Module 2 — Sự kiện cực đoan toàn cầu",
        "",
        f"Nhóm chủ đề phiên này: `{topic_name}`",
        "",
        "| Trạng thái | Documents mới | impact_weight cao nhất | impact_weight trung bình | Thời điểm chạy (UTC) |",
        "|---|---|---|---|---|",
        f"| {badge} | {saved} | {max_iw:.2f} | {avg_iw:.2f} | {now_iso} |",
        "",
    ]
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run():
    logger.info("=" * 60)
    logger.info("🌍 MODULE 2 — Sự kiện cực đoan toàn cầu")
    logger.info("=" * 60)

    ensure_ttl_index(events.COLLECTION, events.TTL_HOURS)

    topic_name, queries = get_next_topic_group()
    cascade = SearchCascade()

    all_links = []
    for query in queries:
        links = cascade.search(query, max_links=events.LINKS_PER_SEARCH)
        for link in links:
            link["matched_query"] = query
        all_links.extend(links)
        logger.info(f"   -> '{query}': {len(links)} link")

    if not all_links:
        logger.warning("   ⚠️ Không tìm được link nào phiên này, kết thúc sớm.")
        _emit_step_summary("FAIL", 0, topic_name, [])
        return

    # Ưu tiên nguồn thật trước, tin đồn/blog sau
    all_links = sort_by_priority(all_links)

    saved_count = 0
    seen_urls = set()
    impact_weights: list[float] = []

    for link in all_links:
        if saved_count >= MAX_ARTICLES_TO_KEEP:
            break
        url = link["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        article = fetch_article(url)
        if article is None:
            cascade.mark_result(link["domain"], success=False)
            continue

        if not is_fresh_enough(article["published_at"]):
            logger.info(f"   ⏭️  Bỏ qua (quá {events.MAX_ARTICLE_AGE_HOURS}h): {url}")
            continue

        if len(article["text"]) < 200:
            cascade.mark_result(link["domain"], success=False)
            continue

        cascade.mark_result(link["domain"], success=True)

        summary = extractive_summary(
            article["text"],
            domain_keywords=events.IMPACT_KEYWORDS,
            max_sentences=6,
        )

        source_priority = get_priority(link["domain"])
        impact_weight = _events_impact_weight(source_priority, summary["matched_keywords"])
        extracted_facts = _filter_factual_facts(summary["key_facts"])

        payload = {
            "topic_group": topic_name,
            "matched_query": link.get("matched_query"),
            "url": url,
            "domain": link["domain"],
            "source_priority": source_priority,
            "title": link.get("title", ""),
            "published_at": article["published_at"],
            "summary": summary["summary"],
            "key_facts": summary["key_facts"],
            "matched_impact_keywords": summary["matched_keywords"],
        }
        doc = build_envelope(EventType.MACRO_DISRUPTION, impact_weight, extracted_facts, payload)
        insert_with_ttl(events.COLLECTION, doc, events.TTL_HOURS)
        saved_count += 1
        impact_weights.append(impact_weight)
        logger.info(f"   ✅ Đã lưu: {link.get('title', url)[:70]} (impact_weight={impact_weight:.2f})")

    if saved_count > 0:
        commit_topic_group(topic_name)
    logger.info(f"🏁 Module 2 hoàn tất: {saved_count} bài viết mới cho nhóm '{topic_name}'.")

    status = "PASS" if saved_count > 0 else "FAIL"
    _emit_step_summary(status, saved_count, topic_name, impact_weights)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        _emit_step_summary("FAIL", 0, "unknown", [])
        raise
