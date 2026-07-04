"""
Module 3 — Bước 1 (Định danh), phần 2: lọc Wikidata P31=Q5.
Wikipedia title -> Wikidata QID (qua pageprops) -> kiểm tra instance-of
Human (Q5). Loại bỏ sự kiện/tổ chức/địa danh trùng tên lọt vào top pageviews.
API thuần, không cào web.
"""
import logging

import requests

from config import people

logger = logging.getLogger(__name__)


def _get_wikidata_qid(title: str, lang: str) -> str | None:
    url = people.WIKIPEDIA_API_URL.format(lang=lang)
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "titles": title,
    }
    try:
        resp = requests.get(url, params=params, timeout=people.HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                return qid
    except Exception as e:
        logger.warning(f"   ⚠️ Không lấy được QID cho '{title}': {e}")
    return None


def is_human(qid: str) -> bool:
    """True nếu Wikidata entity có claim P31 (instance of) = Q5 (human)."""
    params = {
        "action": "wbgetclaims",
        "format": "json",
        "entity": qid,
        "property": "P31",
    }
    try:
        resp = requests.get(people.WIKIDATA_API_URL, params=params, timeout=people.HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        claims = resp.json().get("claims", {}).get("P31", [])
        for claim in claims:
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if value.get("id") == "Q5":
                return True
    except Exception as e:
        logger.warning(f"   ⚠️ Không kiểm tra được P31 cho {qid}: {e}")
    return False


def filter_to_humans(titles: list[str], lang: str, top_n: int) -> list[str]:
    """Trả về tối đa top_n title đã xác nhận là Con người, giữ thứ tự pageviews."""
    humans = []
    for title in titles:
        if len(humans) >= top_n:
            break
        qid = _get_wikidata_qid(title, lang)
        if qid and is_human(qid):
            humans.append(title.replace("_", " "))
    return humans
