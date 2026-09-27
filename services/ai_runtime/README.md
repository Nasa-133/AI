# AI Runtime

Model chaqirig‘i va agent tool loop (TZ 10, 11, 13.9). Biznes ma’lumotini faqat Core Tool API orqali oladi; Core DB’ga va ERP’ga kirmaydi.

## Oqim

`RunAgent.v1` (navbat `ai_runtime.agent`) → `agent.agent_runs` + `agent.run_queue` → runner lease bilan oladi → model ↔ Tool API sikli (har qadamdan keyin checkpoint) → outbox: `AgentRunProgressed.v1`, `AgentRunCompleted.v1`. `CancelAgentRun.v1` keyingi qadamdan oldin to‘xtatadi.

## Qarorlar

- **Tenant izolyatsiyasi.** `agent_runs` FORCE RLS ostida. Runner tenantlar bo‘ylab ish olishi uchun `run_queue` ishlatiladi: unda faqat `run_id`, `tenant_id` va lease maydonlari bor (matn, token, checkpoint yo‘q), shuning uchun RLS’siz. Run’ni olgach runner tenant kontekstini bog‘laydi va satrni RLS ostida o‘qiydi. SECURITY DEFINER funksiya kerak bo‘lmadi.
- **Crash recovery.** Lease tugasa boshqa worker checkpoint’dan davom etadi: tugallangan tool chaqiruvlari takrorlanmaydi; chala chaqiruv o‘sha `tool_call_id` bilan qayta yuboriladi (Core dedup qiladi). Eski worker yozishga urinsa `LeaseLost`.
- **capability_token** `agent_runs` ustunida ochiq saqlanadi, logga yozilmaydi va eventlarga kirmaydi. Qisqa muddatli (Core `exp`), lekin DB darajasida shifrlash hali yo‘q.
- **Provayder.** `AI_MODEL_PROVIDER=fake|openai`. OpenAI sozlanmagan bo‘lsa worker ishga tushmaydi; fake’ga yashirin o‘tish yo‘q.
- **Tool schema’lari** `contracts/tools/*.args.v1.json` nusxasi (`adapters/tool_schemas/`), mosligi test bilan tekshiriladi.

## Sozlamalar (`AI_` prefiks)

`DATABASE_URL`, `MIGRATIONS_DATABASE_URL`, `AMQP_URL`, `BUSINESS_TOOLS_URL`, `BUSINESS_TOOLS_TOKEN`, `MODEL_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL_MAIN`, `OPENAI_MODEL_FAST`, `MAX_TOOL_CALLS` (20), `LEASE_SECONDS` (60), `RUNNER_CONCURRENCY` (4).

## Buyruqlar

```bash
uv run alembic upgrade head             # ai_owner bilan
uv run python -m ai_runtime.bootstrap.worker
uv run pytest -q                        # integration: Postgres kerak
```

## Cheklovlar

- **OpenAI adapteri faqat mock klient bilan testlangan.** Haqiqiy API bilan (strict function schema’lar qabul qilinishi, `reasoning.encrypted_content` aylanishi, refusal/incomplete) kalit berilgunga qadar tekshirilmagan.
- `FakeProvider` qoidaga asoslangan: o‘zbek (lotin) tilidagi analitik so‘rovlar uchun; haqiqiy modelni almashtirmaydi.
- `OPENAI_MODEL_FAST` hali ishlatilmaydi (niyatni tasniflash keyin).
- `cost_estimate` hozircha `"0"`: narxlar konfiguratsiyasi Governance bilan keyin.
