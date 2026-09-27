"""Worker sikllari: consumer, sync runner va outbox relay bitta jarayonda."""

import asyncio
import logging

from abo_messaging import OutboxRelay
from abo_messaging.rabbit import RabbitConsumer

from ..application.sync_runner import SyncRunner

logger = logging.getLogger("integration_runtime.worker")


async def runner_loop(runner: SyncRunner, stop: asyncio.Event, *, idle: float = 1.0) -> None:
    while not stop.is_set():
        try:
            worked = await runner.run_once()
        except Exception:
            logger.exception("Sync runner iteratsiyasi yiqildi")
            worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=idle)
            except TimeoutError:
                pass


async def run(consumer: RabbitConsumer, runner: SyncRunner, relay: OutboxRelay,
              stop: asyncio.Event) -> None:
    await consumer.start()
    logger.info("Integration worker ishga tushdi")
    await asyncio.gather(runner_loop(runner, stop), relay.run_forever(stop))
    logger.info("Integration worker to‘xtadi")
