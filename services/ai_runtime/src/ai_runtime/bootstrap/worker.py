"""AI Runtime worker: `ai_runtime.agent` consumer, run runner’lari va outbox relay.

Ishga tushirish: `python -m ai_runtime.bootstrap.worker`. SIGTERM’da joriy qadam
checkpoint’da qoladi; lease tugagach boshqa worker davom ettiradi.
"""

import asyncio
import logging
import signal

from abo_messaging import InboxProcessor, OutboxRelay
from abo_messaging.rabbit import RabbitConsumer, RabbitPublisher, connect

from ..adapters.handlers import (
    EMBEDDINGS_QUEUE,
    QUEUE,
    bind_envelope_tenant,
    make_embedding_handlers,
    make_handlers,
)
from ..entrypoints.worker import serve
from .container import build_container, make_runner
from .settings import Settings

logger = logging.getLogger("ai_runtime.worker")


async def run(settings: Settings) -> None:
    container = build_container(settings)
    connection = await connect(settings.amqp_url)
    processor = InboxProcessor(container.engine, consumer=QUEUE,
                               handlers=make_handlers(max_tool_calls=settings.max_tool_calls),
                               on_transaction_start=bind_envelope_tenant)
    await RabbitConsumer(connection, processor, queue=QUEUE).start()
    await container.objects.ensure_bucket(settings.vectors_bucket)
    embeddings = InboxProcessor(
        container.engine, consumer=EMBEDDINGS_QUEUE,
        handlers=make_embedding_handlers(store=container.objects, provider=container.embedder,
                                         bucket=settings.vectors_bucket),
        on_transaction_start=bind_envelope_tenant)
    await RabbitConsumer(connection, embeddings, queue=EMBEDDINGS_QUEUE).start()
    relay = OutboxRelay(container.engine, RabbitPublisher(connection))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    logger.info("AI Runtime worker ishga tushdi (provider=%s)", container.provider.name)
    try:
        runners = [make_runner(container) for _ in range(settings.runner_concurrency)]
        await serve(stop, relay.run_forever(stop), runners)
    finally:
        await connection.close()
        await container.tools.aclose()
        await container.engine.dispose()
        logger.info("AI Runtime worker to‘xtadi")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings()))


if __name__ == "__main__":
    main()
