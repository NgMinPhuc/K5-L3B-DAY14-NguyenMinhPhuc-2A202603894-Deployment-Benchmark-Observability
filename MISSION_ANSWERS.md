# Day 14 Lab - Mission Answers

> K5-L3B · Day 14 · Deployment, Benchmark & Observability

---

## Part 1: Localhost vs Production

_CP1 — pending._

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
