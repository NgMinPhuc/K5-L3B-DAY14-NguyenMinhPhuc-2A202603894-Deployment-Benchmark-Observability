"""
Rate limiting (tiêu chí 7) — sliding window 60 giây, state nằm trong Redis
nên mọi worker/instance dùng chung và vẫn còn sau khi restart agent.
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Tối đa RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key. Vượt → 429 + Retry-After."""
    redis_key = "rate:" + hashlib.sha256(key.encode()).hexdigest()[:16]  # không lưu key thô
    now = time.time()
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)  # bỏ request ngoài cửa sổ
        pipe.zcard(redis_key)                                       # đếm request còn lại
        _, count = pipe.execute()
        if count >= settings.rate_limit_per_minute:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest[0][1])) + 1) if oldest else WINDOW_SECONDS
            raise HTTPException(status_code=429, detail="Rate limit exceeded",
                                headers={"Retry-After": str(retry_after)})
        pipe = r.pipeline()
        pipe.zadd(redis_key, {f"{now}:{uuid.uuid4().hex[:8]}": now})  # member duy nhất mỗi request
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable (Redis)")
