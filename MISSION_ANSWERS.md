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

### Exercise 2.1: Dockerfile cơ bản (`02-docker/develop/Dockerfile`)
1. **Base image**: `python:3.11` (bản full, Debian + Python runtime; không phải `-slim`).
2. **Working directory**: `/app` (`WORKDIR /app`).
3. **COPY `requirements.txt` trước**: tận dụng layer cache. Dependencies ít đổi nên layer `pip install` được cache; khi chỉ sửa code (`COPY app.py`) Docker không phải cài lại dependencies.
4. **CMD vs ENTRYPOINT**: `CMD` là lệnh/tham số mặc định, dễ bị ghi đè bằng `docker run <image> <lệnh khác>`; `ENTRYPOINT` là executable cố định của container (muốn đổi phải dùng `--entrypoint`). Thường kết hợp: ENTRYPOINT = chương trình, CMD = tham số mặc định. Dockerfile này dùng `CMD ["python", "app.py"]`.

### Exercise 2.2: Build và run
Lưu ý: port 8000 trên host đang bị một process khác (không liên quan) chiếm, nên mình map sang **host port 8102** (`-p 8102:8000`) thay vì 8000. Endpoint `/ask` của `app.py` nhận `question` dạng query param.
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name cp2-dev -p 8102:8000 my-agent:develop
curl -X POST "http://localhost:8102/ask?question=Hello"
# {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
curl http://localhost:8102/health
# {"status":"ok","uptime_seconds":8.4,"container":true}
```

### Exercise 2.3: Multi-stage build
- **Stage 1 (builder)**: `python:3.11-slim` + `gcc`, `libpq-dev`; `pip install --user` dependencies vào `/root/.local`. Stage này không được deploy.
- **Stage 2 (runtime)**: `python:3.11-slim` sạch, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local` + source code, có `HEALTHCHECK`, chạy uvicorn 2 workers.
- **Vì sao nhỏ hơn**: (1) base `slim` thay vì `python:3.11` full (1.62GB vs 189MB); (2) toolchain build (gcc, apt cache, header) nằm ở builder và bị bỏ đi, runtime không mang theo; (3) chỉ copy site-packages cần để chạy.

Đo thực tế (`docker images | grep my-agent`):
```
my-agent:advanced   034d14ead9c4   240MB    57.4MB
my-agent:develop    9eadc283acf3   1.67GB   426MB
```
| Image | Disk usage | Content size |
|---|---|---|
| develop (single-stage) | 1.67 GB | 426 MB |
| advanced (multi-stage) | 240 MB | 57.4 MB |
| Giảm | **~85.6%** (1.67GB → 240MB) | **~86.5%** (426 → 57.4MB) |

(Tính từ số liệu `docker images` ở trên, quy 1.67GB ≈ 1710MB. Vượt mức 50-70% kỳ vọng và đạt mục tiêu < 500MB.)

### Exercise 2.4: Docker Compose stack
```bash
cd 02-docker/production && touch .env.local   # gitignored, không commit
docker compose -p k5-day14-docker up -d --build
```
Port 80/443 bind thành công, không cần override. 4 services được start và đều healthy: `agent`, `redis`, `qdrant`, `nginx`.
```
 Client --HTTP :80/:443--> +---------+  upstream agent_backend  +-----------+
                           |  nginx  | -----------------------> |  agent    |  FastAPI :8000
                           | (rate   |                          | (uvicorn) |  (không publish port)
                           |  limit) |                          +-----+-----+
                           +---------+              REDIS_URL         |        QDRANT_URL
                                                  +------------------+------------------+
                                             +----v---+                            +----v----+
                                             | redis  | :6379                      | qdrant  | :6333
                                             +--------+                            +---------+
   Tất cả nằm trong network bridge `internal`; chỉ nginx publish port ra host.
```
Giao tiếp: các service gọi nhau qua DNS tên service trong network `internal` (`agent:8000`, `redis:6379`, `qdrant:6333`); `agent` chỉ start khi redis và qdrant healthy (`depends_on: service_healthy`); nginx là reverse proxy + rate limit 10 req/s/IP. Lưu ý: `main.py` hiện chỉ nhận env `REDIS_URL`/`QDRANT_URL` chứ chưa thực sự kết nối (grep không thấy dùng trong code), nên agent→redis/qdrant mới là cấu hình sẵn.

Test qua Nginx:
```bash
curl -i http://localhost/health
# HTTP/1.1 200 OK  (Server: nginx, X-Frame-Options: DENY, ...)
# {"status":"ok","uptime_seconds":7.3,"version":"2.0.0","timestamp":"2026-11-26T08:14:52.793094"}
curl http://localhost/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
# {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```
Debug: `docker compose -p k5-day14-docker ps`, `docker logs <container>`, `docker exec -it <container> sh`.

---

## Part 3: Cloud Deployment

Theo lớp K5, deploy chính agent Part 6 (`06-lab-complete/`), không deploy app mẫu `03-cloud-deployment/`.
Chi tiết lệnh và biến môi trường: [DEPLOYMENT.md](DEPLOYMENT.md).

### Exercise 3.1: Railway deployment (nền tảng chính)

- **URL:** https://agent-production-4fa29d22.up.railway.app
- **Cách deploy:** `cd 06-lab-complete` → `railway init` → `railway add --database redis` → tạo service `agent` với
  `AGENT_API_KEY` (ngẫu nhiên), `REDIS_URL=${{Redis.REDIS_URL}}`, `ENVIRONMENT=production` → `railway up` → `railway domain`.
- **Tự kiểm tra (4 lệnh CP6, 2026-11-26 08:52 UTC):**

  ```text
  GET  /health                 → 200
  GET  /ready                  → 200   (Redis trên Railway kết nối được)
  POST /ask  (không có key)    → 401
  POST /ask  (có X-API-Key)    → 200
  ```

- **Screenshot:** [dashboard](screenshots/dashboard.png) · [running](screenshots/running.png) · [test](screenshots/test.png)

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| Điểm | `railway.toml` | `render.yaml` | Vì sao khác |
| --- | --- | --- | --- |
| Phạm vi | Cấu hình **1 service** (build + deploy) | **Blueprint** cả hạ tầng: service `web` + `keyvalue` (Redis) | Railway tạo Redis bằng CLI/dashboard (`railway add --database redis`); Render muốn khai báo mọi thứ trong 1 file IaC |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `dockerfilePath` | Cùng build từ Dockerfile, chỉ khác cú pháp |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` | Cả hai dùng liveness `/health` để quyết định deploy thành công |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Render tự restart, không khai báo | Railway cho cấu hình policy ngay trong file |
| Secret | Không nằm trong file; đặt bằng `railway variables` / `railway add --variables` | `AGENT_API_KEY: generateValue: true` (Render tự sinh) | Không file nào chứa giá trị secret, nên commit an toàn |
| Nối Redis | `REDIS_URL=${{Redis.REDIS_URL}}` (biến tham chiếu, đặt trên platform) | `fromService: {type: keyvalue, property: connectionString}` | Render nối service ngay trong blueprint; Railway nối bằng biến tham chiếu |
| Env khác | Đặt trên dashboard/CLI | `envVars` khai báo trong file (`ENVIRONMENT`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`) | Render ưu tiên config-as-code; Railway ưu tiên CLI |

Railway hợp khi muốn deploy nhanh từ CLI (`railway up` upload thẳng thư mục). Render hợp khi muốn cả hạ tầng
(web + Redis + secret) nằm trong 1 file review được qua Git.

### Exercise 3.3: Cloud Run CI/CD (đọc `cloudbuild.yaml` + `service.yaml`, không deploy)

1. **Trigger:** push lên `main` → Cloud Build chạy `cloudbuild.yaml`.
2. **test:** image `python:3.11-slim` cài `requirements.txt` + chạy `pytest tests/`; test fail thì pipeline dừng, không build.
3. **build → push:** `docker build` gắn 2 tag `:$COMMIT_SHA` và `:latest` (dùng `--cache-from :latest` để tận dụng layer cache), rồi push lên Container Registry `gcr.io/$PROJECT_ID/ai-agent`.
4. **deploy:** `gcloud run deploy` bằng image `:$COMMIT_SHA` (truy vết được commit) ở `asia-southeast1`, min 1 / max 10 instance, 512Mi / 1 CPU, secret lấy từ Secret Manager (`--set-secrets`), không hardcode.
5. **`service.yaml`** là IaC (Knative) của service: autoscaling 1–10, `containerConcurrency: 80`, `livenessProbe` → `/health`, `startupProbe` → `/ready`, secret `AGENT_API_KEY` / `OPENAI_API_KEY` từ `secretKeyRef`.

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

> Ghi chú: cổng 8000 trên máy đang bị tiến trình khác chiếm nên Exercise 5.1–5.2 chạy bản develop bằng `PORT=8104 python app.py` (app đọc biến `PORT`), thay vì 8000. Python 3.13 trong venv ngoài repo. Stack Exercise 5.4 dùng cổng 8080 đúng như hướng dẫn.

### Exercise 5.1: Health và readiness

`05-scaling-reliability/develop/app.py` đã có sẵn cả hai endpoint. Chạy trên cổng 8104:

```
$ curl -s -w '\nHTTP %{http_code}\n' localhost:8104/health
{"status":"ok","uptime_seconds":2.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:56:45.782919+00:00","checks":{"memory":{"status":"ok","used_percent":66.4}}}
HTTP 200
$ curl -s -w '\nHTTP %{http_code}\n' localhost:8104/ready
{"ready":true,"in_flight_requests":1}
HTTP 200
```

- `/health` (liveness): "process còn sống không?". Nếu fail/timeout thì platform **restart** container. Chỉ nên kiểm tra bản thân process, không phụ thuộc dịch vụ ngoài.
- `/ready` (readiness): "đã sẵn sàng nhận traffic chưa?". Trả 503 khi đang khởi động (`_is_ready=False`), đang shutdown hoặc dependency (Redis/DB) chưa nối được. Load balancer **ngừng gửi traffic** nhưng không restart.
- (`in_flight_requests: 1` là chính request `/ready` đang được middleware đếm.)

### Exercise 5.2: Graceful shutdown

Gửi request chậm (mock LLM ngủ 3 giây) rồi `kill -TERM` sau 1 giây:

```
kill -TERM 21378
--- curl result
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
HTTP 200 time=3.083595s
--- log
INFO:     Shutting down
INFO:     127.0.0.1:51447 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 14:56:53,528 INFO 🔄 Graceful shutdown initiated...
2026-11-26 14:56:53,529 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [21378]
2026-11-26 14:56:53,530 INFO Received signal 15 — uvicorn will handle graceful shutdown
process exited
```

Request đang xử lý vẫn hoàn thành (HTTP 200 sau 3.08s) dù SIGTERM đến sau 1 giây; uvicorn ngừng nhận kết nối mới ("Shutting down"), chờ request xong rồi chạy phần shutdown của `lifespan` (đặt `_is_ready=False`, chờ `_in_flight_requests` về 0, tối đa 30s) rồi mới thoát. Nếu dùng SIGKILL thì request sẽ bị cắt ngang.

### Exercise 5.3: Stateless design

State trong RAM (ví dụ `conversation_history = {}`) hỏng khi chạy nhiều instance vì mỗi instance có bộ nhớ riêng: request 1 của user rơi vào instance A (lưu history ở A), request 2 qua load balancer rơi vào instance B thì B không thấy history, nên agent "mất trí nhớ". Instance bị restart/scale-down cũng mất toàn bộ state. Giải pháp: giữ state ở kho dùng chung (Redis); instance chỉ xử lý logic nên thay thế/nhân bản tuỳ ý. Bản `production/app.py` lưu session và history trong Redis (`/chat`, `/chat/{session_id}/history`).

### Exercise 5.4: Load balancing

```
$ touch .env.local   # đã gitignore, không commit
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
$ docker compose -p k5-day14-scaling ps
k5-day14-scaling-agent-1   Up (healthy)   8000/tcp
k5-day14-scaling-agent-2   Up (healthy)   8000/tcp
k5-day14-scaling-agent-3   Up (healthy)   8000/tcp
k5-day14-scaling-nginx-1   Up             0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up (healthy)   6379/tcp
```

(Lần `up` đầu bị Docker Hub trả 429 khi pull `nginx:alpine`, thử lại sau vài phút thì được.) Gọi 10 lần `POST /chat` qua Nginx, in `session_id` (8 ký tự đầu), `served_by`, `turn`:

```
43f30ad1 instance-515807 2
e435c0a7 instance-746c62 2
dee79a7d instance-33a180 2
ec2ec373 instance-515807 2
ddd06134 instance-746c62 2
5b6cca11 instance-33a180 2
649c0b96 instance-515807 2
a04c4ad6 instance-746c62 2
e88ec627 instance-33a180 2
19071c9c instance-515807 2
```

Nginx chia request round-robin qua 3 instance (515807 → 746c62 → 33a180 → lặp lại). Mỗi lệnh curl không gửi `session_id` nên mỗi lần tạo một session mới. Nếu một instance chết, Nginx chuyển traffic sang các instance còn lại (không thử trong bài này).

### Exercise 5.5: Test stateless

```
$ python test_stateless.py
Session ID: b922babc-328b-4092-88ed-bbc359eb02c9
Request 1: [instance-746c62]  Q: What is Docker?
Request 2: [instance-33a180]  Q: Why do we need containers?
Request 3: [instance-515807]  Q: What is Kubernetes?
Request 4: [instance-746c62]  Q: How does load balancing work?
Request 5: [instance-33a180]  Q: What is Redis used for?
Total requests: 5
Instances used: {'instance-515807', 'instance-33a180', 'instance-746c62'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

(Output rút gọn phần câu trả lời mock và danh sách 10 message.) Giải thích: 5 câu hỏi cùng một session được 3 instance khác nhau xử lý, nhưng khi đọc history có đủ 10 message (5 user + 5 assistant) vì state nằm trong Redis chứ không nằm trong RAM của instance nào. Script này không tự tắt instance nào, nên kết quả chứng minh state chia sẻ giữa các instance, chưa chứng minh sống sót khi instance chết. Cuối cùng chạy `docker compose -p k5-day14-scaling down` để trả cổng 8080.

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

| CP | Hỏi AI gì | AI làm gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| CP1 | Tìm anti-pattern trong `01-localhost-vs-production/develop/app.py`, so sánh với `production/` | Claude Code đọc code, chạy 2 bản app (cổng 8101/8111 vì 8000 đang bận), soạn câu trả lời | Số dòng đối chiếu bằng `cat -n`; output curl và log server là kết quả chạy thật |
| CP2 | Trả lời câu hỏi Dockerfile, đo kích thước image, chạy stack Nginx | Claude Code build image develop/advanced, chạy container (cổng 8102) và compose `-p k5-day14-docker` | Kích thước lấy từ `docker images` (1.67GB → 240MB); curl qua Nginx trả 200 |
| CP3 | Test 401/200/429, giải thích JWT, rate limit, cost guard | Claude Code chạy `04-api-gateway` (cổng 8103), vòng lặp curl tới 429, đọc `cost_guard.py` | Output `curl -i` thật, token đã che; dòng code được trích đúng file |
| CP4 | Health/readiness, SIGTERM, scale 3 instance | Claude Code chạy app develop (cổng 8104), gửi SIGTERM khi đang có request, chạy compose `--scale agent=3` + `test_stateless.py` | Request vẫn 200 sau SIGTERM; 3 instance luân phiên; history giữ nguyên qua Redis |
| CP5 | Hoàn thành các TODO trong `06-lab-complete/` | Claude Code viết `config.py`, `auth.py`, `redis_client.py`, `rate_limiter.py` (sorted set Redis), `cost_guard.py` (counter Redis theo ngày), `main.py` (log JSON, `/health`, `/ready`, shutdown), Dockerfile multi-stage non-root, compose, `railway.toml`, `render.yaml` | Chạy `check_production_ready.py` bản đầy đủ (có Docker) → `PASS 12/12`, 43/43 checks; không sửa script chấm |
| CP6 | Deploy agent Part 6 lên Railway, viết DEPLOYMENT.md, so sánh railway.toml/render.yaml, đọc pipeline Cloud Run | Claude Code chạy Railway CLI (`init`, `add --database redis`, `add --service agent` với biến môi trường, `up`, `domain`), sinh `AGENT_API_KEY` ngẫu nhiên lưu ngoài repo, chụp `running.png`/`test.png` từ output thật bằng Chrome headless | 4 lệnh CP6 trả 200/200/401/200; `check_production_ready.py --public-url` báo Public URL ✅; quét repo không chứa key |

Ghi chú: cổng 8000 trên máy đang bị một process khác dùng nên các bài Part 1–5 chạy ở cổng khác (đã ghi rõ trong từng mục). Docker Hub có lúc trả 429 khi pull image, đã retry.
