"""Business Worker: outbox relay va broker consumer’lari.

Ishga tushirish: `python -m business.entrypoints.worker`.
SIGTERM’da joriy iteratsiya tugaydi; commit qilinmagan outbox yozuvlari qayta yuboriladi.
"""

import asyncio
import logging
import signal

from abo_messaging import InboxProcessor, OutboxRelay
from abo_messaging.rabbit import RabbitConsumer, RabbitPublisher, connect

from business.bootstrap.container import build_container
from business.bootstrap.settings import Settings

from .consumers import ANALYTICS_QUEUE, DOCUMENTS_QUEUE, WORKSPACE_QUEUE, Consumers

logger = logging.getLogger("business.worker")


async def run(settings: Settings) -> None:
    container = build_container(settings)
    await container.storage.ensure_bucket(settings.uploads_bucket)
    engine = container.engine
    connection = await connect(settings.amqp_url)
    consumers = Consumers(container)
    for queue, routes in ((ANALYTICS_QUEUE, consumers.analytics_routes()),
                          (WORKSPACE_QUEUE, consumers.workspace_routes()),
                          (DOCUMENTS_QUEUE, consumers.documents_routes())):
        processor = InboxProcessor(engine, consumer=queue, handlers=routes,
                                   on_transaction_start=consumers.bind)
        await RabbitConsumer(connection, processor, queue=queue).start()
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
