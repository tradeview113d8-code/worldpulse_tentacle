"""
Bộ lọc văn bản sơ cấp cho Module 4.
====================================
Đây CHỈ là lớp lọc kỹ thuật cấp thấp (regex, không LLM) để loại rác/link
quảng cáo/từ lóng thô tục quá mức và ép giới hạn độ dài trước khi ghi Mongo.
Bộ lọc `platform_and_legal_guardrails` đầy đủ (luật lách kiểm duyệt theo
tiêu chuẩn cộng đồng) nằm ở tầng downstream (Phase 2 của Chimera) — repo
này không có quyền truy cập cấu hình/LLM của tầng đó nên không thể tái tạo
lại toàn bộ logic ở đây. Mục tiêu tại đây chỉ là "đủ sạch để không rác".
"""
import re

from config import comedy

# Vài mẫu link/số điện thoại/ký tự lạ phổ biến trong rác quảng cáo cào được.
URL_RE = re.compile(r"https?://\S+|www\.\S+")
PHONE_RE = re.compile(r"\b0\d{9,10}\b")
EXCESS_WHITESPACE_RE = re.compile(r"\s+")
# Ký tự lạ/emoji lặp nhiều lần (rác trang trí, không mang nội dung)
WEIRD_REPEAT_RE = re.compile(r"([^\w\sÀ-ỹ.,!?()\"'-])\1{2,}")

# Danh sách rút gọn các từ lóng thô tục PHỔ BIẾN cần che (không toàn diện —
# chỉ đủ để loại các trường hợp quá thô, không phải bộ lọc kiểm duyệt đầy
# đủ). Dùng \b để tránh che nhầm từ ghép hợp lệ.
_MILD_PROFANITY = ["đm", "dm", "vcl", "vkl", "đcm", "dcm", "cmm", "clgt"]
PROFANITY_RE = re.compile(
    r"\b(" + "|".join(_MILD_PROFANITY) + r")\b", flags=re.IGNORECASE
)


def _looks_like_spam(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in comedy.BANNED_SUBSTRINGS)


def clean_text(raw: str) -> str:
    """Chuẩn hoá whitespace, bỏ URL/SĐT, che nhẹ từ lóng thô tục quá mức."""
    if not raw:
        return ""
    text = URL_RE.sub("", raw)
    text = PHONE_RE.sub("", text)
    text = WEIRD_REPEAT_RE.sub(r"\1", text)
    text = PROFANITY_RE.sub("***", text)
    text = EXCESS_WHITESPACE_RE.sub(" ", text).strip()
    return text


def validate_trope(context: str, punchline: str) -> dict | None:
    """
    Làm sạch + kiểm định 1 cặp (context, punchline).
    Trả về dict {"context", "punchline"} đã làm sạch, hoặc None nếu bị loại
    (quá ngắn, toàn rác quảng cáo, hoặc rỗng sau khi lọc).
    """
    context = clean_text(context)[: comedy.MAX_TEXT_CHARS]
    punchline = clean_text(punchline)[: comedy.MAX_TEXT_CHARS]

    if len(context) < comedy.MIN_CONTEXT_CHARS or not punchline:
        return None

    if _looks_like_spam(context) or _looks_like_spam(punchline):
        return None

    return {"context": context, "punchline": punchline}
