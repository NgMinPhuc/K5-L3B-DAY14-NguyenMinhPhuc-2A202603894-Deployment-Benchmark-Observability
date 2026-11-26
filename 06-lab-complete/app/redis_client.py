"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

redis.from_url chỉ tạo client, KHÔNG kết nối ngay — nên app vẫn khởi động được khi Redis chưa sẵn sàng.
"""
import redis

from app.config import settings

# Timeout ngắn để /ready trả 503 nhanh thay vì treo khi Redis mất kết nối
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready: ping được Redis → True, lỗi kết nối → False."""
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
