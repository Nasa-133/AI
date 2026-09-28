# ADR 007 — Deterministik analitika: raqamlar LLM matnidan olinmaydi

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Til modeli raqamni “hisoblab” yozishi mumkin, lekin natija tekshirilmaydi va qayta
takrorlanmaydi. Moliyaviy xulosada bitta noto‘g‘ri raqam ishonchni yo‘qotadi. TZ 7.2 har
biznes raqami tasdiqlangan metrika va snapshot’dan kelishini talab qiladi.

## Qaror

- Metrika lug‘ati (`analytics/domain/metrics.py`) — ID, versiya, formula, birlik, ruxsat etilgan
  kesimlar. Hisob Decimal’da, domain funksiyasida; valyutalar qo‘shilmaydi.
- Agent faqat Tool API (`run_metric_query`, `compare_periods`, `explain_contributions`) orqali
  raqam oladi; javobdagi raqamlar tool natijasidan. Natija `query_spec_id` va dataset snapshot
  bilan bog‘lanadi — dashboard va chat bir xil query’ni ishlatadi (A04).
- Snapshot versiyalangan (`valid_from_seq`/`valid_to_seq`); sync yarim yo‘lda uzilsa oxirgi to‘liq
  snapshot qoladi (A05).

## Muqobillar

- **LLM’ga SQL yozdirish (text-to-SQL).** Moslashuvchan, lekin natija tasdiqlanmagan va RLS/ruxsat
  chegarasini buzish xavfi. Rad etildi.
- **BI vositasi (Metabase va h.k.) ichiga joylash.** Tez, lekin metrika semantikasi va ruxsat
  bizning modeldan tashqarida qoladi.

## Trade-off

Yangi savol turi uchun yangi metrika/kesim kerak — agent “hamma narsani” javob bera olmaydi va
aniqlashtiradi. Evaziga har raqam qayta hisoblanadi va manbasi ko‘rsatiladi.

## Oqibat va tekshiruv

- Eval: 42 deterministik holat `expected.json` (generator o‘zi hisoblagan) va golden A01/A02/A07
  bilan 100% mos; 10 agent javobida raqam hisob mexanizmi natijasi bilan bir xil
  (`docs/reports/eval-*.md`).
- `services/business/tests/unit/analytics`, `tests/integration/test_analytics*.py`.
