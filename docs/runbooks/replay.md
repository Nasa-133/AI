# Replay: outbox va DLQ

Yetkazish **at-least-once**; har consumer inbox’da `event_id` bo‘yicha dedup qiladi, handler va
inbox belgisi bitta tranzaksiyada (ADR 004). Shuning uchun qayta yuborish takroriy ta’sir
bermaydi — sinov: `packages/abo_messaging/tests/test_outbox_inbox.py::test_replay_*`,
`test_rabbit_e2e.py` (DLQ qaytarish).

## Qachon

| Belgisi | Harakat |
|---|---|
| Broker yo‘qolgan/qayta yaratilgan, xabarlar yo‘qolgan bo‘lishi mumkin | Outbox replay (oyna: hodisa boshlanishidan) |
| Zaxiradan tiklandi | Outbox replay: zaxira nuqtasidan keyin |
| `<navbat>.dlq` da xabarlar (consumer xatosi, noma’lum versiya) | Sababni tuzatish → DLQ replay |
| `messaging.outbox.failed_at` to‘ldirilgan (broker uzoq vaqt yo‘q edi) | Outbox replay (faqat failed ham qo‘shiladi) |

## Tashxis

```sql
-- har runtime bazasida
SELECT event_type, count(*) FILTER (WHERE sent_at IS NULL AND failed_at IS NULL) AS pending,
       count(*) FILTER (WHERE failed_at IS NOT NULL) AS failed, max(created_at)
FROM messaging.outbox GROUP BY 1 ORDER BY 2 DESC;
SELECT now();  -- oyna DB soati bo‘yicha tanlanadi
```

RabbitMQ: management UI yoki `rabbitmqctl list_queues name messages` — `*.dlq` navbatlari.

## Outbox replay

```bash
cd services/business   # yoki ai_runtime / integration_runtime
uv run python ../../tools/ops/replay.py outbox --db "$BUSINESS_MIGRATIONS_DATABASE_URL" \
  --since "2026-09-28 10:00+05" [--until "..."] [--type SourceBatchReady.v1] [--tenant <uuid>]
```

Relay keyingi siklda yuboradi. Tur bo‘yicha filtrlash tavsiya etiladi (masalan, faqat
`AgentRunCompleted.v1`).

## DLQ replay

1. Xabarni ko‘rish (management UI → Get messages): `event_type`, `x-abo-attempt`, xato logi.
2. Sababni tuzatish (kod deploy, konfiguratsiya, kontrakt versiyasi).
3. Qaytarish — faqat shu consumer navbatiga (boshqa consumer’larga qayta tarqatilmaydi):
   ```bash
   uv run python ../../tools/ops/replay.py dlq --amqp "$AMQP_URL" --queue business.workspace --limit 100
   ```
4. DLQ bo‘shaganini va consumer logida xato yo‘qligini tekshirish.

Navbatlar: `business.analytics`, `business.workspace`, `business.documents`,
`ai_runtime.agent`, `ai_runtime.embeddings`, `integration_runtime.sync`.
