"""Transport-only messaging: envelope, transactional outbox, inbox dedup, RabbitMQ.

Biznes mantiqi, domain modeli yoki umumiy jadval yo‘q (ADR 004). Har servis o‘z
outbox/inbox jadvallariga o‘z bazasida egalik qiladi.
"""

from .envelope import Envelope, InvalidEnvelope, new_envelope
from .inbox import Handler, InboxProcessor, Outcome, PermanentError
from .outbox import OutboxRelay, Publisher, RelayStats, enqueue
from .replay import replay_outbox

__all__ = [
    "Envelope",
    "Handler",
    "InboxProcessor",
    "InvalidEnvelope",
    "OutboxRelay",
    "Outcome",
    "PermanentError",
    "Publisher",
    "RelayStats",
    "enqueue",
    "new_envelope",
    "replay_outbox",
]
