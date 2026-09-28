# AI Business Office — qurish rejasi

Manba: `AI_Business_Office_TZ.md` v1.3. Reja TZ’ning 21-bo‘limidagi ketma-ketlikni ish paketlariga, qabul testlariga va bog‘liqliklarga aylantiradi. Har bosqich oxirida ishlaydigan foydalanuvchi oqimi, testlar va ma’lum cheklovlar topshiriladi; placeholder tayyor deb hisoblanmaydi.

## 1. Texnologik qarorlar (P0)

| Soha | Tanlov | Sabab |
|---|---|---|
| Python | 3.12, `uv` (har servisda o‘z `pyproject.toml` va `uv.lock`) | Tez, deterministik lockfile |
| HTTP | FastAPI + Pydantic v2 | TZ talabi |
| DB | PostgreSQL 16 + pgvector; SQLAlchemy 2 (async, asyncpg); Alembic | RLS, vektor va FTS bitta joyda |
| Broker | RabbitMQ (aio-pika), versionli JSON xabarlar | TZ 13.8; Celery servislar orasida ishlatilmaydi |
| Worker | O‘z consumer’imiz (aio-pika) + outbox relay | Kontrakt Python funksiya nomiga bog‘lanmaydi |
| Storage | S3-mos (lokalda SeaweedFS) | Immutable batch va fayllar |
| Cache | Redis | Rate limit, kesh; source of truth emas |
| Auth | Argon2id (`argon2-cffi`), TOTP (`pyotp`), server-side sessiya + httpOnly cookie | TZ 3-bo‘lim |
| Sifat | ruff, mypy (strict domain/application), pytest, import-linter | 13.15 gate’lari |
| Frontend | Next.js + TypeScript, `openapi-typescript` generated client, TanStack Query, ECharts | TZ 13.2 |
| LLM | OpenAI Responses API — faqat AI Runtime’da, `ModelProvider` port + `FakeProvider` | ADR 008 |
| Lokal muhit | Docker Compose (`infra/compose`) | 4 servis + platforma |
| CI | GitHub Actions: har servis alohida job | 13.15 |

## 2. Bosqichlar

Taxminiy muddat 3–4 kishilik jamoa uchun (2 backend, 1 frontend, 0.5 DevOps/QA). Bitta dasturchi + LLM bilan ~2 barobar uzoqroq.

### Bosqich 0 — Poydevor (2–3 hafta)

Maqsad: chegaralari CI’da tekshiriladigan bo‘sh, lekin ishlaydigan skelet.

| # | Ish paketi | Natija |
|---|---|---|
| 0.1 | Monorepo, `infra/compose` (Postgres+pgvector, RabbitMQ, Redis, MinIO), 3 ta logical DB va alohida credential | `make up` bilan platforma ko‘tariladi |
| 0.2 | Business Core, AI Runtime, Integration Runtime skeletlari: hexagonal qatlamlar, bootstrap, health/readiness | Har servis alohida ishga tushadi va testlanadi |
| 0.3 | Arxitektura testlari: import-linter (domain → framework taqiqi, kontekstlar orasidagi private import taqiqi, servislar orasidagi import taqiqi) | Qoidani buzgan PR CI’da yiqiladi |
| 0.4 | Identity & Access: tenant, user, membership, rol; onboarding, login/logout, sessiya, `/me`, korxona almashtirish; MFA | TZ 3-bo‘lim auth talablari |
| 0.5 | Tenant izolyatsiyasi: RLS (FORCE), transaction-local `app.tenant_id`, owner bo‘lmagan app role | S01 testining DB qismi |
| 0.6 | Kontraktlar: event envelope, command/event JSON Schema, OpenAPI eksport va baseline diff | `contracts/` CI’da tekshiriladi |
| 0.7 | Outbox/inbox kutubxonasi har runtime uchun (umumiy kod emas — har servisda o‘z implementatsiyasi yoki faqat transport tiplari) | Relay, dedup, retry, DLQ testlari |
| 0.8 | Sintetik ma’lumot generatori (savdo, qaytarish, ombor, qarzdorlik; 1 mln tranzaksiyagacha) | Keyingi bosqichlar uchun fixture |
| 0.9 | CI: lint, type, test, arch, contract, secret scan | Yashil pipeline |

Qabul: 13.15 gate 1, 2, 10; S01 (DB darajasi); login oqimi end-to-end.

### Bosqich 1 — Analitika vertikal kesimi (3–4 hafta)

Maqsad: CSV → tasdiqlangan metrika → chat savoli → deterministik hisob → manbali javob → dashboard.

| # | Ish paketi |
|---|---|
| 1.1 | `POST /uploads` (purpose=`dataset_import`), MinIO, hajm/MIME tekshiruvi |
| 1.2 | Integration Runtime: Sync Engine, Connector Protocol, `file_import` va `demo_erp` connectorlari, canonical `sales.*`, `inventory.*`, `finance.receivable` v1 |
| 1.3 | Core Analytics ingestion: `SourceBatchReady` → validatsiya, dedup, karantin → `DatasetSnapshot` → `DatasetSnapshotPublished` |
| 1.4 | Semantik qatlam: metrika lug‘ati (7.1), mapping tasdiqlash API, query builder (parametrli SQL), Decimal/timezone qoidalari |
| 1.5 | Tool API: `list_available_metrics`, `run_metric_query`, `compare_periods`, `explain_contributions`, `create_dashboard`; delegated capability |
| 1.6 | AI Runtime: `RunAgent` consumer, tool loop, `FakeProvider` (deterministik), OpenAI adapteri, strict schema’lar, checkpoint |
| 1.7 | Workspace: conversation/message/task/TaskStep, `202 task_id`, SSE (persistent sequence, `Last-Event-ID`) |
| 1.8 | Dashboards: `DashboardSpec` validatsiyasi, saqlash, versiya, preview, CSV eksport |

Qabul: A01–A07, A04 (chat va dashboard bir xil raqam), I01, I02, I04, T02, T04.

### Bosqich 2 — Web ilova (Bosqich 1 bilan parallel, 3–4 hafta)

| # | Ish paketi |
|---|---|
| 2.1 | Next.js skeleti, generated API client, auth sahifalari, korxona almashtirish |
| 2.2 | Layout: chap navigatsiya, markaz, o‘ng chat; mobil variant |
| 2.3 | Chat: `@agent`, fayl biriktirish, context chip, vazifa kartasi, SSE, xato holatlari |
| 2.4 | Dashboard doskasi, tanlash oynasi, tafsilot oynasi, drill-down, breadcrumb, view-state |
| 2.5 | Mapping tasdiqlash ekrani va import holati |

Qabul: U02–U07.

### Bosqich 3 — Hujjatlar (3 hafta)

Upload (purpose=`document`) → skaner → parse (PDF/DOCX/TXT) → chunk → `GenerateEmbeddings` → pgvector + o‘zbekcha FTS normalizatori → `search_documents`/`read_document_section` → DOCX patch/draft/diff/promote (409).

Qabul: D01–D06, S03.

### Bosqich 4 — Virtual ofis (2 hafta)

Ofis sahnasi (DOM/SVG), agent kartalari, holat mapping’i (6-bo‘lim), parallel limit va navbat, reduced-motion, klaviatura.

Qabul: T01, U01.

### Bosqich 5 — Ishonchlilik va boshqaruv (2–3 hafta)

Retry/backoff, cancel (`CancelAgentRun`), budget rezervi va limitlar, o‘chirish lifecycle’i, audit, psevdonimlash filtri, failure/degradation testlari, network policy.

Qabul: T03, T05, I03, I05, I06, S02; 13.15 gate 5–8.

### Bosqich 6 — P0 qabul (1–2 hafta)

Real OpenAI tekshiruvi, eval to‘plami (40/20/10/10), load test, restore/replay mashqi, runbook’lar, ADR 001–012, ma’lum cheklovlar ro‘yxati.

Qabul: 20-bo‘lim to‘liq; 13.15 barcha gate’lar.

### Keyin — P1

Birinchi haqiqiy ERP adapteri, reconciliation, OCR, XLSX tahriri, SSO, pilot yuklama. Oldindan shart: yuridik xulosa va hosting hududi (TZ 18, 24).

## 3. Kritik yo‘l va parallel ishlar

```
0.1 → 0.2 → 0.3 ─┬→ 0.4 → 0.5 ─┬→ 1.1 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 6
                 └→ 0.6 → 0.7 ─┘        1.2 ↗                        ↘ 3 → 5 ↗
                                  2.1 → 2.2 → 2.3 → 2.4 → 4 ────────────────↗
```

Frontend 0.6 dagi OpenAPI baseline tayyor bo‘lgach mock server bilan parallel boshlaydi.

## 4. Xavflar

| Xavf | Chora |
|---|---|
| Arxitektura infratuzilmasi analitikadan vaqt oladi | Bosqich 0 qat’iy cheklangan; N/N−1 va canary keyinga |
| O‘zbek tilida qidiruv/embedding sifati past | Bosqich 3 boshida kichik eval to‘plami |
| OpenAI mavjudligi/narxi | `FakeProvider` bilan to‘liq ishlash, model konfiguratsiyada |
| Yuridik lokalizatsiya | Pilotdan oldin yurist xulosasi; psevdonimlash Bosqich 5 da |
| LLM kod yozuvchi skelet qoldiradi | Har bosqich qabul testlari bilan yopiladi |

## 5. Holat

### Bosqich 0 — Poydevor: ✅ yakunlandi

| Ish paketi | Holat | Izoh |
|---|---|---|
| 0.1 Monorepo va platforma | ✅ | 3 ta logical DB, alohida owner/app rollari; Postgres hostda 55432 |
| 0.2 Servis skeletlari | ✅ | Business Core to‘liq; AI va Integration health + qatlamlar (Bosqich 1 da to‘ldiriladi) |
| 0.3 Arxitektura testlari | ✅ | import-linter + `tests/architecture`; buzilish CI’ni yiqitishi qo‘lda tekshirildi |
| 0.4 Identity va auth | ✅ | Onboarding, login, lockout, MFA (TOTP, replay himoyasi), sessiya, CSRF, korxona almashtirish, takliflar, a’zolar va rollar, parol tiklash, Redis rate limit |
| 0.5 Tenant izolyatsiyasi (RLS) | ✅ | FORCE RLS (tenants, memberships, invitations), app roli superuser/BYPASSRLS emas, kontekst sizmasligi testlangan |
| 0.6 Kontraktlar | ✅ | Envelope, 4 command, 5 event, 4 canonical + batch manifest; OpenAPI baseline va breaking-change tekshiruvi |
| 0.7 Outbox/inbox | ✅ | `packages/abo_messaging` (ADR 004), Business migratsiyasi va worker; retry/DLQ haqiqiy RabbitMQ bilan testlangan |
| 0.8 Sintetik ma’lumotlar | ✅ | `tools/synthetic_data`, golden (A01/A02/A07) va demo (19 ming satr, 12 oy, barcha ssenariylar) |
| 0.9 CI | 🟡 | Workflow yozilgan, lokal `make check` yashil; GitHub’da remote yo‘qligi sababli ishga tushirilmagan |

Ma’lum cheklovlar:
- Production email adapteri yo‘q: `notifier=log` faqat lokal, boshqa muhitda taklif/parol havolasi yuborilmaydi (provayder tanlovi kerak).
- Rate limit Redis ishlamasa o‘chadi (fail-open); login uchun DB lockout baribir ishlaydi.
- Takliflar commitdan keyin yuboriladi; yuborish xatosi logga yoziladi, qayta yuborish endpointi hali yo‘q.

### Bosqich 1 — Analitika vertikal kesimi: 🟡 asosiy oqim ishlaydi

`make e2e` — API va 3 worker alohida jarayon sifatida: CSV yuklash → mapping tasdiqlash → sync →
ingestion → chat savoli → AI (FakeProvider) → Tool API → hisob → manbali javob → dashboard.
Barqaror (3/3), ~9 soniya.

| Ish paketi | Holat | Izoh |
|---|---|---|
| 1.1 Yuklash | ✅ | CSV → S3, SHA-256, limitlar; XLSX — aniq 415 xabari bilan (P1) |
| 1.2 Integration Runtime | ✅ | Connector SDK, lease’li sync, `file_import`, `demo_erp` (demo deb belgilangan) |
| 1.3 Ingestion | ✅ | Karantin, versiyali snapshot, idempotent batch |
| 1.4 Semantik qatlam | ✅ | 10 metrika, taqqoslash, hissa; valyutalar qo‘shilmaydi; A01/A02/A04/A06/A07 testlangan |
| 1.5 Tool API | ✅ | Servis tokeni, capability, joriy rol, siyosat, schema, idempotentlik |
| 1.6 AI Runtime | ✅ | FakeProvider bilan ishlaydi; OpenAI adapteri real kalit bilan tekshirilmagan |
| 1.7 Workspace | ✅ | Chat, task, RunAgent, SSE (Last-Event-ID), bekor qilish |
| 1.8 Dashboards | 🟡 | Tool orqali yaratish, doska va tafsilot; foydalanuvchi tahriri/versiyalash/ulashish/CSV eksport — hali yo‘q |

Qolgan ishlar va ma’lum cheklovlar:
- OpenAI bilan real tekshiruv (kalit kerak).
- Dashboard tahriri, ulashish, CSV eksport (TZ 8.2).
- FakeProvider: dashboard nomi xabar matnidan olinadi; jadval sarlavhasida metrika ID’si.
- Dashboard kartochkasi preview’i faqat saqlangan natijadan; “yangilash” (refresh) yo‘q.
- Budjet rezervi faqat identifikator (limit qo‘llanmaydi) — Bosqich 5.
- Ingestion batch’ni xotirada ushlaydi (~200 ming satrgacha mos); katta batch — SQL staging, P1.
- Web ilova (Bosqich 2) boshlanmagan; Node.js o‘rnatilmagan.

### Bosqich 2 — Web ilova: ✅ yakunlandi

`make stack` — API + 3 worker + web (http://localhost:3010). `make e2e-ui` — Playwright.

| Ish paketi | Holat | Izoh |
|---|---|---|
| 2.1 Skelet, API client, auth | ✅ | Next.js 16, OpenAPI’dan tiplar, CSRF, ro‘yxatdan o‘tish, login, MFA (QR), korxona almashtirish |
| 2.2 Layout | ✅ | Chap menyu, markaz, doimiy chat; mobil: bitta panel + pastki navigatsiya (toshish yo‘q) |
| 2.3 Chat | ✅ | @agent, SSE task kartasi (bosqich + vaqt, soxta foiz yo‘q), bekor qilish, xavfsiz markdown, xato holatlari |
| 2.4 Dashboardlar | ✅ | Doska, tanlash oynasi, ilova ichidagi oyna, drill-down (oy → filial → mahsulot), breadcrumb, sessiyada tiklanish, Escape va fokus qaytishi |
| 2.5 Integratsiya ekrani | ✅ | CSV yuklash, eng mos entity, mapping tahriri, holat qiymatlari, sinxronlash holati |

Brauzer testlari (Playwright, haqiqiy stek): U02, U03, U05, U06, U07 va to‘liq oqim — o‘tadi (3/3).

UI tekshiruvida topilib tuzatilgan xatolar: birinchi xabarda suhbat ID yo‘qolishi; yangi dashboard
doskada ko‘rinmasligi; bir fayl uchun 4 ta mapping muharriri; mapping jadvalida siqilgan
tanlovlar; mobil ekranda gorizontal toshish va Sozlamalarga yo‘l yo‘qligi; FakeProvider’da oylar
oralig‘i, dashboard nomi, jadval sarlavhalari va debitorlik metrika ID’si.

Bosqich 2 yakunida qo‘shildi:
- A’zolar: ro‘yxat, taklif (Owner/Admin qoidalari), rolni o‘zgartirish, chiqarish; taklifni qabul
  qilish sahifasi; parolni tiklash (so‘rov va yangi parol) sahifalari.
- Dashboard: tahrir (nom, widget nomi/turi/tartibi, o‘chirish) → yangi versiya; versiyalar ro‘yxati;
  ulashish (butun korxona yoki tanlangan a’zolar, ACL backend’da); yangilash (oxirgi snapshot);
  widget bo‘yicha CSV eksport (UTF-8 BOM, formula injection neytrallangan).
- Mavzu: tizim / yorug‘ / qorong‘i, birinchi chizishdan oldin qo‘llanadi (miltillash yo‘q).
- Brauzer testlari: 4 ta ssenariy (asosiy oqim, drill-down, a’zolar va parol, dashboard amallari),
  2 marta ketma-ket barqaror.

Keyingi bosqichlarga o‘tgan ishlar:
- Chat’dagi hujjat “chip”i — Bosqich 3 da qo‘shildi; dataset chip’i — P1.
- Ofis sahnasi va jonli agent holatlari — Bosqich 4.
- Email orqali haqiqiy yuborish (hozir `notifier=log` faqat lokal) — provayder tanlovi kerak.
- Katta eksport uchun fon vazifasi (hozir widget natijasi ≤5000 satr, sinxron).
- ✅ (Bosqich 5) Integratsiya testlari endi alohida *_test bazalarida. Eski yozuv: stek ishlab tursa AI worker test
  run’ini olib ketishi mumkin (beqarorlik). Testlar uchun alohida bazalar — Bosqich 5.

### Bosqich 3 — Hujjatlar: ✅ yakunlandi (FakeProvider bilan; OpenAI tekshiruvi — Bosqich 6)

| Ish paketi | Holat | Izoh |
|---|---|---|
| 3.1 Yuklash va parse | ✅ | DOCX/PDF/TXT, 25 MB limit, tuzilma skaneri, alohida jarayonda parse (timeout, rlimit), skaner PDF → `needs_ocr` |
| 3.2 Bo‘lim/parcha, qidiruv | ✅ | Locator’lar (¶, sahifa, jadval katagi), o‘zbekcha normalizator + FTS prefiks, pgvector, RRF; ACL qidiruvdan oldin |
| 3.3 Embedding | ✅ | `GenerateEmbeddings` → AI Runtime (`ai_runtime.embeddings`) → vektorlar `abo-ai` bucket’da → `EmbeddingsGenerated`; so‘rov vektori `POST /internal/v1/embed` (servis tokeni, 2 s); AI uzilsa matnli rejim va ogohlantirish |
| 3.4 Tahrir | ✅ | `replace_text` patch, DOCX run darajasida, draft versiya, bo‘lim diff’i, promote (409 VERSION_CONFLICT) |
| 3.5 Tool API va agent | ✅ | `search_documents`, `read_document_section`, `compare_document_versions`, `create_document_draft`; Dilnoza (hujjat yordamchisi), koordinator va moliya — faqat o‘qish |
| 3.6 Web | ✅ | Hujjatlar sahifasi (yuklash, holatlar, qidiruv, versiyalar, matn, farq, joriy qilish, yuklab olish, ulashish, o‘chirish); chat’da hujjat chip’i; draft havolasi |

Qabul testlari:
- Integratsiya (Postgres + S3): D01–D05, S03, ACL, chip → `context_refs`, pgvector saqlash va qidiruv.
- Unit: FakeProvider hujjat rejasi — D01 (iqtibos, versiya, locator), D02 (“Hujjatda topilmadi”),
  D06 (hujjat ichidagi buyruq bajarilmaydi), tahrir → draft, noaniq joy → aniqlashtiruvchi savol.
- To‘liq stek (`make e2e`): yuklash → parse → embedding → gibrid qidiruv → iqtibosli javob → AI draft
  → diff → promote.
- Brauzer (Playwright): hujjat oqimi va mobil kenglik (375 px) — 5/5 ssenariy o‘tadi.

Topilib tuzatilgan xatolar: app roli `vector` turini ko‘rmasligi (public sxemaga USAGE, 0010
migratsiyasi) — embedding saqlash va vektor qidiruv ishlamas edi; AI draftdan keyin hujjat
versiyalari yangilanmasligi; chat markdown’ida iqtibos va kursiv yo‘qligi.

Ma’lum cheklovlar:
- `hash` embedding — lokal/demo uchun (kalitsiz); sifatli semantik qidiruv uchun
  `AI_EMBEDDING_PROVIDER=openai` va `OPENAI_EMBEDDING_MODEL` (Bosqich 6 da tekshiriladi).
  Provayder almashtirilsa eski vektorlar o‘lcham bo‘yicha e’tiborsiz qoladi; qayta indekslash buyrug‘i — P1.
- OCR yo‘q (skaner PDF faqat belgilanadi) — P1.
- PDF tahriri draftda DOCX sifatida saqlanadi (asl PDF maketi saqlanmaydi).
- O‘zbek tilidagi qidiruv eval to‘plami — Bosqich 6 eval bilan.

### Bosqich 4 — Virtual ofis: ✅ yakunlandi

| Ish paketi | Holat | Izoh |
|---|---|---|
| 4.1 Agent navbati | ✅ | Har agent uchun korxona bo‘yicha parallel limit (`BUSINESS_AGENT_PARALLEL_LIMIT`, standart 3); to‘lsa — shu agent navbati, o‘rni ko‘rsatiladi, boshqa mutaxassislikka o‘tkazilmaydi; advisory lock bilan poygasiz; slot bo‘shaganda keyingisi yuboriladi; navbatdagi vazifani bekor qilish — AI’ga hech narsa yuborilmaydi |
| 4.2 Holat mapping’i | ✅ | TZ 6 jadvali domen funksiyasi sifatida: step turi AI bosqichidan (read/retrieve/compute/analyze/draft), ustuvorlik, yakuniy holat 30 s dan so‘ng `idle`, aniqlashtirish → `awaiting_input` (javob berilguncha) |
| 4.3 API | ✅ | `GET /api/v1/office` (agent holati, joriy ishlar / limit, navbat, joriy vazifa; boshqa foydalanuvchi vazifasi matni yashirin), `GET /api/v1/tasks`; SSE’da `task.queued` |
| 4.4 Ofis sahnasi | ✅ | DOM/SVG: 5 ta stol, personaj, holat belgisi; strelkalar/Home/End, Enter — agent kartasi (non-modal, Escape va fokus qaytishi); `prefers-reduced-motion`; “Ro‘yxat” ko‘rinishi — sahnasiz muqobil (U01) |
| 4.5 Agent kartasi va Vazifalar | ✅ | Faol vazifalar, bosqich, navbatdagi o‘rin, to‘xtatish, “Chatga yozish” (agent tanlanadi, fokus), suhbatni ochish; Vazifalar sahifasi |

Qabul testlari:
- Unit: holat mapping jadvali, ustuvorlik, 30 s qoida, aniqlashtirish.
- Integratsiya: T01 (limit 1 → o‘rinlar 1, 2; boshqa agent darhol; slot bo‘shaganda navbat siljiydi),
  T05 (navbatdagini bekor qilish), ofis holati progress eventidan, `awaiting_input`.
- To‘liq stek: uchta parallel so‘rov → bittasi ishlaydi, ikkitasi navbatda → hammasi yakunlanadi.
- Brauzer: ofis holati, klaviatura, karta, “Chatga yozish”, ro‘yxat ko‘rinishi (saqlanadi),
  Vazifalar, mobil kenglik; aniqlashtirish → “Javobingizni kutmoqda”, reduced-motion’da animatsiya
  yo‘q (odatiy rejimda borligi ham tekshiriladi). Jami 7/7.

Topilib tuzatilgan xatolar: navbatdagi bir nechta vazifadan eng oxirgisi “joriy” deb ko‘rsatilishi
(endi AI’ga yuborilgan va eng eskisi); vosita xatosi matnida ikki nuqta.

Ma’lum cheklovlar:
- Agent profillari (ism sozlash, doimiy UUID) — P1; hozir standart ismlar.
- `awaiting_approval` holati mapping’da bor, lekin tasdiq talab qiladigan qadam hali yo‘q.
- Ofis holati 2 s polling bilan yangilanadi (backend holatidan); tenant SSE kanali — P1.
- Osilib qolgan (15 daqiqadan oshgan) vazifa slotni band qilmaydi; uni avtomatik `failed` qilish — Bosqich 5.

#### Bosqich 4 aniqlashtirish — jonli ofis xaritasi (TZ 6 “Ofis ko‘rinishi” yangilandi): ✅

- Tepadan ko‘rinadigan xarita (SVG, 60×36 katak): 5 bo‘lim, majlis xonasi, dam olish zonasi,
  koridor, devor va eshiklar, stollar (egasi belgilangan), mebel.
- Harakat backend holatidan: vazifa → o‘z stoliga yurish (A*, devor/mebeldan o‘tmaydi), stolda
  ishlash animatsiyasi (qo‘llar, monitor); `idle` → dam olish joyi. Tasodifiy yurish yo‘q.
  Bir nechta agent mustaqil. Reduced-motion — yurishsiz, animatsiyasiz.
- Kamera: g‘ildirak, +/−, klaviatura, surish, pinch; kamera va joylashuv sessiyada saqlanadi
  (dashboard oynasi va sahifa almashishi holatni yo‘qotmaydi).
- Yorliqlar ekranda o‘qiladigan o‘lchamda; uzoqlashtirilganda bo‘sh agent ismlari yig‘iladi.
- Agent kartasi: joriy vazifa + oxirgi natija (javob, manbalar soni, dashboard/draft havolalari).
- Backend: `/office` → `last_result`; aniqlashtirishga javob — faqat shu agentga keyingi vazifa.

Testlar: unit — xarita (barcha joylar ochiq va o‘zaro yetib boriladi, yo‘l hech qachon to‘siqdan
o‘tmaydi), harakat (holat → joy, yetib borish, stolida bo‘lsa joyida), kamera; brauzer — agent
stoliga yuradi (“walking” → “desk”, o‘z bo‘limida), boshqalar joyida, karta natija bilan, zoom/surish
(tugma, g‘ildirak, sichqoncha, klaviatura), dashboard oynasi va sahifa almashganda holat saqlanadi,
ikki agent parallel, reduced-motion’da “walking” bo‘lmaydi. Brauzer testlari jami 8/8.

Topilib tuzatilgan xatolar: chatda yuborish davomida yozilgan keyingi xabar o‘chib ketishi;
boshqa agentga yozilgan xabar aniqlashtirishga javob deb hisoblanishi; kichik ekranda yorliqlar
ustma-ust tushishi.

Keyin (Bosqich 5 bilan) yopilgan cheklovlar: agentlar to‘qnashuvdan qochadi; ofis holati tenant
SSE orqali; mobil/to‘liq ekran xarita.


### Bosqich 5 — Ishonchlilik va boshqaruv: ✅ yakunlandi

| Ish paketi | Holat | Izoh |
|---|---|---|
| 5.1 Test bazalari | ✅ | `*_test` bazalari (`make test-db`); stek ishlab tursa ham integratsiya testlari barqaror |
| 5.2 Budjet (TZ 19) | ✅ | Narx konfiguratsiyadan (AI `AI_PRICE_*`), vazifa rezervi (standart 0.05 USD) yuborishdan oldin, yakunda haqiqiy sarf; kunlik/oylik limit, 80% ogohlantirish, 100% da yangi pulli ish to‘xtaydi (sabab chatda); Sozlamalar va sarlavhada holat |
| 5.3 Fon ishlari | ✅ | Osilgan vazifa → `TASK_TIMEOUT` (rezerv bo‘shatiladi, navbat siljiydi); suhbat 90 kun, draft 90 kun, audit 365 kun; tozalash job’i eksponensial qayta urinish; tenant ro‘yxati (faqat ID, RLS saqlanadi) |
| 5.4 T03 | ✅ | Model 429/timeout/5xx — 3 urinish, Retry-After, holat chatda; tugasa `PROVIDER_UNAVAILABLE`, soxta javob yo‘q; SDK yashirin retry o‘chiq |
| 5.5 Audit | ✅ | Middleware: muhim amallar (faqat ID’lar, IP); agent artifactlari; faqat qo‘shiladi (UPDATE/DELETE taqiq), 365 kun; egasi/admin uchun Sozlamalarda |
| 5.6 Psevdonimlash (13.12) | ✅ | Ko‘rsatma, tool natijasi, embedding matnida telefon/email/PINFL/pasport/karta va mijoz nomlari tokenlanadi; javob va tool argumentlari Core’da tiklanadi; shifrlangan vault (7 kun); tenant sozlamasi, audit |
| 5.7 Chegara va migratsiya | ✅ | I06: credential faqat o‘z bazasiga, app roli imtiyozsiz, FORCE RLS (2 ta asosli istisno); compose tarmoq segmentatsiyasi, NetworkPolicy namunasi; gate 8: `make migration-check` (CI’da) |
| 5.8 Degradatsiya | ✅ | `make degradation`: I05, I03, broker restart (gate 5/7) haqiqiy jarayonlar bilan; UI: “eskirgan” belgisi, “AI javob bermayapti — navbatda” izohi |
| Ofis qoldiqlari | ✅ | Tenant SSE, to‘qnashuvdan qochish (+ tiqilishsiz joylashuv invarianti), to‘liq ekran, “Xaritada ko‘rsatish”, mobil kadr |

Qabul: T03 (unit), T05 (integratsiya), I03, I05 (degradatsiya skripti), I06 (integratsiya);
gate 5 (outbox/inbox/lease + broker restart), 6, 7, 8. (S02 bu yerda yopilgan deb yozilgan edi —
Bosqich 6 tekshiruvida filial doirasi umuman yo‘qligi aniqlandi va Bosqich 6 da qo‘shildi.)

Tekshiruvlar: `make check` (Business 168, AI 73, Integration 14, messaging 17, repo 236, web 34),
`make e2e` 3/3, `make degradation` 5/5 bosqich, Playwright 11/11, `make migration-check`.

Topilib tuzatilgan xatolar: provayder xatosida run cheksiz qayta olinishi (sarf); dam olish zonasida
agentlar tiqilib qolishi; maxfiylik belgisi keshi asinxron bo‘lgani uchun “sakrashi”; mobil aniqlash
element o‘lchamidan (barqaror emas) — ekran kengligiga o‘tkazildi; xaritada ko‘rsatish hodisasi
xarita chizilmasdan yo‘qolishi.

Ma’lum cheklovlar:
- Budjet embedding sarfini hisobga olmaydi (faqat agent run tokenlari); narx bitta model uchun.
- Audit yozuvi amaldan keyin alohida tranzaksiyada (crash oynasida yo‘qolishi mumkin; amal esa saqlanadi).
- Psevdonimlash regex va ustun nomlariga asoslangan (erkin matndagi F.I.Sh. aniqlanmaydi) —
  pilotdan oldin yurist xulosasi bilan kengaytiriladi (TZ 18).
- AI bucket’idagi vaqtinchalik vektor fayllari o‘chirilmaydi (lifecycle qoidasi — infra).
- NetworkPolicy namunaviy; FQDN egress allowlist klaster egress gateway’ida sozlanadi.


### Bosqich 6 — P0 qabul: 🟡 yakunlandi, real OpenAI tekshiruvi kutilmoqda

Qabul matritsasi: [ACCEPTANCE.md](ACCEPTANCE.md) — TZ 20 dagi har ID va 13.15 gate’lari uchun test/skript.

| Ish paketi | Holat | Izoh |
|---|---|---|
| 6.1 Eval (TZ 20) | ✅ fake / ⏳ OpenAI | `make eval`: 42 raqamli (golden + Tool API), 10 agent raqami, 15+5 hujjat Q&A, 11 tahrir, 10 adversarial — 100%. `make eval-openai` kalit bilan |
| 6.2 Yuklama (TZ 19) | ✅ | `make load`: 1 mln satr 62 s da so‘rovga tayyor; KPI P95 1.97 s; vazifa qabul P95 0.20 s; SSE P95 0.52 s; 10 MB DOCX 22 s; 0 xato (`docs/reports/load-*.md`) |
| 6.3 Tiklash | ✅ | `scripts/restore-drill.sh`: RTO 57 s, 44 jadval / 3.3 mln satr va 733 S3 obyekt mos |
| 6.4 Replay | ✅ | `tools/ops/replay.py` (outbox oynasi, DLQ qaytarish), testlar; runbook |
| 6.5 S02 filial doirasi | ✅ | `memberships.branch_scope`; HTTP, Tool API, taqqoslash/hissa, dashboard/eksport/yangilash; UI “Filiallar” va “Filialga ruxsat yo‘q” |
| 6.6 Yetishmagan qabul testlari | ✅ | A03, A05 (Integration + Core), T02, T04, U04 (backend + Picker) |
| 6.7 Hujjatlar | ✅ | ADR 001–012, runbook’lar (deploy, backup-restore, replay, incidents), PERMISSIONS, LOCAL_SETUP, KNOWN_LIMITATIONS, ACCEPTANCE |
| 6.8 CI | ✅ | pip-audit va npm audit (gate 10), migration-check, secret scan |

Tekshiruvlar: `make check` (Business 179, AI 74, Integration 28, messaging 18, repo 236, web 37),
`make e2e` 3/3, `make degradation` 5/5, Playwright 11/11, eval (fake) 100%.

Topilib tuzatilgan xatolar: eval’da Tool API chaqiruvlari sessiya cookie’si sabab CSRF’ga urilib,
ruxsat ssenariylari “soxta o‘tishi”; KPI so‘rovi har safar 1 mln satrni skanerlashi (snapshot keshi —
P95 5.5 s → 2.0 s); pg_restore xatolari yashirin qolishi; S02 umuman amalga oshirilmagani.

Qolgan: real OpenAI bilan `make eval-openai` (kalit kerak); yuridik xulosa (TZ 18) va email
kanali — [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

### ERP integratsiyasi (soxta ERP bilan): ✅

Yo‘riqnoma: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) — ulash usullari, ma’lumot talablari,
REST API shartnomasi, bosqichma-bosqich ulash va tekshirish, yangi connector yozish, diagnostika.

- `tools/fake_erp` — shartnomaga mos soxta ERP REST API (Bearer kalit, izchil kursor, 429/503
  simulyatsiyasi); demo tarixi + 2026-09-01 dan bugungacha “jonli” yangi hujjatlar. `make stack`
  bilan :8070 da ishga tushadi.
- Integration Runtime: `erp_api` connector (sahifa darajasida retry, `Retry-After`, kalit xatosi
  qayta urinilmaydi), ERP maydonlari uchun mapping shablonlari (100% moslik).
- Business: `erp_api` manbalari har 15 daqiqada avtomatik qayta sinxronlanadi
  (`BUSINESS_ERP_AUTO_SYNC_SECONDS`); muvaffaqiyatsiz sinxronni qayta boshlash.
- Web: “ERP ulash (API)” — 4 obyekt; holat xaritasi obyektga mos (ombor harakati turlari endi UI’da
  ham ulanadi — avval faqat savdo holatlari taklif qilinardi).
- Testlar: conformance (4 connector), ERP xatolari/kursor, avtomatik sinxron, tizim testi
  (`tests/system/test_erp.py`), Playwright (`e2e/erp.spec.ts`).
