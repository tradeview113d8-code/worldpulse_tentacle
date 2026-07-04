"""
Module 3: Xúc tu Nhân vật Nổi bật (cửa sổ 24h qua)
====================================================
Bước 1 (định danh, API thuần): Wikimedia Pageviews -> Wikidata P31=Q5.
Bước 2 (ngữ cảnh, tái sử dụng nhẹ): đúng 6 truy vấn (3 quốc tế + 3 VN) qua
search cascade (Playwright + stealth) rồi tóm tắt bằng summarizer.py.

Chạy 2 lần/ngày (12h/lần) — chỉ lưu tên + tóm tắt khách quan "vì sao nổi
bật hôm nay", KHÔNG gán ghép tính cách/số phận hư cấu ở trạm này.

--- TÁI CẤU TRÚC ENVELOPE (BLUEPRINT_WORLDPULSE_TENTACLE.md, Mục 1) ---
Mọi document ghi vào `notable_people` giờ đi qua `shared.envelope.build_envelope()`
trước khi `insert_with_ttl()`. impact_weight suy từ hạng pageview trong
TOP_N_PER_PROJECT (rank 1 > rank 3) — ở module này impact_weight mang
nghĩa "mức độ nổi bật", không phải "mức độ nguy hiểm", nhưng vẫn dùng
đúng tên field để World Simulator xử lý đồng nhất xuyên module.
extracted_facts giờ là list[str] (tách câu) thay vì 1 chuỗi duy nhất.
payload dùng key `trigger_event` (thay cho `context_summary` cũ) và bổ sung
`hot_score` để World Simulator biết mức độ viral hiện tại của nhân vật.
"""
import logging
import os
from datetime import datetime, timezone

from config import people
from shared.mongo import ensure_ttl_index, insert_with_ttl
from shared.search_cascade import SearchCascade
from shared.summarizer import extractive_summary
from shared.envelope import build_envelope, clamp01, EventType

from module3_people.pageviews import fetch_top_titles
from module3_people.wikidata_filter import filter_to_humans

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _identify_people() -> list[dict]:
    """Bước 1: trả về [{"name", "region", "rank"}] — đúng TOP_N_PER_PROJECT
    mỗi vùng. `rank` là hạng 1-indexed theo thứ tự pageview giảm dần trong
    chính vùng đó (rank=1 nổi bật nhất), giữ nguyên thứ tự trả về của
    filter_to_humans()."""
    identified = []
    for region, project in people.PROJECTS.items():
        lang = project.split(".")[0]
        raw_titles = fetch_top_titles(project, people.TOP_N_PER_PROJECT)
        humans = filter_to_humans(raw_titles, lang, people.TOP_N_PER_PROJECT)
        for rank, name in enumerate(humans, start=1):
            identified.append({"name": name, "region": region, "rank": rank})
        logger.info(f"   -> {region} ({project}): {humans}")
    return identified


def _gather_context(person: dict, cascade: SearchCascade) -> dict:
    """Bước 2: 1 truy vấn ngữ cảnh mỗi người (tổng 6 truy vấn/phiên)."""
    query = f"{person['name']} {people.CONTEXT_SEARCH_QUERY_SUFFIX}"
    links = cascade.search(query, max_links=5)

    combined_text = " ".join(link.get("title", "") for link in links)
    summary = extractive_summary(combined_text, max_sentences=3) if combined_text else {"summary": "", "key_facts": []}

    return {
        "trigger_event": summary["summary"],
        "key_facts": summary["key_facts"],
        "source_links": [link["url"] for link in links],
    }


def _people_impact_weight(rank: int) -> float:
    """rank=1 (nổi bật nhất) -> 1.0, rank=TOP_N_PER_PROJECT (thấp nhất
    trong top) -> gần 0, tuyến tính giữa 2 mốc đó."""
    top_n = people.TOP_N_PER_PROJECT
    if top_n <= 1:
        return 1.0
    return clamp01((top_n - rank + 1) / top_n)


def _emit_step_summary(status: str, saved: int, total: int, impact_weights: list[float]) -> None:
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
        "## 👤 Module 3 — Nhân vật nổi bật",
        "",
        "| Trạng thái | Documents mới | impact_weight cao nhất | impact_weight trung bình | Thời điểm chạy (UTC) |",
        "|---|---|---|---|---|",
        f"| {badge} | {saved}/{total} | {max_iw:.2f} | {avg_iw:.2f} | {now_iso} |",
        "",
    ]
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run():
    logger.info("=" * 60)
    logger.info("👤 MODULE 3 — Nhân vật nổi bật")
    logger.info("=" * 60)

    ensure_ttl_index(people.COLLECTION, people.TTL_HOURS)

    identified = _identify_people()
    if not identified:
        logger.warning("   ⚠️ Không định danh được nhân vật nào phiên này.")
        _emit_step_summary("FAIL", 0, 0, [])
        return

    cascade = SearchCascade()
    saved = 0
    impact_weights: list[float] = []

    for person in identified:
        context = _gather_context(person, cascade)
        impact_weight = _people_impact_weight(person["rank"])
        extracted_facts = context["key_facts"]

        payload = {
            "name": person["name"],
            "region": person["region"],
            "trigger_event": context["trigger_event"],
            "source_links": context["source_links"],
            "hot_score": 100,
        }
        doc = build_envelope(EventType.CHARACTER_SEED, impact_weight, extracted_facts, payload)
        insert_with_ttl(people.COLLECTION, doc, people.TTL_HOURS)
        saved += 1
        impact_weights.append(impact_weight)
        logger.info(f"   ✅ {person['name']} ({person['region']}, rank={person['rank']}, impact_weight={impact_weight:.2f})")

    logger.info(f"🏁 Module 3 hoàn tất: {saved} nhân vật đã lưu.")

    status = "PASS" if saved > 0 else "FAIL"
    _emit_step_summary(status, saved, len(identified), impact_weights)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        _emit_step_summary("FAIL", 0, 0, [])
        raise
