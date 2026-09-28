# ADR 009 — Kerakli joyda CQRS read projection; P0’da full event sourcing yo‘q

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Ba’zi o‘qishlar yozish modelidan farq qiladi: ofis holati (task + step + navbat), dashboard
kartochkasi preview’i, hujjat qidiruv parchalari. TZ 13.14 full event sourcing’ni alohida
asoslashsiz kiritishni taqiqlaydi.

## Qaror

- Yozish modeli — oddiy relatsion jadvallar (joriy holat) + outbox eventlari.
- Read projection’lar faqat kerakli joyda va qayta quriladigan:
  - analitika snapshot’lari va saqlangan query natijalari (dashboard kartochkasi);
  - hujjat bo‘limlari/parchalari (FTS + vektor) — versiyadan qayta hosil qilinadi;
  - ofis holati — so‘rov vaqtida task/step’dan hisoblanadi (`workspace/domain/office.py`), alohida
    jadval yo‘q; SSE o‘zgarish belgisi bilan yangilanadi.
- SSE task eventlari (`workspace.task_events`) — UI uchun append-only jurnal, lekin holat manbai emas.

## Muqobillar

- **Full event sourcing (har aggregate eventlardan).** Audit va vaqt bo‘yicha qayta tiklash kuchli,
  lekin migratsiya, versiyalash va projection qayta qurish narxi P0 uchun katta. Rad etildi.
- **Hamma o‘qish yozish modelidan.** Oddiy, lekin qidiruv va dashboard preview sekin bo‘ladi.

## Trade-off

Tarixiy holatni “istalgan vaqtga” tiklab bo‘lmaydi (audit jurnali va snapshot versiyalari bilan
cheklangan). Qayta ko‘rish triggeri: huquqiy talab bilan to‘liq tarix kerak bo‘lsa.

## Oqibat va tekshiruv

- `tests/unit/workspace/test_office.py` (projection mapping), `test_analytics.py` (snapshot
  versiyalari, A05), `test_documents.py` (qayta indekslash, S03 — o‘chirilgan parcha yo‘qoladi).
