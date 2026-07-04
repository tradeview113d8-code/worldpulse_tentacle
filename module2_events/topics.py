"""
Xoay vòng NHÓM CHỦ ĐỀ (không phải từng từ khóa lẻ) cho Module 2.
Mỗi lần chạy (2 lần/ngày) chọn đúng 1 nhóm theo round-robin, dùng tất cả
query trong nhóm đó. Lần chạy sau tự động sang nhóm kế tiếp.

Cùng pattern peek/commit với `module4_comedy/keywords.py` (BUG-3 fix):
`get_next_topic_group()` chỉ "peek" — không ghi state. `commit_topic_group()`
phải được gọi tường minh từ `run.py` sau khi xác nhận có ít nhất 1 bài
viết được lưu, để tránh tiêu tốn slot vòng xoay khi pipeline fail
(crash / timeout / toàn bộ cascade search rỗng).
"""
import json
import logging
import os

from config import events

logger = logging.getLogger(__name__)


def _load_state() -> dict:
    path = events.TOPIC_ROTATION_STATE_FILE
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_index": -1}


def _save_state(state: dict) -> None:
    path = events.TOPIC_ROTATION_STATE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_next_topic_group() -> tuple[str, list[str]]:
    """Trả về (tên_nhóm, [queries]) của nhóm kế tiếp trong vòng xoay.

    CHỈ "peek" — không lưu state ở đây. Gọi `commit_topic_group(name)` sau
    khi xác nhận có kết quả để advance vòng xoay (BUG-3 pattern).
    """
    group_names = list(events.TOPIC_GROUPS.keys())
    state = _load_state()

    next_index = (state.get("last_index", -1) + 1) % len(group_names)
    group_name = group_names[next_index]

    logger.info(f"   🔄 Nhóm chủ đề phiên này: '{group_name}' ({next_index + 1}/{len(group_names)})")
    return group_name, events.TOPIC_GROUPS[group_name]


def commit_topic_group(group_name: str) -> None:
    """Advance vòng xoay sang `group_name` đã dùng. Chỉ gọi sau khi lưu
    được ít nhất 1 bài viết, để tránh waste slot khi pipeline fail (BUG-3).
    """
    group_names = list(events.TOPIC_GROUPS.keys())
    if group_name not in group_names:
        logger.warning(f"   ⚠️ commit_topic_group() nhận group_name không hợp lệ: {group_name!r}")
        return

    state = _load_state()
    state["last_index"] = group_names.index(group_name)
    _save_state(state)
