"""
shared/envelope.py
=====================================================================
Nguồn chân lý duy nhất (single source of truth) cho cấu trúc "envelope"
3 field bắt buộc mà World Simulator Engine (File 2) đọc để phân loại
áp lực/nhân vật/mâu thuẫn — KHÔNG cần biết cấu trúc nội bộ riêng của
từng module Tầng 0 (Ingestion).

Đây là điểm thực thi Mục 1.3 của BLUEPRINT_WORLDPULSE_TENTACLE.md: 4
module KHÔNG được tự tay ghép dict envelope 4 lần (nguyên nhân gốc gây
lệch schema trước tái cấu trúc) — mọi module PHẢI gọi build_envelope()
ở đây trước khi truyền document cho shared.mongo.insert_with_ttl().

Envelope KHÔNG xoá field đặc thù của từng module — nó bọc thêm lên trên
payload hiện có, giữ nguyên toàn bộ field cũ để phục vụ đọc lại/debug
riêng theo từng module (xem Mục 1.1 blueprint).
"""
import math
from enum import Enum


class EventType(str, Enum):
    """Enum cố định đúng 4 giá trị (Mục 1.2 + Chỉ thị #3 của blueprint).

    Module không được tự đặt tên khác hay viết tự do bằng string rời rạc.
    Kế thừa từ `str` để khi ghi Mongo, `EventType.X.value` hoặc chính
    `EventType.X` (qua build_envelope) đều nghiêm ngặt là 1 trong 4 chuỗi
    dưới đây.
    """

    ENVIRONMENTAL_PRESSURE = "environmental_pressure"  # Module 1 — thời tiết
    MACRO_DISRUPTION = "macro_disruption"              # Module 2 — sự kiện cực đoan
    CHARACTER_SEED = "character_seed"                  # Module 3 — nhân vật nổi bật
    NARRATIVE_DEFLECTION = "narrative_deflection"       # Module 4 — hài hước/bẻ lái


def clamp01(value) -> float:
    """Ép giá trị bất kỳ về khoảng đóng [0.0, 1.0].

    Mọi công thức impact_weight của 4 module PHẢI đi qua hàm này trước khi
    gọi build_envelope() (Chỉ thị #4 blueprint) — kể cả khi công thức nội
    bộ "trông có vẻ" đã nằm trong khoảng, để tránh lỗi làm tròn/None/NaN
    lọt ra ngoài khoảng chuẩn mà World Simulator kỳ vọng.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return max(0.0, min(1.0, v))


def build_envelope(event_type, impact_weight, extracted_facts: list, payload: dict) -> dict:
    """Bọc `payload` (dict đặc thù từng module, giữ nguyên mọi field cũ)
    với 3 field envelope bắt buộc: event_type, impact_weight, extracted_facts.

    Args:
        event_type: 1 trong 4 giá trị của EventType (enum hoặc string thô
            khớp đúng .value — cả 2 đều được chấp nhận để linh hoạt gọi từ
            run.py, nhưng luôn ghi ra Mongo dưới dạng string thuần).
        impact_weight: số thực bất kỳ — LUÔN bị ép qua clamp01() ở đây,
            caller không cần tự clamp trước (nhưng nên làm, xem Chỉ thị #4).
        extracted_facts: list[str] câu factual khách quan (số liệu, tên,
            thời điểm, địa điểm, hành động đã xảy ra) — KHÔNG chứa tính từ
            cảm xúc/suy luận/giọng kể chuyện (Mục 1.2 blueprint). Phải là
            list, không phải 1 chuỗi summary duy nhất.
        payload: dict đặc thù của module (field cũ của từng module giữ
            nguyên 100%, envelope chỉ thêm 3 key mới đè lên).

    Returns:
        dict sẵn sàng truyền thẳng cho `shared.mongo.insert_with_ttl()`.

    Raises:
        TypeError: nếu extracted_facts không phải list (bug thường gặp
            nhất: truyền nhầm 1 chuỗi summary chưa tách câu).
    """
    if isinstance(event_type, EventType):
        event_type_value = event_type.value
    else:
        event_type_value = str(event_type)
        valid_values = {e.value for e in EventType}
        if event_type_value not in valid_values:
            raise ValueError(
                f"event_type={event_type_value!r} không thuộc 4 giá trị enum hợp lệ: "
                f"{sorted(valid_values)}. Xem shared/envelope.py::EventType."
            )

    if not isinstance(extracted_facts, list):
        raise TypeError(
            f"extracted_facts phải là list[str], nhận được {type(extracted_facts).__name__}. "
            "Tách chuỗi summary thành list câu trước khi gọi build_envelope() "
            "(vd. dùng key_facts của shared.summarizer.extractive_summary)."
        )

    return {
        **payload,
        "event_type": event_type_value,
        "impact_weight": clamp01(impact_weight),
        "extracted_facts": [str(f).strip() for f in extracted_facts if f and str(f).strip()],
    }
