"""
Config cho WorldPulse-Tentacle
================================
Khác với rulesworldsimulator cũ (1 Settings phẳng dùng chung cho 1 pipeline
tuần tự), repo này chạy 3 module ĐỘC LẬP trên 3 lịch cron riêng. Mỗi module
có namespace hằng số riêng để tránh việc sửa tham số của module này ảnh
hưởng nhầm sang module khác.

Tần suất: cả 3 module đều chạy 2 lần/ngày (12h/lần), lệch phút khởi chạy
nhau trong file workflow .yml để tránh ghi Mongo cùng lúc.
"""
import os


class SharedSettings:
    """Hằng số dùng chung cho toàn bộ 3 module."""

    # === MONGODB ===
    MONGODB_URI = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "worldpulse")

    # === FILES DÙNG CHUNG (tái sử dụng nguyên trạng từ rulesworldsimulator) ===
    ENGINES_FILE = "search_engines.json"
    BLACKBOOK_FILE = "blackbook.json"

    # === ANTI-BAN DELAYS (chỉ dùng cho Module 2 và bước 2 của Module 3) ===
    MIN_REQUEST_DELAY = 8.0
    MAX_REQUEST_DELAY = 20.0

    # === DATA DIRS (state file cục bộ, KHÔNG phải kho lưu vĩnh viễn) ===
    DATA_DIR = "data"


class WeatherSettings:
    """Module 1: Thời tiết Việt Nam (cửa sổ 24h tới)."""

    COLLECTION = "weather_pulses"
    TTL_HOURS = 48

    # Tọa độ tĩnh: 3 thành phố lớn + các vùng ven biển rủi ro bão cao.
    # Không dùng từ khóa xoay vòng — quét toàn bộ danh sách mỗi lần chạy.
    LOCATIONS = [
        {"name": "Hà Nội", "lat": 21.0285, "lon": 105.8542},
        {"name": "TP.HCM", "lat": 10.7769, "lon": 106.7009},
        {"name": "Đà Nẵng", "lat": 16.0544, "lon": 108.2022},
        {"name": "Hải Phòng", "lat": 20.8449, "lon": 106.6881},
        {"name": "Nha Trang", "lat": 12.2388, "lon": 109.1967},
        {"name": "Quy Nhơn", "lat": 13.7830, "lon": 109.2170},
        {"name": "Vinh", "lat": 18.6796, "lon": 105.6813},
        {"name": "Cà Mau", "lat": 9.1769, "lon": 105.1524},
        {"name": "Quảng Ninh (Hạ Long)", "lat": 20.9500, "lon": 107.0833},
        {"name": "Phú Quốc", "lat": 10.2270, "lon": 103.9670},
    ]

    OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_HOURLY_VARS = [
        "temperature_2m",
        "precipitation_probability",
        "windspeed_10m",
        "windgusts_10m",
        "cloudcover",
    ]
    FORECAST_DAYS = 2  # đủ phủ cửa sổ 24h tới + biên an toàn

    # Bản tin cảnh báo bão — HTTP thuần, không Playwright/stealth (luồng sạch).
    # Selector có thể cần cập nhật nếu 2 trang này đổi giao diện.
    NCHMF_WARNING_URL = "https://nchmf.gov.vn/Kttv/vi-VN/1/tin-bao-va-atnd.html"
    JTWC_WARNING_URL = "https://www.metoc.navy.mil/jtwc/jtwc.html"
    HTTP_TIMEOUT_SECONDS = 15


class EventsSettings:
    """Module 2: Sự kiện cực đoan toàn cầu (cửa sổ 48h qua)."""

    COLLECTION = "extreme_events"
    TTL_HOURS = 48

    KEYWORD_STATE_DIR = "data/module2_state"
    LINKS_PER_SEARCH = 20
    MAX_ARTICLE_AGE_HOURS = 48  # loại cứng bài "tổng quan/giải thích" cũ hơn

    # Ưu tiên nguồn ĐẢO NGƯỢC so với rulesworldsimulator cũ: hãng tin sự thật
    # lên top, blog/fandom xuống đáy. Số càng nhỏ càng ưu tiên cao.
    SOURCE_PRIORITY = {
        # Tier 1 — Hãng thông tấn quốc tế uy tín cao
        "reuters.com": 1, "apnews.com": 1, "afp.com": 1, "bbc.com": 1,
        "bbc.co.uk": 1,
        # Tier 2 — Báo lớn / đài quốc gia
        "aljazeera.com": 2, "theguardian.com": 2, "cnn.com": 2,
        "nytimes.com": 2, "washingtonpost.com": 2, "npr.org": 2,
        "vnexpress.net": 2, "tuoitre.vn": 2, "thanhnien.vn": 2,
        # Tier 3 — Cơ quan chính phủ / tổ chức quốc tế (số liệu chính thức)
        "who.int": 3, "reliefweb.int": 3, "usgs.gov": 3, "noaa.gov": 3,
        "un.org": 3,
        # Tier 4 — Báo khu vực / chuyên ngành thứ cấp
        "aa.com.tr": 4, "straitstimes.com": 4, "japantimes.co.jp": 4,
        # Tier thấp nhất — blog, fandom, diễn đàn (mặc định nếu không khớp)
        "reddit.com": 8, "fandom.com": 9,
    }
    DEFAULT_SOURCE_PRIORITY = 6  # domain lạ, chưa phân loại

    # 4 nhóm chủ đề xoay vòng (thay cho keyword tĩnh của rulesworldsimulator).
    # Mỗi lần chạy chọn 1 nhóm theo round-robin, dùng state file lưu index.
    TOPIC_GROUPS = {
        "disaster": [
            "earthquake casualties evacuation", "typhoon landfall damage",
            "flood emergency declared", "wildfire evacuation order",
            "volcanic eruption alert",
        ],
        "geopolitics": [
            "sanctions imposed government", "ceasefire collapse conflict",
            "military mobilization border", "diplomatic crisis embassy",
            "coup attempt government",
        ],
        "economy": [
            "market crash plunge", "currency collapse crisis",
            "bank collapse bailout", "inflation emergency measures",
            "trade embargo announced",
        ],
        "humanitarian": [
            "mass casualties disaster", "refugee crisis emergency",
            "humanitarian crisis famine", "state of emergency declared",
            "death toll rises",
        ],
    }
    TOPIC_ROTATION_STATE_FILE = "data/module2_state/topic_rotation.json"

    # Từ vựng đo lường TÁC ĐỘNG THỰC TẾ — thay cho DRAMA_KEYWORDS giả tưởng
    # của rulesworldsimulator. Dùng cho summarizer.py (boost điểm câu) và
    # T1-style classify (không được coi là drama hư cấu).
    IMPACT_KEYWORDS = [
        "casualties", "fatalities", "death toll", "injured", "missing",
        "evacuated", "evacuation", "displaced", "shelter",
        "sanctions", "embargo", "ceasefire", "mobilization",
        "market crash", "collapse", "bankruptcy", "default",
        "state of emergency", "emergency declaration", "curfew",
        "humanitarian crisis", "famine", "refugee", "aid convoy",
    ]


class PeopleSettings:
    """Module 3: Nhân vật nổi bật (cửa sổ 24h qua)."""

    COLLECTION = "notable_people"
    TTL_HOURS = 24

    WIKIMEDIA_PAGEVIEWS_URL = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/all-access/{year}/{month}/{day}"
    )
    WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
    WIKIPEDIA_API_URL = "https://{lang}.wikipedia.org/w/api.php"

    PROJECTS = {
        "international": "en.wikipedia",
        "vietnam": "vi.wikipedia",
    }
    TOP_N_PER_PROJECT = 3  # 3 quốc tế + 3 Việt Nam = 6 tổng

    # Trang kỹ thuật/không phải nhân vật thường lọt top pageviews, loại thủ công
    EXCLUDE_TITLES = {
        "Main_Page", "Trang_Chính", "Special:Search", "Wikipedia",
    }

    CONTEXT_SEARCH_QUERY_SUFFIX = "why trending news today"
    HTTP_TIMEOUT_SECONDS = 15


class ComedySettings:
    """Module 4: Xúc tu Hài hước & Đời sống (kho "nguyên liệu bẻ lái" cho
    cơ chế cứu nguy khi Chimera bị lặp/bế tắc kịch bản — xem README module4)."""

    COLLECTION = "human_comedy_tropes"
    TTL_HOURS = 24 * 30  # 30 ngày — tuổi thọ cao hơn tin tức sự kiện (48h)

    MAX_TEXT_CHARS = 500        # context/punchline > ngưỡng này bị cắt/loại
    MIN_CONTEXT_CHARS = 20      # loại bài quá ngắn, không đủ ngữ cảnh
    MAX_TROPES_PER_RUN = 20

    KEYWORD_STATE_DIR = "data/module4_state"
    KEYWORD_ROTATION_STATE_FILE = "data/module4_state/keyword_rotation.json"
    LINKS_PER_SEARCH = 10

    # === LUỒNG 1: Direct fetch — API JSON công khai, không cần Playwright ===
    REDDIT_BASE_URL = "https://www.reddit.com"
    REDDIT_SUBREDDITS = ["VietNam", "TroChuyenLinhTinh"]
    REDDIT_TIME_FILTER = "week"   # top posts of the week
    REDDIT_POSTS_PER_SUB = 5
    REDDIT_COMMENTS_PER_POST = 1  # chỉ cần comment vote cao nhất (punchline)

    # Voz — best-effort, DOM XenForo có thể đổi theo thời gian (giống rủi ro
    # NCHMF/JTWC ở Module 1: lỗi ở đây không được để crash toàn Module 4).
    VOZ_THREAD_LIST_URL = "https://voz.vn/f/thu-gian.101/"
    VOZ_THREAD_LIST_SELECTOR = "div.structItem-title a"
    VOZ_THREADS_PER_RUN = 5
    VOZ_POST_SELECTOR = "article.message"          # 1 element / post (chứa content + reactions)
    VOZ_POST_CONTENT_SELECTOR = "div.bbWrapper"     # relative to VOZ_POST_SELECTOR
    VOZ_REACTION_SCORE_SELECTOR = "a.reactionsBar-link"  # relative to VOZ_POST_SELECTOR

    # === LUỒNG 2: Search cascade theo nhóm từ khóa mồi xoay vòng ===
    SEED_KEYWORD_GROUPS = {
        "cong_so": [
            "chuyện dở khóc dở cười công sở",
            "sếp giao việc tréo ngoe",
            "đồng nghiệp làm điều bất ngờ hài hước",
        ],
        "gia_dinh": [
            "tình huống trớ trêu trong gia đình",
            "con nít nói câu khiến cả nhà cười",
            "chuyện hài hước ông bà nội ngoại",
        ],
        "trend_mxh": [
            "trend mạng xã hội gây cười tuần này",
            "bình luận bá đạo dân mạng",
            "câu chuyện hài hước dân mạng chia sẻ",
        ],
        "doi_song": [
            "tình huống hài hước giao thông xe ôm",
            "sự cố hài hước nơi công cộng",
            "chuyện dở khóc dở cười đi chợ siêu thị",
        ],
    }

    # === BỘ LỌC VĂN BẢN SƠ CẤP (regex, không phải guardrail đầy đủ — phần
    # platform_and_legal_guardrails đầy đủ nằm ở tầng downstream/Phase 2) ===
    BANNED_SUBSTRINGS = [
        "inbox zalo", "zalo:", "sđt:", "sdt:", "hotline", "link bio",
        "tải app", "vay tiền nhanh", "click vào đây", "xem thêm tại",
        "quảng cáo", "tài trợ", "khuyến mãi",
    ]


shared = SharedSettings()
weather = WeatherSettings()
events = EventsSettings()
people = PeopleSettings()
comedy = ComedySettings()


def init_dirs():
    """Tạo các thư mục state cần thiết. Gọi tường minh từ entrypoint (vd.
    `if __name__ == "__main__":` của mỗi module's run.py) — KHÔNG chạy tự
    động lúc import config.py (DC-3: side effect tại import time là
    anti-pattern, vd. test code `import config` sẽ tạo dirs không mong
    muốn). Trong thực tế các state writer (`topics.py`, `keywords.py`)
    đã tự `os.makedirs(..., exist_ok=True)` khi ghi, nên hàm này chỉ cần
    thiết nếu muốn đảm bảo dirs tồn tại trước đó (vd. mount volume, CI cache).
    """
    for d in [shared.DATA_DIR, events.KEYWORD_STATE_DIR, comedy.KEYWORD_STATE_DIR]:
        os.makedirs(d, exist_ok=True)
