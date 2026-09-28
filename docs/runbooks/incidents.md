# Hodisalar

## AI Runtime yoki OpenAI javob bermayapti

**Belgilar**: chatda “AI xizmati hozir javob bermayapti — vazifa navbatda saqlangan”; vazifalar
`queued`; qidiruvda “Semantik qidiruv vaqtincha mavjud emas”; AI logida `ModelUnavailable`.

**Tizim o‘zi nima qiladi** (I05, T03): dashboard, hujjat va matnli qidiruv ishlaydi; vazifalar
yo‘qolmaydi; provayder 429/timeout’da 3 marta kutish bilan urinadi, keyin `PROVIDER_UNAVAILABLE`
(soxta javob yo‘q); 15 daqiqadan oshgan vazifa `TASK_TIMEOUT` bilan yopiladi, budjet rezervi
qaytariladi.

**Harakat**:
1. `GET /health/ready` (AI API); AI worker logi; OpenAI status sahifasi.
2. 401/403 (kalit) — [Kalit almashtirish](#kalit-almashtirish). 429 — limitlar/budjetni tekshirish,
   `AI_RUNNER_CONCURRENCY` ni vaqtincha kamaytirish.
3. Tiklangach navbatdagi vazifalar o‘zi bajariladi (bir marta — idempotent).

## Broker (RabbitMQ) ishlamayapti

**Belgilar**: vazifalar `queued`, import “kutilmoqda”; outbox’da `pending` o‘sadi.
**Tizim**: yozuvlar outbox’da saqlanadi; worker’lar qayta ulanadi (robust connection); broker
qaytgach relay yuboradi (gate 5/7, `scripts/degradation.sh`).
**Harakat**: brokerni tiklash; `failed_at` to‘lgan xabarlar bo‘lsa [replay.md](replay.md).

## Integration Runtime ishlamayapti / ma’lumot eskirgan

**Belgilar**: dashboard doskasida “Eskirgan” ogohlantirishi; manba holati “Kutilmoqda”.
**Tizim** (I03): dashboard oxirgi to‘liq snapshot bilan ishlaydi; chat va hujjatlar ishlaydi.
**Harakat**: Integration worker logi; ERP/fayl mavjudligi; tiklangach sync qayta boshlanadi.
Chegara: `BUSINESS_DATA_STALE_AFTER_SECONDS` (standart 300).

## Budjet limiti tugadi

**Belgilar**: chatda “AI budjeti limiti tugagan”, sarlavhada “AI budjeti 100%”.
**Harakat**: korxona egasi Sozlamalar → AI budjeti’da limitni oshiradi (auditda qayd). Boshlangan
vazifalar tugaydi; yangi pulli ish limit ichida qayta boshlanadi.

## Osilib qolgan vazifa

Worker o‘zi 15 daqiqadan keyin `TASK_TIMEOUT` qiladi (`maintenance_loop`). Qo‘lda tekshirish:
```sql
SELECT id, agent_role_key, status, dispatched_at FROM workspace.tasks
WHERE status NOT IN ('succeeded','partial','failed','cancelled') ORDER BY dispatched_at;
```
AI tomonida: `agent.run_queue` lease’lari (`lease_expires_at`) — eskirgan lease boshqa worker
tomonidan davom ettiriladi.

## Kalit almashtirish

| Kalit | Tartib |
|---|---|
| `OPENAI_API_KEY` | Yangi kalit → AI Runtime secret → AI worker/API restart. Eski kalitni o‘chirish. |
| Servis tokeni (`BUSINESS_TOOLS_SERVICE_TOKEN` = `AI_BUSINESS_TOOLS_TOKEN`) | Ikkala tomonda bir vaqtda; Business avval qabul qilsa ham, qisqa uzilishda AI tool chaqiruvi 401 → run xato bilan tugaydi (qayta yuborish mumkin). |
| `BUSINESS_CAPABILITY_SIGNING_KEY` | Almashtirilganda faol vazifalar capability’si yaroqsiz bo‘ladi (≤10 daqiqa) — kam yuklama vaqtida. |
| `BUSINESS_DATA_ENCRYPTION_KEY` | MFA sirlari va psevdonim vault’i shu kalit bilan shifrlangan: qayta shifrlash migratsiyasi kerak (P1). Hozircha almashtirish = foydalanuvchilar MFA’ni qayta sozlaydi; psevdonim tokenlari 7 kunda o‘zi tozalanadi. |
| DB parollari | Har runtime alohida; ulanish hovuzi restart bilan. |

## Tenant ma’lumotini o‘chirish (mijoz talabi)

1. Hujjatlar: har hujjat `DELETE /api/v1/documents/{id}` (kirish darhol yopiladi, fayllar cleanup
   job bilan; muvaffaqiyatsizi qayta uriniladi).
2. Suhbatlar: retention (`BUSINESS_RETENTION_CONVERSATION_DAYS`) yoki qo‘lda — P1 da API.
3. Integratsiya batch’lari (`abo-integration`), vektorlar (`abo-ai`) — S3 prefiks `…/<tenant_id>/`.
4. Backup’lardan — saqlash muddati (30 kun) tugagach.
5. Audit jurnalida qayd; bajarilganini mijozga yozma tasdiqlash.
