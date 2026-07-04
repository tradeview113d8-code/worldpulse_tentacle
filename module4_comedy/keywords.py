"""
Xoay vòng NHÓM TỪ KHÓA MỒI cho Luồng 2 (Search Cascade) của Module 4.
Cùng cơ chế round-robin với module2_events/topics.py, state riêng để
không đụng chạm vòng xoay của Module 2.
"""
import json
import logging
import os

from config import comedy

logger = logging.getLogger(__name__)


def _load_state() -> dict:
    path = comedy.KEYWORD_ROTATION_STATE_FILE
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_index": -1}


def _save_state(state: dict):
    path = comedy.KEYWORD_ROTATION_STATE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_next_keyword_group() -> tuple[str, list[str]]:
    """Trả về (tên_nhóm, [seed_keywords]) của nhóm kế tiếp trong vòng xoay.

    CHỈ "peek" — không lưu state ở đây. Nếu fetch_via_search() fail (crash,
    timeout, network) mà state đã bị advance trước đó (bug cũ), mỗi lần
    fail sẽ tiêu tốn 1 slot trong vòng xoay 4 nhóm mà không thu được gì.
    Gọi `commit()` sau khi xác nhận có kết quả để advance vòng xoay.
    """
    group_names = list(comedy.SEED_KEYWORD_GROUPS.keys())
    state = _load_state()

    next_index = (state.get("last_index", -1) + 1) % len(group_names)
    group_name = group_names[next_index]

    logger.info(f"   🔄 Nhóm từ khóa mồi phiên này: '{group_name}' ({next_index + 1}/{len(group_names)})")
    return group_name, comedy.SEED_KEYWORD_GROUPS[group_name]


def commit(group_name: str):
    """Advance vòng xoay sang `group_name` đã dùng. Chỉ gọi sau khi
    `fetch_via_search()` trả về ít nhất 1 kết quả, để tránh waste slot khi
    pipeline fail (BUG-3)."""
    group_names = list(comedy.SEED_KEYWORD_GROUPS.keys())
    if group_name not in group_names:
        logger.warning(f"   ⚠️ commit() nhận group_name không hợp lệ: {group_name!r}")
        return

    state = _load_state()
    state["last_index"] = group_names.index(group_name)
    _save_state(state)
