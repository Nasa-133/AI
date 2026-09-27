"""Worker sikllari (kompozitsiyadan mustaqil): runner loop va umumiy xizmat qilish."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Sequence

from ..application.runner import AgentRunner

logger = logging.getLogger("ai_runtime.worker")


async def runner_loop(runner: AgentRunner, stop: asyncio.Event,
                      idle_interval: float = 0.5) -> None:
    while not stop.is_set():
        try:
            worked = await runner.run_once()
        except Exception:
            logger.exception("Runner iteratsiyasi yiqildi")
            worked = False
        if not worked:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=idle_interval)


async def serve(stop: asyncio.Event, relay_loop: Awaitable[None],
                runners: Sequence[AgentRunner]) -> None:
    await asyncio.gather(relay_loop, *(runner_loop(r, stop) for r in runners))
