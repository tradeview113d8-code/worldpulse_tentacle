"""
Phân loại nguồn cho Module 2 — logic ĐẢO NGƯỢC hoàn toàn so với
rulesworldsimulator/t1_classify.py: ở đó blog/fandom worldbuilding được xếp
priority 1 (nguồn chất liệu sáng tạo), ở đây hãng tin sự thật (Reuters, AP,
AFP, BBC...) lên priority 1 vì mục tiêu là "sự thật khách quan" chứ không
phải chất liệu hư cấu.
"""
from config import events


def get_priority(domain: str) -> int:
    """Số càng nhỏ càng ưu tiên cao. Domain lạ -> DEFAULT_SOURCE_PRIORITY."""
    domain = domain.lower().replace("www.", "")
    for known_domain, priority in events.SOURCE_PRIORITY.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return priority
    return events.DEFAULT_SOURCE_PRIORITY


def sort_by_priority(links: list[dict]) -> list[dict]:
    """Sắp xếp links theo priority nguồn tăng dần (ưu tiên cao trước)."""
    return sorted(links, key=lambda link: get_priority(link.get("domain", "")))
