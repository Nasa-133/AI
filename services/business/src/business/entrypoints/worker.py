"""Business Worker: outbox relay va (keyingi bosqichlarda) broker consumer’lari.

Ishga tushirish: `python -m business.entrypoints.worker`.
SIGTERM’da joriy iteratsiya tugaydi; commit qilinmagan outbox yozuvlari qayta yuboriladi.
"""

import asyncio
import logging
import signal

from abo_messaging import OutboxRelay
from abo_messaging.rabbit import RabbitPublisher, connect

from business.bootstrap.settings import Settings
from business.platform.db import make_engine

logger = logging.getLogger("business.worker")


async def run(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    connection = await connect(settings.amqp_url)
    relay = OutboxRelay(engine, RabbitPublisher(connection))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    logger.info("Business worker ishga tushdi")
    try:
        await relay.run_forever(stop)
    finally:
        await connection.close()
        await engine.dispose()
        logger.info("Business worker to‘xtadi")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings()))  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
