from typing import Protocol


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """Urinishni hisobga oladi; limit oshgan bo‘lsa False qaytaradi."""
        ...
