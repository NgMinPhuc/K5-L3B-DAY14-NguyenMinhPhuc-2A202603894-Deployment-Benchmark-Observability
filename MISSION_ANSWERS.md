# Day 14 Lab - Mission Answers

> K5-L3B · Day 14 · Deployment, Benchmark & Observability

---

## Part 1: Localhost vs Production

_CP1 — pending._

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
