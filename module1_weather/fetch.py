"""
Lọc "bài tổng quan/giải thích cũ" theo published_at — đặc thù Module 2
(dùng `events.MAX_ARTICLE_AGE_HOURS` làm ngưỡng mặc định).

`fetch_article()` (tải HTML + bóc published_at) đã chuyển sang
`shared/fetch.py` vì đó là logic generic, không có gì đặc thù Module 2 —
xem docstring ở đó. Re-export tại đây để không phá bất kỳ import cũ nào
(`from module2_events.fetch import fetch_article`) còn sót lại.
"""
from datetime import datetime, timezone

from config import events
from shared.fetch import fetch_article  # noqa: F401  (re-export, giữ tương thích ngược)

__all__ = ["fetch_article", "is_fresh_enough"]


def is_fresh_enough(published_at, max_age_hours: int = None) -> bool:
    """
    True nếu bài viết đủ mới HOẶC không xác định được ngày (cho qua, tránh
    loại nhầm bài tốt chỉ vì trang không có metadata chuẩn — an toàn hơn là
    chặn cứng khi không chắc chắn).
    """
    max_age_hours = max_age_hours or events.MAX_ARTICLE_AGE_HOURS
    if published_at is None:
        return True
    age = datetime.now(timezone.utc) - published_at
    return age.total_seconds() <= max_age_hours * 3600
