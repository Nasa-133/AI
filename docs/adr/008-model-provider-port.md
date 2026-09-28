# ADR 008 — Model provayderi porti

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Model provayderi (OpenAI) narx, sifat va hosting talablari bo‘yicha almashishi mumkin; testlar va
lokal ishlab chiqish kalitsiz ishlashi kerak. TZ 10 va 13.15 gate 4 provayder almashishi domain
importlarini o‘zgartirmasligini talab qiladi. Xato bo‘lsa fake’ga yashirin o‘tish taqiqlangan.

## Qaror

- `ai_runtime/ports/model.py`: `ModelProvider.respond(ModelRequest) → ModelResponse` (Responses API
  elementlari formatida, tool call’lar bilan); `ModelUnavailable(retryable)`.
- Adapterlar: `OpenAIResponsesProvider` (strict tools, `store=False`, SDK ichki retry o‘chiq) va
  `FakeProvider` (deterministik reja — testlar va demo). Tanlov faqat konfiguratsiya
  (`AI_MODEL_PROVIDER`), composition root’da; xato bo‘lsa fake’ga o‘tish yo‘q.
- Embedding ham port: `EmbeddingProvider` (hash — lokal, OpenAI — production).
- Runner qayta urinish siyosatini o‘zi boshqaradi (T03): cheklangan, holat ko‘rinadigan.

## Muqobillar

- **OpenAI SDK’ni runner ichida to‘g‘ridan-to‘g‘ri chaqirish.** Kamroq kod, lekin testlar real
  kalit yoki murakkab mock talab qiladi; provayder almashishi runner’ni o‘zgartiradi.
- **LangChain kabi freymvork.** Tayyor abstraksiya, lekin bog‘liqlik katta va checkpoint/lease
  semantikamiz bilan mos emas.

## Trade-off

FakeProvider haqiqiy model emas: u bilan o‘tgan eval “real integratsiya tekshirildi” degani emas
(hisobotda rejim aniq yoziladi). Fake’ni ham qo‘llab-quvvatlash kerak.

## Oqibat va tekshiruv

- import-linter: “OpenAI SDK faqat adapters qatlamida”.
- `tests/unit/test_openai_provider.py` (mock transport), `test_provider_failures.py` (429/5xx/401
  xaritasi, qayta urinish), `test_runner.py` fake bilan to‘liq oqim.
- `make eval-openai` — real provayder bilan bir xil eval (kalit kerak).
