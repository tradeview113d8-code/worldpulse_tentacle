"""
dashboard/report.py — Cross-tentacle Dashboard (Layer 2)
=========================================================
Workflow thứ 5, độc lập, chạy lệch sau cả 4 module (xem
.github/workflows/module5_dashboard.yml). CHỈ đọc field envelope
(event_type, impact_weight, extracted_facts, created_at) từ 4 collection
Mongo — không biết và không cần biết cấu trúc nội bộ riêng của từng module
(Mục 3.1, Layer 2 của BLUEPRINT_WORLDPULSE_TENTACLE.md).

Đây là script ĐỌC-ONLY: không insert, không sửa dữ liệu, không gọi LLM.
"""
import logging
import os
from datetime import datetime, timezone

from config import weather, events, people, comedy
from shared.mongo import get_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# (tên hiển thị, emoji, module namespace có .COLLECTION)
TENTACLES = [
    ("Module 1 — Thời tiết Việt Nam", "🌦️", weather),
    ("Module 2 — Sự kiện cực đoan toàn cầu", "🌍", events),
    ("Module 3 — Nhân vật nổi bật", "👤", people),
    ("Module 4 — Hài hước & Đời sống", "😂", comedy),
]


def _collection_stats(collection_name: str) -> dict | None:
    """Đọc 4 field envelope + created_at qua 1 pipeline aggregate duy nhất
    (count, avg/max impact_weight, created_at gần nhất). Trả về None nếu
    collection rỗng (chưa có document nào còn hạn TTL)."""
    coll = get_collection(collection_name)
    pipeline = [
        {
            "$group": {
                "_id": None,
                "count": {"$sum": 1},
                "avg_impact_weight": {"$avg": "$impact_weight"},
                "max_impact_weight": {"$max": "$impact_weight"},
                "latest_created_at": {"$max": "$created_at"},
            }
        }
    ]
    result = list(coll.aggregate(pipeline))
    if not result:
        return None
    return result[0]


def _status_badge(stats: dict | None) -> str:
    """PASS nếu collection có ít nhất 1 document còn hạn TTL, FAIL nếu
    rỗng (module chưa chạy lần nào hoặc lỗi toàn phần khiến không ghi
    được document nào). Nền màu đặc, không hiệu ứng trong suốt (Mục 3.2)."""
    if stats and stats.get("count", 0) > 0:
        return "🟢 **PASS**"
    return "🔴 **FAIL**"


def _format_timestamp(dt) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_dashboard_markdown() -> str:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# 🧭 WorldPulse-Tentacle — Cross-Tentacle Dashboard",
        "",
        f"Tổng hợp trạng thái gần nhất của cả 4 xúc tu, tạo lúc `{now_iso}` (UTC).",
        "",
        "| Xúc tu | Trạng thái | Docs còn hạn TTL | impact_weight cao nhất | impact_weight trung bình | Lần ghi gần nhất (UTC) |",
        "|---|---|---|---|---|---|",
    ]

    for display_name, emoji, module_settings in TENTACLES:
        stats = _collection_stats(module_settings.COLLECTION)
        badge = _status_badge(stats)
        count = stats.get("count", 0) if stats else 0
        max_iw = stats.get("max_impact_weight") if stats else None
        avg_iw = stats.get("avg_impact_weight") if stats else None
        latest = stats.get("latest_created_at") if stats else None

        max_iw_str = f"{max_iw:.2f}" if isinstance(max_iw, (int, float)) else "—"
        avg_iw_str = f"{avg_iw:.2f}" if isinstance(avg_iw, (int, float)) else "—"

        lines.append(
            f"| {emoji} {display_name} | {badge} | {count} | {max_iw_str} | {avg_iw_str} | {_format_timestamp(latest)} |"
        )

    lines.append("")
    lines.append(
        "_Chỉ đọc 3 field envelope (`event_type`, `impact_weight`, `extracted_facts`) + `created_at` — "
        "không đụng vào cấu trúc nội bộ riêng của từng module._"
    )
    lines.append("")
    return "\n".join(lines)


def run():
    logger.info("=" * 60)
    logger.info("🧭 MODULE 5 — Cross-Tentacle Dashboard")
    logger.info("=" * 60)

    markdown = build_dashboard_markdown()
    logger.info("\n" + markdown)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    else:
        logger.info("   ℹ️ GITHUB_STEP_SUMMARY không tồn tại (chạy local) — chỉ log ra console.")

    logger.info("🏁 Module 5 hoàn tất.")


if __name__ == "__main__":
    run()
