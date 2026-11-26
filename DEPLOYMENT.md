# Deployment Information

## Public URL
https://agent-production-4fa29d22.up.railway.app

## Platform
Railway (project `k5-day14-agent`, environment `production`, region `iad`).
Deploy thư mục `06-lab-complete/` bằng `railway up` — build từ `Dockerfile` theo `06-lab-complete/railway.toml`
(`builder = "DOCKERFILE"`, `healthcheckPath = "/health"`). Redis là service `Redis` (Railway database) trong cùng project,
agent nối tới qua private network (`redis.railway.internal`).

## Các lệnh đã chạy

```bash
cd 06-lab-complete
railway init --name k5-day14-agent
railway add --database redis
railway add --service agent \
  --variables "AGENT_API_KEY=<random 32 byte>" \
  --variables 'REDIS_URL=${{Redis.REDIS_URL}}' \
  --variables "ENVIRONMENT=production"
railway up --service agent --ci
railway domain --service agent
```

## Test Commands

Chạy với `BASE=https://agent-production-4fa29d22.up.railway.app` và `AGENT_API_KEY` là key đã đặt trên Railway
(mỗi lệnh chỉ in mã HTTP, không lộ key). Kết quả đo ngày 2026-11-26 08:52 UTC:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

### Health Check
```bash
curl https://agent-production-4fa29d22.up.railway.app/health
# {"status":"ok"}
curl https://agent-production-4fa29d22.up.railway.app/ready
# {"status":"ready"}
```

### API Test (with authentication)
```bash
curl -X POST https://agent-production-4fa29d22.up.railway.app/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deployment?"}'
# {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."}
```

`python check_production_ready.py --public-url https://agent-production-4fa29d22.up.railway.app` →
`✅ Public URL: GET https://agent-production-4fa29d22.up.railway.app/health → 200`.

## Environment Variables Set

Đặt trên Railway (service `agent` → Variables), **không** ghi trong code hay commit vào repo:

| Biến | Giá trị | Ghi chú |
| --- | --- | --- |
| `AGENT_API_KEY` | chuỗi ngẫu nhiên 32 byte (`secrets.token_urlsafe`) | secret, chỉ có trên Railway |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | tham chiếu biến của service Redis, Railway tự điền |
| `ENVIRONMENT` | `production` | |
| `PORT` | do Railway cấp | app đọc `${PORT:-8000}` trong `CMD` |

`RATE_LIMIT_PER_MINUTE` và `DAILY_BUDGET_USD` dùng giá trị mặc định trong `app/config.py` (10 req/phút, 1.0 USD/ngày).

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png) — `railway status`, `railway deployment list`, `/health`, `/ready`, log JSON trên Railway
- [Test results](screenshots/test.png) — 4 lệnh tự kiểm CP6: 200 / 200 / 401 / 200
