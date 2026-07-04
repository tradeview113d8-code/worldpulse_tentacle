"""
Mongo helper dùng chung cho cả 3 module.
=========================================
Nguyên tắc vận hành DB (theo biên bản tái cấu trúc):
- KHÔNG lưu trữ vĩnh viễn bất kỳ dữ liệu nào trong repo này.
- Mọi collection đều có TTL index riêng để cụm M0 (512MB) luôn nhẹ.
- Mỗi module tự gọi ensure_ttl_index() một lần khi khởi động — idempotent,
  MongoDB bỏ qua nếu index đã tồn tại với cùng cấu hình.
"""
import logging
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import shared

logger = logging.getLogger(__name__)

_client = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        if not shared.MONGODB_URI:
            raise RuntimeError(
                "MONGODB_URI chưa được thiết lập (biến môi trường / GitHub Secret)."
            )
        _client = MongoClient(shared.MONGODB_URI)
    return _client


def get_collection(name: str):
    db = get_client()[shared.MONGODB_DB_NAME]
    return db[name]


def ensure_ttl_index(collection_name: str, ttl_hours: int, field: str = "expires_at"):
    """
    Tạo TTL index trên `field` (mặc định expires_at) nếu chưa có.
    Mỗi document tự tính expires_at khi insert — index chỉ cần expireAfterSeconds=0
    để Mongo tự xóa đúng thời điểm document đã quá hạn.
    """
    try:
        coll = get_collection(collection_name)
        coll.create_index(field, expireAfterSeconds=0, name=f"ttl_{field}")
        logger.info(f"   ✅ TTL index sẵn sàng trên '{collection_name}.{field}' (TTL={ttl_hours}h)")
    except PyMongoError as e:
        logger.error(f"   ⚠️ Không thể tạo TTL index cho '{collection_name}': {e}")


def ensure_index(collection_name: str, field: str):
    """Tạo index thường (không TTL) trên `field` nếu chưa có — dùng cho các
    truy vấn dedup lặp lại nhiều lần mỗi run (vd. `find_one({"source_url": ...})`
    ở Module 4), tránh full collection scan khi collection lớn dần trong
    cửa sổ TTL 30 ngày."""
    try:
        coll = get_collection(collection_name)
        coll.create_index(field, name=f"idx_{field}")
        logger.info(f"   ✅ Index sẵn sàng trên '{collection_name}.{field}'")
    except PyMongoError as e:
        logger.error(f"   ⚠️ Không thể tạo index cho '{collection_name}.{field}': {e}")


def ensure_unique_index(collection_name: str, field: str):
    """Tạo UNIQUE index thật trên `field` — chặn race condition TOCTOU ở
    tầng DB (2 tiến trình GitHub Actions chồng lấn cùng insert 1 giá trị
    trùng `field` thì tiến trình thứ 2 sẽ nhận DuplicateKeyError thay vì
    ghi trùng lặp thành công).

    Dùng `partialFilterExpression` để loại trừ document có `field` rỗng
    (chuỗi "") khỏi ràng buộc unique — trường hợp source_url rỗng (vd.
    lỗi extract href) vẫn được insert bình thường, dedup những bản ghi đó
    dựa vào các trường khác ở tầng gọi hàm, không phải ở đây.

    Nếu collection hiện tại đã có sẵn document trùng `field` (không rỗng)
    từ trước khi index này tồn tại, MongoDB sẽ từ chối tạo index (lỗi
    E11000 ngay lúc create_index) — log lỗi và bỏ qua, không raise, để
    không chặn toàn bộ run vì việc này (cần dọn dữ liệu trùng cũ trước).
    """
    try:
        coll = get_collection(collection_name)
        coll.create_index(
            field,
            unique=True,
            name=f"uniq_{field}",
            partialFilterExpression={field: {"$gt": ""}},
        )
        logger.info(f"   ✅ UNIQUE index sẵn sàng trên '{collection_name}.{field}'")
    except PyMongoError as e:
        logger.error(
            f"   ⚠️ Không thể tạo UNIQUE index cho '{collection_name}.{field}' "
            f"(có thể do dữ liệu trùng cũ cần dọn trước): {e}"
        )


def utc_now():
    return datetime.now(timezone.utc)


def insert_with_ttl(collection_name: str, document: dict, ttl_hours: int):
    """Chèn 1 document, tự gắn created_at + expires_at theo ttl_hours."""
    from datetime import timedelta

    now = utc_now()
    document = {
        **document,
        "created_at": now,
        "expires_at": now + timedelta(hours=ttl_hours),
    }
    coll = get_collection(collection_name)
    result = coll.insert_one(document)
    return result.inserted_id
