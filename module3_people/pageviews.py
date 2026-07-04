"""
Module 3 — Bước 1 (Định danh): Wikimedia Pageviews API.
API thuần, không cào web. Lấy top bài viết hôm qua (UTC) cho từng project,
loại trang kỹ thuật, trả về danh sách title thô để đưa qua Wikidata lọc
tiếp "chỉ giữ Con người" ở bước sau.
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from config import people

logger = logging.getLogger(__name__)


def _yesterday_utc() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=1)


def fetch_top_titles(project: str, top_n: int) -> list[str]:
    """
    project: "en.wikipedia" | "vi.wikipedia" (xem config.people.PROJECTS)
    Dùng ngày hôm qua UTC vì Pageviews API cần ngày đã đóng dữ liệu đầy đủ.
    """
    day = _yesterday_utc()
    url = people.WIKIMEDIA_PAGEVIEWS_URL.format(
        project=project, year=day.strftime("%Y"), month=day.strftime("%m"), day=day.strftime("%d")
    )
    headers = {"User-Agent": "worldpulse-tentacle/1.0 (data collection bot)"}

    try:
        resp = requests.get(url, headers=headers, timeout=people.HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"   ⚠️ Pageviews API lỗi cho {project}: {e}")
        return []

    articles = data.get("items", [{}])[0].get("articles", [])
    titles = []
    for item in articles:
        title = item.get("article", "")
        if title in people.EXCLUDE_TITLES or title.startswith("Special:"):
            continue
        titles.append(title)
        if len(titles) >= top_n * 3:  # lấy dư ra vì bước lọc Wikidata sẽ loại bớt
            break

    return titles
