"""Redis fixed-window rate limiter.

Redis ishlamasa so‘rov o‘tkaziladi (fail-open) va logga yoziladi: login uchun
DB darajasidagi lockout baribir himoya qiladi.
"""

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    def __init__(self, url: str, *, prefix: str = "abo:rl:") -> None:
        self._redis = Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self._prefix = prefix

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        full_key = f"{self._prefix}{key}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(full_key)
                pipe.expire(full_key, window_seconds, nx=True)
                count, _ = await pipe.execute()
        except RedisError:
            logger.warning("Rate limiter mavjud emas, so‘rov o‘tkazildi", exc_info=True)
            return True
        return int(count) <= limit

    async def close(self) -> None:
        await self._redis.aclose()


class NoopRateLimiter:
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        return True
