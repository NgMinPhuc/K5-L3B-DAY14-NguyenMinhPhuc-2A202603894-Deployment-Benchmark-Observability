"""
Production AI Agent — Part 6 Final Project.
Kiểm tra: python check_production_ready.py
"""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ── Structured logging: mỗi dòng log là một JSON object ──
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))   # field bổ sung (path, status, ms...)
        if record.exc_info:
            entry["exc"] = record.exc_info[0].__name__  # chỉ tên lỗi, không in stack trace
        return json.dumps(entry, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    # Gắn cho cả logger của uvicorn để log hệ thống cũng là JSON
    for name in ("", "uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.setLevel(logging.INFO)
        lg.propagate = name == ""
    logging.getLogger("uvicorn.access").disabled = True  # đã có log request riêng bên dưới


setup_logging()
logger = logging.getLogger("agent")


def log(event: str, **fields) -> None:
    logger.info(event, extra={"fields": fields})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: không ping Redis để app khởi động được dù Redis chưa sẵn sàng
    log("startup", environment=settings.environment, port=settings.port)
    yield
    # Shutdown (uvicorn nhận SIGTERM): request đang chạy đã xong → đóng kết nối rồi thoát
    log("shutdown")
    r.close()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def request_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log("request", method=request.method, path=request.url.path,
        status=response.status_code, ms=round((time.perf_counter() - start) * 1000, 1))
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Không lộ stack trace cho client; chi tiết nằm trong log
    logger.error("unhandled_error", extra={"fields": {"path": request.url.path, "error": type(exc).__name__}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health():
    """Liveness: process còn sống là 200 — không phụ thuộc Redis."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi Redis kết nối được, nếu không 503."""
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready", "reason": "redis unavailable"})
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)   # 429
    check_budget()              # 402
    answer = llm_ask(body.question)
    # Ước lượng token thô: ~1.3 token / từ
    in_tokens = int(len(body.question.split()) * 1.3) + 1
    out_tokens = int(len(answer.split()) * 1.3) + 1
    cost = record_cost(in_tokens, out_tokens)
    log("ask", input_tokens=in_tokens, output_tokens=out_tokens, cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
