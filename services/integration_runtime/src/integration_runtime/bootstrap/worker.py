"""Composition root. Ishga tushirish: `python -m integration_runtime.bootstrap.worker`."""

import asyncio
import logging
import signal
import socket

from abo_messaging import InboxProcessor, OutboxRelay
from abo_messaging.rabbit import RabbitConsumer, RabbitPublisher, connect
from sqlalchemy.ext.asyncio import create_async_engine

from ..adapters.connectors import DemoErpConnector, FileImportConnector
from ..adapters.erp_api import ErpApiConnector
from ..adapters.s3_storage import S3Storage
from ..adapters.sql_uow import SqlUnitOfWorkFactory
from ..application.handlers import CommandHandlers
from ..application.sync_engine import SyncEngine
from ..application.sync_runner import SyncRunner
from ..entrypoints import worker
from ..entrypoints.messages import QUEUE, MessageHandlers
from ..ports.connector import Connector
from .clock import SystemClock
from .settings import Settings


async def main_async(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    storage = S3Storage(endpoint_url=settings.s3_endpoint_url, access_key=settings.s3_access_key,
                        secret_key=settings.s3_secret_key, region=settings.s3_region)
    await storage.ensure_bucket(settings.canonical_bucket)
    connectors: dict[str, Connector] = {"file_import": FileImportConnector(storage)}
    if settings.enable_demo_connector:
        connectors["demo_erp"] = DemoErpConnector(settings.demo_data_dir)
    if settings.erp_api_url:
        connectors["erp_api"] = ErpApiConnector(
            settings.erp_api_url, settings.erp_api_key.get_secret_value(),
            page_size=settings.erp_api_page_size)

    connection = await connect(settings.amqp_url)
    messages = MessageHandlers(CommandHandlers(connectors))
    processor = InboxProcessor(engine, consumer=QUEUE, handlers=messages.routes(),
                               on_transaction_start=messages.on_transaction_start)
    runner = SyncRunner(
        uow_factory=SqlUnitOfWorkFactory(engine), connectors=connectors,
        engine=SyncEngine(storage, bucket=settings.canonical_bucket), clock=SystemClock(),
        owner=f"{settings.worker_id}:{socket.gethostname()}",
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await worker.run(RabbitConsumer(connection, processor, queue=QUEUE), runner,
                         OutboxRelay(engine, RabbitPublisher(connection)), stop)
    finally:
        await connection.close()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async(Settings()))  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
