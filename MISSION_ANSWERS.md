# Day 14 Lab - Mission Answers

> K5-L3B · Day 14 · Deployment, Benchmark & Observability

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `develop/app.py`

| # | Anti-pattern (dòng + code) | Vì sao nguy hiểm | `production/app.py` / `config.py` sửa thế nào |
|---|---|---|---|
| 1 | L17 `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và L18 `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` | Secret nằm trong code, push lên GitHub là lộ | `config.py` L27 `os.getenv("OPENAI_API_KEY", "")`, L32 `os.getenv("AGENT_API_KEY", "")`; `app.py` L24 `from config import settings` |
| 2 | L21-22 `DEBUG = True`, `MAX_TOKENS = 500` (config cứng, không quản lý tập trung) | Đổi môi trường phải sửa code | `config.py` L19 `os.getenv("DEBUG", "false")`, L29 `max_tokens`, L50 `settings = Settings().validate()` (fail fast, L42-43) |
| 3 | L33 `print(f"[DEBUG] Got question: {question}")` | `print` không có level/timestamp/format, khó parse | `app.py` L28-31 `logging.basicConfig(... format='{"time":...}')`, L111 `logger.info(json.dumps({...}))` |
| 4 | L34 `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` | Log ra secret, ai đọc log cũng thấy key (thấy thật trong log ở Exercise 1.2) | L110 comment "KHÔNG log secrets"; L111-115 chỉ log `question_length`, `client_ip` |
| 5 | L42-43 không có health check endpoint | Platform không biết agent crash để restart, LB không biết route đi đâu | `app.py` L135 `@app.get("/health")` (liveness), L152 `@app.get("/ready")` (readiness, 503 khi chưa sẵn sàng, L159-160) |
| 6 | L51 `host="localhost"` | Chỉ nhận kết nối nội bộ, trong container/cloud không truy cập được | `app.py` L196 `host=settings.host`; `config.py` L17 mặc định `"0.0.0.0"` |
| 7 | L52 `port=8000` | Railway/Render inject `PORT`, port cứng sẽ sai hoặc đụng port khác | `app.py` L197 `port=settings.port`; `config.py` L18 `int(os.getenv("PORT", "8000"))` |
| 8 | L53 `reload=True` | Reload theo file change chỉ dành cho dev, tốn tài nguyên ở production | `app.py` L198 `reload=settings.debug` (chỉ bật khi `DEBUG=true`) |
| 9 | Không có graceful shutdown/lifespan (cả file không xử lý SIGTERM) | Container bị tắt đột ngột, request đang chạy bị cắt | `app.py` L39-67 `lifespan` (startup/shutdown), L180-189 `handle_sigterm` + `signal.signal(signal.SIGTERM, ...)` |

### Exercise 1.2: Chạy bản develop

Lưu ý trung thực: port 8000 trên máy đang bị một process khác (không thuộc bài lab) chiếm, nên mình không chạy `python app.py` (hardcode 8000) mà chạy trực tiếp bằng uvicorn trên **port 8101** (develop) và đặt `PORT=8111` cho bản production. Không kill process nào ngoài các process mình tự khởi chạy. Dùng Python 3.13 trong venv nằm ngoài repo.

```bash
cd 01-localhost-vs-production/develop
uvicorn app:app --port 8101
curl -X POST "http://localhost:8101/ask?question=Hello"
```
Output thật:
```
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```
`curl http://localhost:8101/` trả về `{"message":"Hello! Agent is running on my machine :)"}`

Log phía server (minh chứng anti-pattern #4, key bị in ra):
```
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). ...
INFO:     127.0.0.1:51389 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```
Bản develop chạy được trên localhost nhưng chưa production-ready: không có `/health`, `/ready`, và log lộ key.

Bản production (`PORT=8111 python app.py` trong `production/`):
```
$ curl localhost:8111/health
{"status":"ok","uptime_seconds":5.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:56:32.220832+00:00"}
$ curl localhost:8111/ready
{"ready":true}
$ curl -X POST localhost:8111/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```
Log server: `Uvicorn running on http://0.0.0.0:8111`, không có secret trong log.

### Exercise 1.3: So sánh develop vs production

| Feature | Develop (basic) | Production (advanced) | Tại sao quan trọng? |
|---|---|---|---|
| Config | Hằng số trong code (L21-22) | Env vars qua `Settings` dataclass (`config.py`) | Đổi giữa dev/staging/prod không cần sửa code (12-factor) |
| Secrets | Hardcode key + DB password (L17-18) | `os.getenv`, không có trong repo | Tránh lộ khi push Git; xoay key không cần deploy lại code |
| Validation | Không | `validate()` fail fast nếu thiếu `AGENT_API_KEY` ở production | Lỗi cấu hình lộ ngay lúc khởi động thay vì lúc chạy |
| Host binding | `localhost` | `0.0.0.0` (`HOST`) | Trong container, `localhost` không nhận traffic từ ngoài |
| Port | Cứng `8000` | Từ `PORT` env | Cloud (Railway/Render) tự inject port; tránh đụng port (như 8000 trên máy mình) |
| Debug/reload | `reload=True` luôn bật | `reload=settings.debug` (mặc định false) | Reload ở production tốn tài nguyên, kém ổn định |
| Logging | `print()`, in cả secret | JSON log có level, không log secret | Log aggregator (Loki/Datadog) parse, search được; không rò rỉ |
| Health check | Không có | `/health` (liveness), `/ready` (readiness), `/metrics` | Platform biết khi nào restart, LB biết khi nào route traffic |
| Shutdown | Tắt đột ngột | `lifespan` + SIGTERM handler | Hoàn tất request đang chạy, không mất dữ liệu |
| Input / CORS | `question` là query param, không CORS | JSON body, trả 422 nếu thiếu, CORS theo `allowed_origins` | Validate đầu vào và giới hạn origin giảm bề mặt tấn công |

### Cần hiểu

- **Vì sao hardcode secret nguy hiểm:** secret vào Git history thì ai đọc được repo (hoặc bản fork) đều lấy được, kể cả sau khi xóa khỏi code; bot quét GitHub tìm key trong vài phút, dẫn đến mất tiền hoặc lộ dữ liệu. Secret nên để ở env/secret manager, dễ đổi và thu hồi.
- **Vì sao cần health check:** platform dùng `/health` để phát hiện agent treo/crash và tự restart, `/ready` để load balancer chỉ gửi traffic khi agent đã sẵn sàng. Không có thì process "sống nhưng hỏng" vẫn nhận request.
- **Vì sao cần graceful shutdown:** khi deploy/scale, platform gửi SIGTERM; nếu tắt ngay, request đang xử lý bị rớt và dữ liệu dở dang bị mất. Graceful cho phép hoàn tất request rồi đóng connection sạch.

---

## Part 2: Docker

_CP2 — pending._

---

## Part 3: Cloud Deployment

_CP6 — pending._

---

## Part 4: API Security

_CP3 — pending._

---

## Part 5: Scaling & Reliability

_CP4 — pending._

---

## Part 6: Final Project — check_production_ready.py

_CP5 — pending._

---

## AI log

_Filled per checkpoint._
