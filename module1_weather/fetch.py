"""
Module 1: Xúc tu Thời Tiết Việt Nam — luồng dữ liệu SẠCH.
Không Playwright, không stealth, không anti-ban: gọi thẳng API công khai.
"""
import logging

import requests

from config import weather

logger = logging.getLogger(__name__)

# Nhiều site .gov/.mil (NCHMF, JTWC) chặn request không có User-Agent trình
# duyệt thật (mặc định requests gửi "python-requests/x.x" -> bị WAF trả 403).
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_open_meteo(lat: float, lon: float) -> dict | None:
    """Gọi Open-Meteo cho 1 tọa độ, trả về dữ liệu giờ trong FORECAST_DAYS ngày tới."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(weather.OPEN_METEO_HOURLY_VARS),
        "forecast_days": weather.FORECAST_DAYS,
        "timezone": "Asia/Bangkok",
    }
    try:
        resp = requests.get(weather.OPEN_METEO_URL, params=params, timeout=weather.HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"   ⚠️ Open-Meteo lỗi cho ({lat}, {lon}): {e}")
        return None


def summarize_next_24h(open_meteo_data: dict) -> dict:
    """
    Rút gọn dữ liệu hourly thô thành các chỉ số cực đoan cho 24h tới:
    nhiệt độ max/min, xác suất mưa max, gió giật max, mây trung bình.
    """
    hourly = open_meteo_data.get("hourly", {})
    n = 24  # 24 giờ đầu tiên = cửa sổ 24h tới

    def _slice(key):
        values = hourly.get(key, [])[:n]
        return [v for v in values if v is not None]

    temps = _slice("temperature_2m")
    rain_prob = _slice("precipitation_probability")
    wind = _slice("windspeed_10m")
    gusts = _slice("windgusts_10m")
    cloud = _slice("cloudcover")

    return {
        "temp_max_c": max(temps) if temps else None,
        "temp_min_c": min(temps) if temps else None,
        "rain_probability_max_pct": max(rain_prob) if rain_prob else None,
        "windspeed_max_kmh": max(wind) if wind else None,
        "windgusts_max_kmh": max(gusts) if gusts else None,
        "cloudcover_avg_pct": round(sum(cloud) / len(cloud), 1) if cloud else None,
    }


def fetch_storm_bulletins() -> list[dict]:
    """
    Best-effort: lấy bản tin cảnh báo bão từ NCHMF + JTWC. Đây là phần dễ vỡ
    nhất (selector/URL phụ thuộc giao diện trang, có thể đổi theo thời gian) —
    thất bại ở đây KHÔNG được làm crash toàn bộ Module 1, chỉ trả về [].

    Mỗi nguồn có 1 danh sách URL ứng viên: trang cũ NCHMF (nchmf.gov.vn/Kttv/...)
    đã đổi cấu trúc sang '/kttvsite/...' (404 nếu dùng URL cũ); JTWC
    (metoc.navy.mil) đã đổi domain sang metoc.dc3n.navy.mil, và các site
    .gov/.mil thường trả 403 nếu thiếu User-Agent trình duyệt thật -> luôn
    gửi kèm _BROWSER_HEADERS. Thử lần lượt từng candidate, dùng candidate
    đầu tiên trả về 200.
    """
    bulletins = []
    sources = [
        (
            "NCHMF",
            [
                weather.NCHMF_WARNING_URL,
                "https://nchmf.gov.vn/kttvsite/vi-VN/1/bao-ap-thap-nhiet-doi-2049-15.html",
                "https://kttv.gov.vn/kttvsite/vi-VN/1/bao-ap-thap-nhiet-doi-2049-15.html",
            ],
        ),
        (
            "JTWC",
            [
                weather.JTWC_WARNING_URL,
                "https://www.metoc.dc3n.navy.mil/jtwc/jtwc.html",
                "https://www.metoc.navy.mil/jtwc/jtwc.html",
            ],
        ),
    ]

    from bs4 import BeautifulSoup

    for source_name, candidate_urls in sources:
        last_error = None
        for url in dict.fromkeys(candidate_urls):  # bỏ trùng, giữ thứ tự
            if not url:
                continue
            try:
                resp = requests.get(
                    url,
                    headers=_BROWSER_HEADERS,
                    timeout=weather.HTTP_TIMEOUT_SECONDS,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                # Lấy đoạn text đầu trang làm tóm tắt thô — cần tinh chỉnh
                # selector thật khi có quyền truy cập trực tiếp để kiểm tra
                # DOM thực tế.
                text = " ".join(soup.get_text(separator=" ").split())[:1500]
                bulletins.append({"source": source_name, "url": url, "raw_excerpt": text})
                last_error = None
                break
            except Exception as e:
                last_error = e
                logger.warning(f"   ⚠️ {source_name} lỗi với {url}: {e}")
        if last_error is not None:
            logger.warning(f"   ⚠️ Không lấy được bản tin {source_name} (đã thử {len(candidate_urls)} URL)")

    return bulletins
    
