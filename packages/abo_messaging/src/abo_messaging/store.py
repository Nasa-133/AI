"""Outbox va inbox jadvallari shakli.

Jadvallarni har servis o‘z migratsiyasida yaratadi (DDL shu shaklga mos bo‘lishi shart,
`OUTBOX_INBOX_DDL` namuna sifatida). Kutubxona faqat so‘rov yozadi, jadvalga egalik qilmaydi.
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

OUTBOX_INBOX_DDL = """
CREATE SCHEMA messaging;
CREATE TABLE messaging.outbox (
    id bigserial PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    event_type text NOT NULL,
    routing_key text NOT NULL,
    tenant_id uuid NOT NULL,
    envelope jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    failed_at timestamptz,
    last_error text
);
CREATE INDEX outbox_pending_idx ON messaging.outbox (next_attempt_at, id)
    WHERE sent_at IS NULL AND failed_at IS NULL;
CREATE TABLE messaging.inbox (
    event_id uuid NOT NULL,
    consumer text NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer)
);
"""


def make_tables(schema: str = "messaging") -> tuple[Table, Table]:
    metadata = MetaData(schema=schema)
    outbox = Table(
        "outbox",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("event_id", Uuid, nullable=False, unique=True),
        Column("event_type", Text, nullable=False),
        Column("routing_key", Text, nullable=False),
        Column("tenant_id", Uuid, nullable=False),
        Column("envelope", JSONB, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("attempts", Integer, nullable=False),
        Column("next_attempt_at", DateTime(timezone=True), nullable=False),
        Column("sent_at", DateTime(timezone=True)),
        Column("failed_at", DateTime(timezone=True)),
        Column("last_error", Text),
    )
    inbox = Table(
        "inbox",
        metadata,
        Column("event_id", Uuid, nullable=False),
        Column("consumer", Text, nullable=False),
        Column("processed_at", DateTime(timezone=True), nullable=False),
        PrimaryKeyConstraint("event_id", "consumer"),
    )
    return outbox, inbox
