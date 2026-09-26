"""RabbitMQ topologiyasi: bitta topic exchange, har consumer uchun queue + retry + DLQ.

    abo (topic) --event_type--> <consumer>            (asosiy navbat)
    <consumer> xatosi        --> <consumer>.retry      (TTL, keyin abo.retry orqali qaytadi)
    doimiy xato/limit        --> <consumer>.dlq        (qo‘lda ko‘rib chiqish, replay)
"""

import asyncio
import logging
from dataclasses import dataclass

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractRobustConnection,
)

from .inbox import InboxProcessor, Outcome

logger = logging.getLogger(__name__)

EXCHANGE = "abo"
RETRY_EXCHANGE = "abo.retry"
ATTEMPT_HEADER = "x-abo-attempt"


class RabbitPublisher:
    """Publisher confirm bilan: `publish` broker xabarni qabul qilgandagina qaytadi."""

    def __init__(self, connection: AbstractRobustConnection) -> None:
        self._connection = connection
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> AbstractExchange:
        async with self._lock:
            if self._exchange is None or self._channel is None or self._channel.is_closed:
                self._channel = await self._connection.channel(publisher_confirms=True)
                self._exchange = await self._channel.declare_exchange(
                    EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
                )
            return self._exchange

    async def publish(self, *, routing_key: str, body: bytes, message_id: str) -> None:
        exchange = await self._ensure()
        await exchange.publish(
            aio_pika.Message(body=body, message_id=message_id, content_type="application/json",
                             delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=routing_key,
            mandatory=False,
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_ms: int = 1_000
    max_delay_ms: int = 60_000

    def delay_ms(self, attempt: int) -> int:
        delay: int = self.base_delay_ms * (2 ** (attempt - 1))
        return min(delay, self.max_delay_ms)


class RabbitConsumer:
    def __init__(
        self,
        connection: AbstractRobustConnection,
        processor: InboxProcessor,
        *,
        queue: str,
        retry: RetryPolicy | None = None,
        prefetch: int = 10,
    ) -> None:
        self._connection = connection
        self._processor = processor
        self._queue_name = queue
        self._retry = retry or RetryPolicy()
        self._prefetch = prefetch
        self._channel: AbstractChannel | None = None

    async def declare(self) -> None:
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=self._prefetch)
        self._channel = channel
        main = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
        retry_back = await channel.declare_exchange(RETRY_EXCHANGE, aio_pika.ExchangeType.DIRECT,
                                                    durable=True)
        queue = await channel.declare_queue(self._queue_name, durable=True)
        for event_type in self._processor.event_types:
            await queue.bind(main, routing_key=event_type)
        # Retry navbatidan TTL tugagach xabar asosiy navbatga qaytadi.
        await queue.bind(retry_back, routing_key=self._queue_name)
        await channel.declare_queue(
            f"{self._queue_name}.retry",
            durable=True,
            arguments={"x-dead-letter-exchange": RETRY_EXCHANGE,
                       "x-dead-letter-routing-key": self._queue_name},
        )
        await channel.declare_queue(f"{self._queue_name}.dlq", durable=True)

    async def start(self) -> None:
        if self._channel is None:
            await self.declare()
        assert self._channel is not None
        queue = await self._channel.get_queue(self._queue_name)
        await queue.consume(self._on_message)

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        raw_attempt = (message.headers or {}).get(ATTEMPT_HEADER, 1)
        attempt = raw_attempt if isinstance(raw_attempt, int) else 1
        outcome = await self._processor.process(message.body, attempt=attempt,
                                                max_attempts=self._retry.max_attempts)
        if outcome is Outcome.RETRY:
            await self._republish(message, f"{self._queue_name}.retry", attempt + 1,
                                  expiration_ms=self._retry.delay_ms(attempt))
        elif outcome is Outcome.DEAD:
            await self._republish(message, f"{self._queue_name}.dlq", attempt)
        # Qayta yo‘naltirish tasdiqlangandan keyingina asl xabar ack qilinadi.
        await message.ack()

    async def _republish(self, message: AbstractIncomingMessage, queue: str, attempt: int,
                         *, expiration_ms: int | None = None) -> None:
        assert self._channel is not None
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=message.body,
                message_id=message.message_id,
                content_type=message.content_type,
                headers={**(message.headers or {}), ATTEMPT_HEADER: attempt},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                expiration=(expiration_ms / 1000) if expiration_ms else None,
            ),
            routing_key=queue,
        )


async def connect(url: str) -> AbstractRobustConnection:
    return await aio_pika.connect_robust(url)
