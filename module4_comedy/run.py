"""
Module 4: Xúc tu Hài hước & Đời sống (CRON 4)
================================================
Thu thập "tình huống gây cười" đã được cộng đồng mạng Việt Nam kiểm chứng
(qua vote/like), lưu vào `human_comedy_tropes` (TTL 30 ngày) làm nguyên
liệu bẻ lái cho tầng downstream (Chimera) khi kịch bản rơi vào vòng lặp.

Luồng thu thập (song song, không phụ thuộc nhau — lỗi 1 luồng không chặn
luồng còn lại):
  1. Direct Fetch: Reddit JSON API (r/VietNam, r/TroChuyenLinhTinh, ...) +
     Voz (best-effort HTML, xem caveat trong voz_source.py).
  2. Search Cascade: nhóm từ khóa mồi xoay vòng (round-robin theo lần chạy).

CHÚ Ý VỀ RANH GIỚI REPO (giống Module 2/3 — xem README):
  Repo này CHỈ gom nguyên liệu thô + lọc rác kỹ thuật cấp thấp (text_filter.py:
  bỏ link/SĐT/spam, ép giới hạn ký tự). Cơ chế "Circuit Breaker" mô tả trong
  biên bản (đếm lỗi kịch bản, ép LLM viết lại có twist, chạy qua
  `platform_and_legal_guardrails` đầy đủ) thuộc về pipeline chính của
  Chimera/CHIMERA WorldSim — nằm ở repo khác, có quyền truy cập LLM + luật
  kiểm duyệt platform mà repo này không có. Hàm `get_random_trope()` dưới
  đây chỉ là tiện ích ĐỌC Mongo cho pipeline đó gọi, KHÔNG tự chạy LLM.

--- TÁI CẤU TRÚC ENVELOPE (BLUEPRINT_WORLDPULSE_TENTACLE.md, Mục 1) ---
Mọi document mới ghi vào `human_comedy_tropes` giờ đi qua
`shared.envelope.build_envelope()` trước khi `insert_with_ttl()`.
impact_weight là hằng số thấp cố định (đúng bản chất "nguyên liệu giảm áp",
không phải placeholder che giấu việc chưa tính toán — Mục 1.2 blueprint).
extracted_facts = [context, punchline], mang tính mô tả tình huống, không
suy luận nguyên nhân.
"""
import logging
import os
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from config import comedy
from shared.mongo import (
    ensure_ttl_index,
    ensure_index,
    ensure_unique_index,
    insert_with_ttl,
    get_collection,
)
from shared.envelope import build_envelope, EventType

from module4_comedy.reddit_source import fetch_all_configured as fetch_reddit
from module4_comedy.voz_source import fetch_top_threads as fetch_voz
from module4_comedy.search_source import fetch_via_search
from module4_comedy.text_filter import validate_trope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Hằng số cố định — đây là nguyên liệu "giảm áp"/bẻ lái kịch bản, không
# phải áp lực mô phỏng, nên không cần công thức suy từ dữ liệu như 3 module
# kia (Mục 1.2 blueprint cho phép hằng số ở đây, đúng bản chất dữ liệu).
COMEDY_IMPACT_WEIGHT = 0.1


def _collect_candidates() -> list[dict]:
    candidates = []

    try:
        candidates.extend(fetch_reddit())
    except Exception as e:
        logger.warning(f"   ⚠️ Luồng Reddit lỗi toàn phần, bỏ qua: {e}")

    try:
        candidates.extend(fetch_voz())
    except Exception as e:
        logger.warning(f"   ⚠️ Luồng Voz lỗi toàn phần, bỏ qua: {e}")

    try:
        candidates.extend(fetch_via_search())
    except Exception as e:
        logger.warning(f"   ⚠️ Luồng Search Cascade lỗi toàn phần, bỏ qua: {e}")

    return candidates


def _emit_step_summary(status: str, saved: int, total_candidates: int) -> None:
    """Ghi bảng Markdown Layer-1 (per-run summary) vào GITHUB_STEP_SUMMARY
    (Mục 3.1 blueprint) — bảng màu Pass/Fail/Timeout nền đặc (Mục 3.2).
    impact_weight của Module 4 là hằng số cố định nên bảng chỉ hiển thị
    giá trị hằng số đó thay vì max/avg tính toán."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    badge = {
        "PASS": "🟢 **PASS**",
        "FAIL": "🔴 **FAIL**",
        "TIMEOUT": "🟠 **TIMEOUT**",
    }.get(status, f"⚪ **{status}**")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "## 😂 Module 4 — Hài hước & Đời sống",
        "",
        "| Trạng thái | Documents mới | Tổng ứng viên thu thập | impact_weight (hằng số) | Thời điểm chạy (UTC) |",
        "|---|---|---|---|---|",
        f"| {badge} | {saved} | {total_candidates} | {COMEDY_IMPACT_WEIGHT:.2f} | {now_iso} |",
        "",
    ]
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run():
    logger.info("=" * 60)
    logger.info("😂 MODULE 4 — Hài hước & Đời sống")
    logger.info("=" * 60)

    ensure_ttl_index(comedy.COLLECTION, comedy.TTL_HOURS)
    ensure_index(comedy.COLLECTION, "source_url")
    # BUG-1 fix: unique index thật ở tầng DB — chặn race condition TOCTOU
    # giữa find_one() (check) và insert_with_ttl() (act) khi 2 tiến trình
    # GitHub Actions chồng lấn nhau cùng ghi trùng source_url.
    ensure_unique_index(comedy.COLLECTION, "source_url")
    coll = get_collection(comedy.COLLECTION)

    candidates = _collect_candidates()
    if not candidates:
        logger.warning("   ⚠️ Không thu thập được tình huống nào phiên này.")
        _emit_step_summary("FAIL", 0, 0)
        return

    saved = 0
    for item in candidates:
        if saved >= comedy.MAX_TROPES_PER_RUN:
            break

        cleaned = validate_trope(item.get("context", ""), item.get("punchline", ""))
        if cleaned is None:
            continue

        source_url = item.get("source_url", "")
        if source_url:
            if coll.find_one({"source_url": source_url}):
                continue  # đã có, tránh trùng lặp trong TTL window
        else:
            # source_url rỗng (vd. Voz href extraction fail) — trước đây
            # (BUG-5) điều kiện `source_url and ...` là False nên bỏ qua
            # hoàn toàn dedup, cho phép insert trùng nhiều lần trong cửa sổ
            # TTL 30 ngày. Dùng context+punchline làm khoá dedup dự phòng.
            if coll.find_one({
                "source_url": "",
                "context": cleaned["context"],
                "punchline": cleaned["punchline"],
            }):
                continue

        extracted_facts = [cleaned["context"], cleaned["punchline"]]
        payload = {
            "context": cleaned["context"],
            "punchline": cleaned["punchline"],
            "source_url": source_url,
            "metadata": {
                "char_length": len(cleaned["context"]) + len(cleaned["punchline"]),
            },
        }
        doc = build_envelope(EventType.NARRATIVE_DEFLECTION, COMEDY_IMPACT_WEIGHT, extracted_facts, payload)
        try:
            insert_with_ttl(comedy.COLLECTION, doc, comedy.TTL_HOURS)
        except DuplicateKeyError:
            # BUG-1 fix: race condition thật xảy ra (2 process chồng lấn
            # cùng ghi 1 source_url) — unique index chặn ở tầng DB đúng
            # như thiết kế, bỏ qua bản ghi này thay vì crash cả run.
            logger.warning(
                f"   ⚠️ Bỏ qua bản ghi trùng (race condition chặn bởi unique "
                f"index): {source_url or cleaned['punchline'][:50]}"
            )
            continue
        saved += 1
        logger.info(f"   ✅ Đã lưu: {cleaned['punchline'][:70]}")

    logger.info(f"🏁 Module 4 hoàn tất: {saved} tình huống mới trong tổng {len(candidates)} thu thập được.")

    status = "PASS" if saved > 0 else "FAIL"
    _emit_step_summary(status, saved, len(candidates))


def get_random_trope() -> dict | None:
    """
    Tiện ích cho pipeline downstream (Chimera): lấy ngẫu nhiên 1 bản ghi
    từ `human_comedy_tropes` để đóng gói vào prompt khẩn cấp khi Circuit
    Breaker kích hoạt (ngưỡng lỗi kịch bản, xem biên bản CRON 4 mục 3).
    CHỈ đọc Mongo — không gọi LLM, không chạy guardrail platform ở đây.
    """
    coll = get_collection(comedy.COLLECTION)
    # $sample tránh TOCTOU race giữa count_documents() và find_one(skip=...):
    # nếu TTL background job xoá doc giữa 2 lệnh, skip value có thể vượt
    # quá count mới, khiến find_one trả về None dù collection không rỗng.
    docs = list(coll.aggregate([{"$sample": {"size": 1}}]))
    if not docs:
        return None
    doc = docs[0]
    return {
        "context": doc.get("context", ""),
        "punchline": doc.get("punchline", ""),
        "source_url": doc.get("source_url", ""),
    }


if __name__ == "__main__":
    try:
        run()
    except Exception:
        _emit_step_summary("FAIL", 0, 0)
        raise
