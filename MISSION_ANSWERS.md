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

> Ghi chú: cổng 8000 trên máy đang bị một tiến trình khác chiếm nên em chạy server ở cổng **8103** (`uvicorn app:app --port 8103`). Mọi lệnh curl bên dưới dùng `localhost:8103`; còn lại giống `CODE_LAB.md`. Token đã che.

### Exercise 4.1: API Key authentication (develop)

Chạy: `AGENT_API_KEY=secret-key-123 uvicorn app:app --port 8103` trong `04-api-gateway/develop/`.

```text
$ curl -i localhost:8103/ask -X POST -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i localhost:8103/ask -X POST -H "X-API-Key: wrong" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i localhost:8103/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

- **Key được check ở đâu?** Hàm `verify_api_key` (`develop/app.py`, dòng 39-54) là dependency của FastAPI, gắn vào `/ask` bằng `Depends(verify_api_key)`. Nó đọc header `X-API-Key` qua `APIKeyHeader` và so với `API_KEY` lấy từ env `AGENT_API_KEY` (dòng 35).
- **Sai key thì sao?** Thiếu key trả **401**, có key nhưng sai trả **403** (đã chạy ở trên). Request bị chặn trước khi vào hàm `ask_agent`, không tốn tiền LLM. `/` và `/health` vẫn public.
- **Rotate key?** Đổi giá trị biến môi trường `AGENT_API_KEY` rồi restart/redeploy; không phải sửa code vì key không hardcode (chỉ có default demo `demo-key-change-in-production`, nên production bắt buộc đặt env). Key cũ lập tức vô hiệu. Hạn chế: chỉ có một key duy nhất, muốn rotate không downtime thì phải hỗ trợ nhiều key cùng lúc (key cũ + key mới) trong giai đoạn chuyển.

### Exercise 4.2: JWT authentication (production)

Dừng develop, chạy `uvicorn app:app --port 8103` trong `04-api-gateway/production/`. Lấy token bằng `POST /auth/token` với `student` / `demo123`:

```text
$ curl -s localhost:8103/auth/token -X POST -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
{"access_token":"eyJ...REDACTED","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."}

$ curl -i localhost:8103/ask -X POST -H "Authorization: Bearer eyJ...REDACTED" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). ...","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
```

Không gửi token thì `/ask` trả 401 (đã thử).

**JWT flow** (`production/auth.py`):
1. Client gửi username/password tới `/auth/token`; `authenticate_user` (dòng 70-75) so với `DEMO_USERS`, sai thì 401.
2. `create_token` (dòng 35-43) tạo payload `sub` (user), `role`, `iat`, `exp` (+60 phút) rồi ký HS256 bằng `JWT_SECRET`.
3. Client gửi `Authorization: Bearer <token>` ở mỗi request.
4. `verify_token` (dòng 46-68) kiểm chữ ký + hạn bằng `jwt.decode`; hết hạn trả 401, token sai/giả trả 403. Không cần tra DB, server stateless: role lấy ngay từ token.

Lưu ý: `requests_remaining: 9` vì request này là request thứ nhất trong cửa sổ 10 req/phút. Trường `budget_remaining_usd` trong response thực chất là `usage.total_cost_usd` (tiền **đã dùng**, `app.py` dòng 160), tên field gây hiểu nhầm; số `/me/usage` cho thấy còn lại 0.999816 USD.

### Exercise 4.3: Rate limiting

Vòng lặp curl của em với token student (request #1 là lệnh 200 ở 4.2, nên vòng lặp bắt đầu từ request thứ 2 trong cửa sổ):

```bash
for i in $(seq 1 14); do curl -s -o /dev/null -w "$i:%{http_code}\n" localhost:8103/ask -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"question\":\"Test $i\"}"; done
```

Kết quả: lần 1 đến 9 trả **200** (9 request, cộng 1 request ở 4.2 thành đúng 10), lần 10 đến 14 trả **429** (5 request).

```text
$ curl -i localhost:8103/ask -X POST -H "Authorization: Bearer eyJ...REDACTED" -H "Content-Type: application/json" -d '{"question":"Test 15"}'
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795679863
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

- **Algorithm:** Sliding Window (log các timestamp), `production/rate_limiter.py`. Mỗi user có một `deque` timestamp (dòng 27, `defaultdict(deque)`). Mỗi request: bỏ timestamp cũ hơn 60 giây bằng `window.popleft()` (dòng 40), nếu `len(window) >= max_requests` (dòng 45) thì raise 429 kèm `Retry-After` tính từ timestamp cũ nhất (dòng 47), ngược lại ghi `window.append(now)`. Cửa sổ trượt theo thời gian nên không bị "dồn" 2 lần limit ở ranh giới phút như fixed window.
- **Limit:** user 10 req/60s (`rate_limiter_user`), admin 100 req/60s (`rate_limiter_admin`), dòng 86-87.
- **Bypass cho admin:** không bypass hẳn mà có tier cao hơn: `app.py` dòng 141 chọn `rate_limiter_admin` nếu `role == "admin"` (role lấy từ JWT, tài khoản `teacher`).
- **Hạn chế:** state nằm trong RAM của từng process (`self._windows`), nên chạy nhiều instance thì mỗi instance đếm riêng và restart là mất; production thật cần Redis.

### Exercise 4.4: Cost guard

`production/cost_guard.py` (bản có sẵn, em đọc và giải thích, không viết lại):

- **Budget:** mỗi user **1 USD/ngày** (`daily_budget_usd=1.0`) và toàn hệ thống **10 USD/ngày** (`global_daily_budget_usd=10.0`), singleton ở dòng 128. Cảnh báo log khi dùng 80% (`warn_at_pct`).
- **Cách tính:** `record_usage` (dòng 93-110) cộng `input_tokens`/`output_tokens` vào `UsageRecord` của user và cộng chi phí vào `_global_cost`; giá theo GPT-4o-mini (0.00015 / 0.0006 USD mỗi 1K token). Trong `app.py`, token là số ước lượng `số từ x 2`.
- **Khi vượt:** `check_budget` (dòng 60-90) được gọi **trước** khi gọi LLM (`app.py` dòng 145). Vượt budget user thì **402 Payment Required**, body có `used_usd`, `budget_usd`, `resets_at`; vượt budget toàn cục thì **503**.
- **State lưu ở đâu:** trong RAM (`self._records`, `self._global_cost`), mất khi restart và không chia sẻ giữa các instance. File ghi rõ production nên dùng Redis/DB.
- **Reset:** theo **ngày**, không phải tháng. `_get_record` (dòng 53-58) so `record.day` với ngày hiện tại (`time.strftime("%Y-%m-%d")`), khác ngày thì tạo `UsageRecord` mới. Lưu ý: ngày theo giờ local của server dù message nói "midnight UTC", và `_global_cost` chỉ khởi tạo một lần (`_global_today` được lưu nhưng không dùng để reset), nên budget toàn cục không tự reset khi sang ngày mới.

**Phiên bản `check_budget` với Redis (budget 10 USD/tháng theo CODE_LAB, pseudocode/giải thích, không sửa `06-lab-complete`):**

```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    key = f"budget:{user_id}:{datetime.now():%Y-%m}"   # key theo tháng => tự "reset" đầu tháng
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:                  # vượt budget -> False (caller trả 402)
        return False
    r.incrbyfloat(key, estimated_cost)                 # cộng dồn chi phí
    r.expire(key, 32 * 24 * 3600)                      # key cũ tự xoá sau 32 ngày
    return True
```

Vì state nằm trong Redis nên mọi instance cùng thấy một số, restart không mất. Một điểm yếu: đọc rồi ghi (`get` rồi `incrbyfloat`) không atomic, hai request đồng thời có thể cùng qua ngưỡng; cách sửa là `incrbyfloat` trước rồi kiểm kết quả (hoàn lại nếu vượt) hoặc dùng Lua script/`WATCH`.

**Vì sao cần cả rate limit lẫn cost guard:**
- Rate limit bảo vệ **tốc độ** (request/phút): chặn spam, DoS, một client chiếm hết tài nguyên. Nhưng không biết mỗi request tốn bao nhiêu tiền: 10 req/phút với prompt rất dài vẫn có thể đốt nhiều token.
- Cost guard bảo vệ **tiền** (tổng chi phí theo token): chặn bill bất ngờ dù client gọi chậm, đều đặn, dưới limit. Nhưng không chặn được burst làm quá tải server trong vài giây.
- Hai lớp bổ sung nhau: rate limit chạy trước (rẻ, từ chối sớm), cost guard chạy sau (đúng thứ tự `app.py` dòng 141-145). Thiếu một trong hai thì còn một lỗ hổng.

---

## Part 5: Scaling & Reliability

_CP4 — pending._

---

## Part 6: Final Project — check_production_ready.py

**Final score: PASS 12/12 — 12/12 tiêu chí đạt · 43/43 checks passed** (`python check_production_ready.py`, full mode with Docker, run in `06-lab-complete/`; image 273 MB, `docker stop` exit code 0 in 0.7s).

```
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Key design choices:
- `/health` (liveness) never touches Redis, so it stays 200 while the process lives; `/ready` pings Redis and returns 503 when it is down, so the platform stops routing traffic to the instance but does not restart a healthy process needlessly.
- Stateless app: rate-limit windows (Redis sorted set per hashed API key) and daily cost totals (`INCRBYFLOAT`) live in Redis, so multiple workers/instances share them and restarts keep the 429/402 state. The Redis client is created lazily, so the app (and the Docker image test, which has no Redis) still starts.
- Graceful shutdown: uvicorn is PID 1 (`CMD ["sh","-c","exec uvicorn ..."]`) and no custom SIGTERM handler overrides it; uvicorn finishes in-flight requests, runs the FastAPI `lifespan` shutdown (closes Redis), and exits 0.
- Config is 12-factor: everything comes from env vars (`config.py`), `.env.example` holds placeholders only, `.env` is git/docker-ignored, and `render.yaml` uses `generateValue: true` for `AGENT_API_KEY`.
- Logs are one JSON object per line (custom `JsonFormatter`, also attached to uvicorn loggers); auth fails closed with 401, validation errors return 422 JSON, and unhandled errors return a generic 500 with no stack trace.

---

## AI log

_Filled per checkpoint._
