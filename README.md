# worldpulse-tentacle

Xúc tu thứ 3 thu thập "nhịp đập thực tại" (thời tiết, biến cố, nhân vật) làm
nguyên liệu thô khách quan cho hệ thống lõi (Chimera) chuyển hóa thành biến
số trong thế giới mô phỏng.

**Nguyên tắc:** repo này chỉ gom sự thật khách quan. Không LLM nào ở đây
được phép đóng vai nhà văn hay gán ghép tính cách/số phận hư cấu — việc
"phiên dịch ẩn dụ" là nhiệm vụ tầng downstream.

## Kiến trúc: 4 micro-module độc lập

Khác với `rulesworldsimulator` (1 luồng Pomodoro nối tiếp), mỗi module ở đây
chạy độc lập trên cron GitHub Actions riêng. Module 1-3 chạy **2 lần/ngày
(12h/lần)**, lệch phút khởi chạy để tránh ghi Mongo cùng lúc. Module 4 chạy
**1 lần/ngày** (dữ liệu hài hước tuổi thọ cao hơn, không cần tần suất cao):

| Module | Cron (UTC) | Nội dung | Collection | TTL |
|---|---|---|---|---|
| 1 — Thời tiết | `0 2,14 * * *` | Open-Meteo + bản tin NCHMF/JTWC, 10 tọa độ tĩnh | `weather_pulses` | 48h |
| 2 — Sự kiện | `10 2,14 * * *` | Search cascade (Playwright) theo nhóm chủ đề xoay vòng | `extreme_events` | 48h |
| 3 — Nhân vật | `20 2,14 * * *` | Wikimedia Pageviews + Wikidata P31=Q5 + 6 truy vấn ngữ cảnh | `notable_people` | 24h |
| 4 — Hài hước & Đời sống | `30 3 * * *` | Reddit JSON + Voz (direct fetch) + search cascade từ khóa mồi | `human_comedy_tropes` | 30 ngày |
| 5 — Cross-Tentacle Dashboard | `0 4 * * *`, `50 14 * * *` | Chỉ ĐỌC field envelope của cả 4 collection trên, không ghi gì | — | — |

Module 4 là kho "nguyên liệu bẻ lái" cho cơ chế Circuit Breaker của Chimera
(downstream): mỗi bản ghi gồm `context` + `punchline` đã qua lọc rác cấp
thấp (`module4_comedy/text_filter.py`). Bộ lọc kiểm duyệt nội dung đầy đủ
(`platform_and_legal_guardrails`) chạy ở tầng downstream, không nằm trong
repo này. Xem docstring đầu file `module4_comedy/run.py` để rõ ranh giới.

## Output Contract (Envelope) — Tầng 0 → World Simulator

Mọi document ghi vào 4 collection trên đều đi qua `shared/envelope.py::build_envelope()`
trước khi `insert_with_ttl()` — đây là nguồn chân lý duy nhất cho 3 field
bắt buộc mà World Simulator Engine (File 2) đọc, không cần biết cấu trúc
nội bộ riêng của từng module:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `event_type` | `str`, 1 trong 4 giá trị enum (`shared/envelope.py::EventType`) | `environmental_pressure` (M1), `macro_disruption` (M2), `character_seed` (M3), `narrative_deflection` (M4) |
| `impact_weight` | `float`, luôn trong `[0.0, 1.0]` | Suy từ dữ liệu thu thập được (công thức riêng từng module, xem docstring `run.py`), không phải số cố định đoán mò |
| `extracted_facts` | `list[str]` | Câu factual khách quan (số liệu/tên/thời điểm/hành động) — không chứa cảm xúc/suy luận |

Document `storm_bulletin` của Module 1 dùng chung shape này (field `type`
tuỳ ý cũ đã bị loại bỏ hoàn toàn) — không còn 2 hệ thống phân loại song
song trong cùng collection `weather_pulses`.

## Hallucination Barrier — Kiểm tra tự động

Repo này không được phép chứa bất kỳ lệnh gọi LLM thật nào (mọi tóm tắt đi
qua `shared/summarizer.py`, thuần Python/Luhn's algorithm). Ranh giới này
được enforce **bằng máy**, không chỉ bằng docstring/comment: mỗi workflow
`.github/workflows/moduleX_*.yml` có 1 bước `🔒 Hallucination Barrier` chạy
**trước** bước `Run Module X`, `grep` toàn bộ `.py` tìm import bị cấm
(`openai`, `anthropic`, `google.generativeai`). Nếu phát hiện, step fail
cứng (`exit 1`), chặn workflow chạy tiếp. Bất kỳ ai thêm code sau này lỡ
import 1 trong các SDK trên sẽ bị CI chặn ngay, không cần review thủ công.

## Hạ tầng dùng chung (`shared/`)

Tái sử dụng nguyên trạng từ `rulesworldsimulator`:
- `stealth.py` — UA rotation + headers giả lập trình duyệt thật.
- `domain_ban.py` — ban có hạn (cooldown 7 ngày), dùng chung cho M2 và bước 2 M3.
- `summarizer.py` — extractive summary (Luhn's algorithm), nhận `domain_keywords`
  khác nhau tùy module gọi (impact keywords cho M2, không dùng keyword riêng cho M3).

Mới viết cho repo này:
- `search_cascade.py` — tổng quát hóa `t0_search.py` cũ thành 1 class dùng
  chung cho M2 và bước 2 của M3 (trước đây gắn cứng vào 1 pipeline).
- `mongo.py` — kết nối + `ensure_ttl_index()` + `insert_with_ttl()` dùng chung.

Module 1 **không** dùng `stealth.py`/`search_cascade.py` — đây là luồng API
sạch (Open-Meteo), gọi trực tiếp bằng `requests`.

## Cấu hình (`config.py`)

Chia 3 namespace riêng (`WeatherSettings`, `EventsSettings`, `PeopleSettings`)
thay vì 1 `Settings` phẳng như bản cũ, để sửa tham số module này không ảnh
hưởng nhầm module khác.

## Biến môi trường / GitHub Secrets cần thiết lập

| Secret | Bắt buộc | Ghi chú |
|---|---|---|
| `MONGODB_URI` | Có | Connection string cụm M0 (512MB) |
| `MONGODB_DB_NAME` | Không | Mặc định `worldpulse` |

## Chạy thử cục bộ

```bash
pip install -r requirements.txt
playwright install chromium   # chỉ cần cho Module 2 và 3

export MONGODB_URI="mongodb+srv://..."

python -m module1_weather.run
python -m module2_events.run
python -m module3_people.run
python -m module4_comedy.run
```

## Rủi ro đã biết / cần theo dõi

- **NCHMF/JTWC scraping** (`module1_weather/fetch.py::fetch_storm_bulletins`):
  selector hiện tại chỉ lấy text thô đầu trang do chưa kiểm tra được DOM
  thật của 2 trang này. Cần tinh chỉnh khi có kết quả chạy thật đầu tiên.
  Lỗi ở đây không làm crash Module 1 (best-effort, có try/except riêng).
- **Freshness filter M2** (`module2_events/fetch.py::is_fresh_enough`): nếu
  không tìm được metadata ngày xuất bản, mặc định CHO QUA bài viết (an toàn
  hơn loại nhầm) — nghĩa là một số bài không có metadata chuẩn vẫn có thể
  lọt qua dù đã cũ. `fetch_article()` đã chuyển sang `shared/fetch.py` (xem
  mục "Việc cần làm" — coupling M4→M2 đã gỡ); `module2_events/fetch.py` giờ
  chỉ còn `is_fresh_enough()` + re-export `fetch_article` để không phá import cũ.
- **Voz scraping M4** (`module4_comedy/voz_source.py`): selector XenForo
  chưa kiểm chứng trên DOM thật của voz.vn, cùng rủi ro như NCHMF ở M1. Best
  -effort, có try/except riêng, không chặn luồng Reddit/Search Cascade nếu
  lỗi.
- **Bộ lọc thô tục M4** (`module4_comedy/text_filter.py`): danh sách rút
  gọn, KHÔNG phải bộ kiểm duyệt đầy đủ — chỉ che các từ lóng phổ biến nhất.
  Nội dung vẫn phải qua `platform_and_legal_guardrails` ở tầng downstream
  trước khi vào Phase 2 của Chimera.
- **State file M2/M3/M4** (`blackbook.json`, `data/module2_state/topic_rotation.json`,
  `data/module4_state/keyword_rotation.json`): được workflow tự commit lại
  sau mỗi lần chạy — cần Actions có quyền `contents: write` (mặc định
  `GITHUB_TOKEN` đã đủ quyền cho repo riêng).

## Việc cần làm cho phiên sau

Phiên này đã vá xong toàn bộ bug/design-concern trong `review-worldpulse-module4.md`
(BUG-1 → BUG-5, DC-1 → DC-3, coupling M4→M2, timeout CI, thiếu index). Còn lại:

### Cần xác minh trên môi trường thật (không kiểm chứng được ở đây — sandbox không có network)
- [ ] **BUG-1 fix (Voz reaction score)**: fix mới giả định mỗi post nằm
  trong `article.message` chứa cả `div.bbWrapper` (nội dung) lẫn
  `a.reactionsBar-link` (reaction) — đúng với XenForo phổ biến nhưng CHƯA
  chạy thử trên DOM thật voz.vn. Chạy `workflow_dispatch` thủ công 1 lần,
  log vài `best_score`/`best_text` ra để đối chiếu bằng mắt với thread thật.
- [ ] **BUG-2 fix (search_batch)**: đo lại runtime thực tế của Module 4 sau
  fix (kỳ vọng giảm từ ~18-24 phút xuống còn ~1 lần browser launch + tổng
  thời gian các engine). Nếu vẫn sát ngưỡng 30 phút mới (đã tăng từ 20),
  cân nhắc giảm `LINKS_PER_SEARCH` hoặc số keyword/nhóm.
- [ ] **BUG-3 fix (commit keyword rotation)**: chạy vài lần liên tiếp (kể cả
  giả lập fail bằng cách ngắt mạng) để xác nhận `last_index` chỉ advance khi
  có kết quả thật.

### Việc chưa làm (không phải bug, nằm ngoài phạm vi bugfix)
- [ ] **Test coverage vẫn bằng 0** — repo chưa có test nào. Ưu tiên viết
  test cho `search_cascade.search_batch()`, `keywords.get_next_keyword_group()`
  /`commit()`, và `voz_source._extract_thread_context_and_punchline()` vì
  đây là 3 chỗ vừa sửa logic quan trọng.
- [ ] **Type hints còn thiếu** ở một số hàm (chủ yếu return type annotation)
  — dọn dần, không gấp.
- [ ] **BUG-5 fallback dedup** (context+punchline khi `source_url` rỗng) chỉ
  là giảm nhẹ triệu chứng. Nếu tỉ lệ Voz trả về URL rỗng cao, nên sửa tận
  gốc: kiểm tra lại logic extract `href` trong `voz_source._list_thread_urls()`.
- [ ] **`priority_sources` trong `search_engines.json`** hiện để trống (đã
  xoá list xenobiology sai ngữ cảnh). Quyết định: hoặc bỏ hẳn field
  `is_priority_source` khỏi `search_cascade.py` (vì không module nào dùng),
  hoặc thật sự implement per-module priority nếu có nhu cầu (vd. Module 2 ưu
  tiên hãng tin lớn — nhưng M2 đã có `SOURCE_PRIORITY` riêng trong
  `config.py`, nên khả năng cao field này chỉ nên xoá hẳn).
- [ ] **`config.init_dirs()`**: mới tách ra khỏi import-time side effect,
  hiện KHÔNG module nào gọi (không bắt buộc vì các state writer tự
  `os.makedirs` khi ghi). Nếu muốn dirs tồn tại trước khi chạy (vd. mount
  volume/cache CI), gọi tường minh ở đầu mỗi `run.py`.
- [ ] **Pin SHA cho GitHub Actions** (`actions/checkout@v4` → SHA cụ thể) —
  security hardening tuỳ chọn, không gấp cho dự án cá nhân.
- [ ] **Module 3 (`module3_people/run.py`) cũng gọi `cascade.search()` trong
  vòng lặp per-person** — không nằm trong phạm vi review Module 4, nhưng
  đáng kiểm tra runtime tương tự BUG-2 nếu số người/run tăng lên; có thể áp
  dụng `search_batch()` ở đây nếu cần.


## Cập nhật phiên đóng gói này (pre-Phase-1)

- **BUG-3 pattern cho Module 2**: `module2_events/topics.py` đã được tách
  `get_next_topic_group()` (peek) và `commit_topic_group(group_name)`
  (advance state), khớp pattern `module4_comedy/keywords.py`.
  `module2_events/run.py` chỉ gọi `commit_topic_group(topic_name)` khi
  `saved_count > 0` — nếu toàn bộ cascade search fail, nhóm chủ đề không
  bị tính là "đã dùng". Sẵn sàng cho Giai đoạn 1 (Output Contract) trong
  `HANDOFF-phien-sau-1.md`.
