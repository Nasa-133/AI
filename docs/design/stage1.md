# Bosqich 1 — analitika vertikal kesimi: dizayn qarorlari

Maqsad oqimi: CSV yuklash → mapping tasdiqlash → canonical batch → Core ingestion va snapshot → chat savoli → AI tool loop → deterministik hisob → manbali javob → dashboard.

Kontraktlar manbasi `contracts/`. Bu hujjat ular orasidagi bog‘lovchi qarorlarni yozadi.

## 1. Kim nimaga egalik qiladi

| Runtime | Egaligi | Bilmaydi |
|---|---|---|
| Business Core | Yuklangan fayllar, data source proyeksiyasi, canonical → metrika sozlamalari, ingestion/karantin, snapshot, query, dashboard, task, SSE, Tool API, capability | Vendor formatlari, model provayderi |
| Integration Runtime | Connector’lar, manba → canonical mapping (versiyali), sync run, raw va canonical batch fayllari | Metrikalar, AI, Core DB |
| AI Runtime | AgentRun, checkpoint, model bilan suhbat holati, prompt versiyalari, tool loop | Core DB, ERP, ruxsat qarori |

## 2. Object storage (lokalda SeaweedFS, S3 API)

| Bucket | Egasi | Kalit shabloni |
|---|---|---|
| `abo-business` | Core | `uploads/{tenant_id}/{upload_id}/{fayl_nomi}` |
| `abo-integration` | Integration | `raw/{tenant_id}/{data_source_id}/{sync_run_id}/{fayl}`, `canonical/{tenant_id}/{data_source_id}/{sync_run_id}/{entity}.jsonl` |

- Canonical batch — UTF-8 JSON Lines, har satr bitta canonical record (`contracts/canonical/...`), satrlar tartibi manbadagi tartib.
- `checksum_sha256` — obyekt baytlarining SHA-256 hex’i. O‘quvchi yuklab olgach tekshiradi; mos kelmasa — doimiy xato.
- P0 lokal: bitta S3 foydalanuvchisi (`abo`). Production: har runtime o‘z credential’i; Integration’ga `abo-business/uploads/` faqat o‘qish, Core’ga `abo-integration/canonical/` faqat o‘qish.

Sozlamalar (har servis o‘z prefiksi bilan): `*_S3_ENDPOINT_URL` (lokal `http://localhost:9000`), `*_S3_ACCESS_KEY`, `*_S3_SECRET_KEY`, `*_S3_REGION` (`us-east-1`).

## 3. Broker navbatlari

Exchange `abo` (topic), routing key = `event_type` (ADR 004).

| Navbat (consumer) | Qabul qiladi |
|---|---|
| `business.analytics` | `SourceBatchReady.v1`, `SyncRunCompleted.v1`, `SyncRunFailed.v1`, `SchemaDiscovered.v1`, `SourceConfigured.v1` |
| `business.workspace` | `AgentRunProgressed.v1`, `AgentRunCompleted.v1` |
| `integration_runtime.sync` | `DiscoverSchema.v1`, `ConfigureSource.v1`, `SyncSource.v1` |
| `ai_runtime.agent` | `RunAgent.v1`, `CancelAgentRun.v1` |

`amqp` sozlamasi: `*_AMQP_URL` (lokal `amqp://abo:abo_dev@localhost:5672/`).

Har runtime o‘z DB’sida `messaging.outbox/inbox` (ADR 004 DDL), tenant jadvallarida `tenant_id` va FORCE RLS (`platform.current_tenant_id()` naqshi, Business 0001 migratsiyasidagi kabi). Consumer tranzaksiyasi boshida envelope’dagi `tenant_id` bilan kontekst bog‘lanadi (`InboxProcessor(on_transaction_start=...)`).

## 4. Manba → canonical mapping (Integration)

1. Core `DiscoverSchema.v1` yuboradi (fayl `object_ref` bilan).
2. Integration fayl sarlavhasi va ≤5 namunaviy satrni o‘qiydi, har canonical entity uchun sarlavhalar mosligi bo‘yicha `match_score` va `suggested_mapping` beradi (`SchemaDiscovered.v1`). Tanish sarlavhalar (sintetik ERP eksporti) uchun shablonlar bor; noma’lum ustun taxmin qilinmaydi — `unmapped_required_fields`.
3. Foydalanuvchi Core’da mapping’ni ko‘radi/tuzatadi va tasdiqlaydi → Core `ConfigureSource.v1` (yangi `mapping_version`) → Integration saqlaydi va `SourceConfigured.v1` qaytaradi.
4. Core `SyncSource.v1(mapping_version)` yuboradi. Integration faqat shu tasdiqlangan versiya bilan ishlaydi; versiya topilmasa — `SyncRunFailed`.

Transformlar (`contracts/events/SchemaDiscovered.v1.json`):

| transform | Ma’nosi |
|---|---|
| `text` | Bo‘sh joy chetlari olinadi; bo‘sh qator — required maydon uchun xato |
| `decimal` | `^-?\d+(\.\d+)?$`; vergul yoki bo‘sh — satr rad etiladi |
| `decimal_or_null` | Bo‘sh → `null` |
| `datetime_tz` | ISO 8601 va offset majburiy; offsetsiz — rad etiladi |
| `date` | `YYYY-MM-DD` |
| `status_map` | `config.status_map` bo‘yicha; topilmasa rad etiladi |
| `const` | `constant` JSON qiymati (`"false"` → false) |

Normallashtirib bo‘lmaydigan satr **rad etiladi** (Integration): raw’da qoladi, `SyncRunCompleted.rejected_count` va namunalarda ko‘rinadi, batch’ga kirmaydi.

## 5. Core ingestion va karantin (Analytics)

- `SourceBatchReady` → faylni o‘qish, checksum, har satrni canonical schema bo‘yicha tekshirish.
- Semantik karantin (Core): bitta batch ichida takrorlangan `source_id` (barcha nusxalari), sotuvda `quantity ≤ 0`, noma’lum valyuta kodi. Karantin satrlari saqlanadi va sababi bilan ko‘rsatiladi, agregatga kirmaydi.
- `is_full_snapshot=true`: batch’da yo‘q oldingi satrlar yangi snapshot’da yopiladi (o‘chirilgan).
- Satr versiyalash: `valid_from_seq` / `valid_to_seq`. Snapshot `S` so‘rovi: `valid_from_seq ≤ S AND (valid_to_seq IS NULL OR valid_to_seq > S)`. O‘zgarmagan satr qayta yozilmaydi.
- Yakunda `DatasetSnapshotPublished.v1`.
- Metrika qoidalari sintetik generator README’sidagi kelishuvga mos (faqat `confirmed`, qaytarish tannarxi ayriladi, tannarx yo‘q satrlar `cogs_missing_rows`).

## 6. Tool API (AI → Core)

- `POST /internal/v1/tools/{name}`; sxemalar `contracts/tools/`.
- `Authorization: Bearer <BUSINESS_TOOLS_SERVICE_TOKEN>` — servis identifikatori (AI tomonda `AI_BUSINESS_TOOLS_TOKEN`).
- `X-ABO-Capability: <RunAgent.capability_token>` — Core imzolagan: `v1.<base64url(JSON)>.<base64url(HMAC-SHA256)>`, JSON: `task_id, tenant_id, user_id, role_key, tools[], exp`. AI uchun shaffof emas.
- Core har chaqiriqda: token imzosi va muddati, a’zolik va rol (joriy, DB’dan), tool rolga ruxsatliligi, argument schema. Biznes xatosi — HTTP 200 + `status=error`; auth xatosi — 401/403.
- `tool_call_id` idempotentlik kaliti: bir xil `(task_id, tool_call_id)` qayta kelsa saqlangan natija qaytadi (`create_dashboard` ikki marta yaratilmaydi).
- AI’dagi sozlama: `AI_BUSINESS_TOOLS_URL` (lokal `http://localhost:8000`).

## 7. AI run modeli

- `RunAgent` handler faqat `agent_runs` satrini yaratadi (tez tranzaksiya). Alohida runner `FOR UPDATE SKIP LOCKED` + `lease_expires_at` bilan run’ni oladi, har tool chaqiruvidan keyin checkpoint yozadi. Worker yiqilsa lease tugaydi va boshqa worker checkpoint’dan davom etadi.
- Limitlar: 20 tool chaqiruvi, `deadline`. Bekor qilinsa (`CancelAgentRun`) yangi qadam boshlanmaydi.
- `ModelProvider` port: `FakeProvider` (deterministik, o‘zbekcha kalit so‘zlar bo‘yicha reja, testlar va demo uchun) va `OpenAIResponsesProvider` (`store=false`, strict function tools, `reasoning.encrypted_content`). `AI_MODEL_PROVIDER=fake|openai`. Kalit yo‘q bo‘lsa real rejim “tekshirilmagan” deb belgilanadi, fake’ga yashirin o‘tish yo‘q.
- Javobdagi har raqam tool natijasidan olinadi; javob formati TZ 7.3; `source_refs` tool natijalaridan yig‘iladi.
