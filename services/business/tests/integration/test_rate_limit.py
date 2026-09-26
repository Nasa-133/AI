import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from business.platform.rate_limit import RedisRateLimiter

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("BUSINESS_REDIS_URL", "redis://localhost:56379/0")


async def test_fixed_window_limit() -> None:
    try:
        await Redis.from_url(REDIS_URL).ping()
    except Exception as exc:  # pragma: no cover - muhitga bog‘liq
        pytest.skip(f"Redis tayyor emas: {exc}")
    limiter = RedisRateLimiter(REDIS_URL)
    key = f"test:{uuid4().hex}"
    results = [await limiter.hit(key, limit=3, window_seconds=60) for _ in range(5)]
    assert results == [True, True, True, False, False]
    await limiter.close()


async def test_fails_open_when_redis_is_down() -> None:
    limiter = RedisRateLimiter("redis://localhost:1/0")
    assert await limiter.hit("any", limit=1, window_seconds=60) is True
    await limiter.close()
