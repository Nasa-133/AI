"""Replay CLI (runbook: docs/runbooks/replay.md). Servis venv’ida ishga tushiriladi.

  # outbox: oynadagi eventlarni qayta yuborish (consumer’lar dedup qiladi)
  uv run python tools/ops/replay.py outbox --db "$BUSINESS_MIGRATIONS_DATABASE_URL" \\
      --since "2026-09-28 10:00+05" [--until ...] [--type AgentRunCompleted.v1] [--tenant UUID]
  # DLQ: sabab tuzatilgach xabarlarni shu consumer navbatiga qaytarish
  uv run python tools/ops/replay.py dlq --amqp "$AMQP_URL" --queue business.workspace [--limit 100]

Vaqt DB soati bilan solishtiriladi — oynani `SELECT now()` natijasiga nisbatan tanlang.
"""

import argparse
import asyncio
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from abo_messaging import replay_outbox
from abo_messaging.rabbit import connect
from abo_messaging.replay import requeue_dlq


async def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("outbox")
    o.add_argument("--db", required=True)
    o.add_argument("--since", required=True, type=datetime.fromisoformat)
    o.add_argument("--until", type=datetime.fromisoformat)
    o.add_argument("--type", action="append", dest="types")
    o.add_argument("--tenant", type=UUID)
    d = sub.add_parser("dlq")
    d.add_argument("--amqp", required=True)
    d.add_argument("--queue", required=True)
    d.add_argument("--limit", type=int, default=1000)
    a = p.parse_args()
    if a.cmd == "outbox":
        engine = create_async_engine(a.db)
        n = await replay_outbox(engine, since=a.since, until=a.until, event_types=a.types,
                                tenant_id=a.tenant)
        await engine.dispose()
        print(f"Qayta yuborishga belgilandi: {n} ta xabar (relay keyingi siklda yuboradi)")
    else:
        connection = await connect(a.amqp)
        n = await requeue_dlq(connection, a.queue, limit=a.limit)
        await connection.close()
        print(f"{a.queue}.dlq → {a.queue}: {n} ta xabar qaytarildi")


if __name__ == "__main__":
    asyncio.run(main())
