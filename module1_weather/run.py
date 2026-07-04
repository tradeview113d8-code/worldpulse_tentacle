"""
Module 1: Xúc tu Thời Tiết Việt Nam (cửa sổ 24h tới)
======================================================
Quét toàn bộ danh sách tọa độ tĩnh (không xoay vòng), gọi Open-Meteo trực
tiếp, kèm bản tin cảnh báo bão NCHMF/JTWC best-effort. Ghi 1 document/thành
phố + 1 document bản tin bão (nếu có) vào Mongo, TTL 48h.

Chạy 2 lần/ngày (12h/lần).

--- TÁI CẤU TRÚC ENVELOPE (BLUEPRINT_WORLDPULSE_TENTACLE.md, Mục 1) ---
Mọi document ghi vào `weather_pulses` giờ đi qua `shared.envelope.build_envelope()`
trước khi `insert_with_ttl()`, thêm 3 field bắt buộc: event_type, impact_weight,
extracted_facts. Document `storm_bulletin` KHÔNG còn field `type` tuỳ ý cũ —
đã hợp nhất về cùng shape envelope như mọi document thời tiết khác trong
cùng collection (Chỉ thị #6 blueprint).
"""
import logging
import os
from datetime import datetime, timezone

from config import weather
from shared.mongo import ensure_ttl_index, insert_with_ttl
from shared.envelope import build_envelope, clamp01, EventType
from shared.summarizer import extractive_summary

from module1_weather.fetch import fetch_open_meteo, summarize_next_24h, fetch_storm_bulletins

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# === Ngưỡng suy ra impact_weight từ chỉ số khí tượng thô ===
# Ngưỡng xấp xỉ theo thang cảnh báo gió giật/bão phổ biến (VN + quốc tế):
# ~120 km/h giật tương ứng vùng bão mạnh (từ cấp 12 trở lên) -> coi là "max"
# cho thang chuẩn hoá 0-1 của riêng module này (không phải ngưỡng khoa học
# tuyệt đối, chỉ dùng để so sánh tương đối giữa các thành phố/lần chạy).
WIND_GUST_SEVERE_KMH = 120.0
RAIN_PROB_MAX_PCT = 100.0
WIND_WEIGHT_IN_SCORE = 0.6
RAIN_WEIGHT_IN_SCORE = 0.4

# Bản tin bão luôn có impact_weight cao cố định vì bản chất là cảnh báo
# khẩn — không suy ra từ số liệu như các document thời tiết theo thành phố
# (đúng như Mục 1.2 blueprint mô tả riêng cho storm_bulletin).
STORM_BULLETIN_IMPACT_WEIGHT = 0.9


def _weather_impact_weight(indicators: dict) -> float:
    """Suy impact_weight từ windgusts_max_kmh + rain_probability_max_pct đã
    có sẵn trong `indicators` — không phải số cố định đoán mò (Mục 1.2)."""
    gust = indicators.get("windgusts_max_kmh")
    rain = indicators.get("rain_probability_max_pct")

    wind_score = clamp01((gust or 0.0) / WIND_GUST_SEVERE_KMH)
    rain_score = clamp01((rain or 0.0) / RAIN_PROB_MAX_PCT)

    return clamp01(WIND_WEIGHT_IN_SCORE * wind_score + RAIN_WEIGHT_IN_SCORE * rain_score)


def _weather_extracted_facts(location_name: str, indicators: dict) -> list[str]:
    """Chuyển các chỉ số thô trong `indicators` thành câu factual khách
    quan (Mục 1.2: 'hiện tại doc chỉ lưu số thô, chưa có câu fact nào')."""
    facts = []

    if indicators.get("windgusts_max_kmh") is not None:
        facts.append(
            f"Gió giật tối đa dự báo {indicators['windgusts_max_kmh']} km/h "
            f"trong 24h tới tại {location_name}."
        )
    if indicators.get("windspeed_max_kmh") is not None:
        facts.append(
            f"Tốc độ gió tối đa dự báo {indicators['windspeed_max_kmh']} km/h "
            f"trong 24h tới tại {location_name}."
        )
    if indicators.get("rain_probability_max_pct") is not None:
        facts.append(
            f"Xác suất mưa tối đa dự báo {indicators['rain_probability_max_pct']}% "
            f"trong 24h tới tại {location_name}."
        )
    if indicators.get("temp_max_c") is not None and indicators.get("temp_min_c") is not None:
        facts.append(
            f"Nhiệt độ dự báo dao động {indicators['temp_min_c']}–{indicators['temp_max_c']}°C "
            f"tại {location_name} trong 24h tới."
        )
    if indicators.get("cloudcover_avg_pct") is not None:
        facts.append(
            f"Độ che phủ mây trung bình dự báo {indicators['cloudcover_avg_pct']}% "
            f"tại {location_name} trong 24h tới."
        )

    return facts


def _storm_bulletin_extracted_facts(bulletins: list[dict]) -> list[str]:
    """Rút câu factual từ raw_excerpt của các bản tin bão bằng
    extractive_summary (thuần Python, không LLM) — fallback về excerpt cắt
    ngắn nếu không tách được câu nào (vd. text quá ngắn/không đúng cấu trúc
    câu chuẩn)."""
    combined_text = " ".join(b.get("raw_excerpt", "") for b in bulletins if b.get("raw_excerpt"))
    if not combined_text:
        return []

    summary = extractive_summary(combined_text, max_sentences=5)
    facts = summary["key_facts"]
    if facts:
        return facts

    return [
        f"{b['source']}: {b['raw_excerpt'][:200]}"
        for b in bulletins
        if b.get("raw_excerpt")
    ]


def _emit_step_summary(status: str, saved: int, total: int, impact_weights: list[float]) -> None:
    """Ghi bảng Markdown Layer-1 (per-run summary) vào GITHUB_STEP_SUMMARY
    (Mục 3.1 blueprint). Bỏ qua im lặng nếu biến môi trường không tồn tại
    (vd. chạy local/dry-run ngoài GitHub Actions).

    Bảng màu Pass/Fail/Timeout dùng nền màu đặc, không hiệu ứng trong suốt
    (Mục 3.2 blueprint)."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    badge = {
        "PASS": "🟢 **PASS**",
        "FAIL": "🔴 **FAIL**",
        "TIMEOUT": "🟠 **TIMEOUT**",
    }.get(status, f"⚪ **{status}**")

    max_iw = max(impact_weights) if impact_weights else 0.0
    avg_iw = (sum(impact_weights) / len(impact_weights)) if impact_weights else 0.0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "## 🌦️ Module 1 — Thời tiết Việt Nam",
        "",
        "| Trạng thái | Documents mới | impact_weight cao nhất | impact_weight trung bình | Thời điểm chạy (UTC) |",
        "|---|---|---|---|---|",
        f"| {badge} | {saved}/{total} | {max_iw:.2f} | {avg_iw:.2f} | {now_iso} |",
        "",
    ]
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run():
    logger.info("=" * 60)
    logger.info("🌦️  MODULE 1 — Thời tiết Việt Nam")
    logger.info("=" * 60)

    ensure_ttl_index(weather.COLLECTION, weather.TTL_HOURS)

    saved = 0
    impact_weights: list[float] = []

    for location in weather.LOCATIONS:
        data = fetch_open_meteo(location["lat"], location["lon"])
        if data is None:
            continue

        indicators = summarize_next_24h(data)
        impact_weight = _weather_impact_weight(indicators)
        extracted_facts = _weather_extracted_facts(location["name"], indicators)

        payload = {
            "location_name": location["name"],
            "lat": location["lat"],
            "lon": location["lon"],
            **indicators,
        }
        doc = build_envelope(EventType.ENVIRONMENTAL_PRESSURE, impact_weight, extracted_facts, payload)
        insert_with_ttl(weather.COLLECTION, doc, weather.TTL_HOURS)
        saved += 1
        impact_weights.append(impact_weight)
        logger.info(
            f"   ✅ {location['name']}: mưa {indicators['rain_probability_max_pct']}%, "
            f"gió giật {indicators['windgusts_max_kmh']}km/h, impact_weight={impact_weight:.2f}"
        )

    bulletins = fetch_storm_bulletins()
    if bulletins:
        extracted_facts = _storm_bulletin_extracted_facts(bulletins)
        payload = {
            "location_name": "Toàn quốc / Biển Đông (bản tin bão)",
            "bulletins": bulletins,
        }
        doc = build_envelope(
            EventType.ENVIRONMENTAL_PRESSURE,
            STORM_BULLETIN_IMPACT_WEIGHT,
            extracted_facts,
            payload,
        )
        insert_with_ttl(weather.COLLECTION, doc, weather.TTL_HOURS)
        impact_weights.append(STORM_BULLETIN_IMPACT_WEIGHT)
        logger.info(f"   ✅ Đã lưu {len(bulletins)} bản tin bão (impact_weight={STORM_BULLETIN_IMPACT_WEIGHT:.2f})")

    total = len(weather.LOCATIONS) + (1 if bulletins else 0)
    logger.info(f"🏁 Module 1 hoàn tất: {saved}/{len(weather.LOCATIONS)} địa điểm.")

    status = "PASS" if saved > 0 else "FAIL"
    _emit_step_summary(status, saved + (1 if bulletins else 0), total, impact_weights)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        _emit_step_summary("FAIL", 0, 0, [])
        raise
