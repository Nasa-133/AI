# ADR 006 — Kanonik yozuvlar va connector anti-corruption layer

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Har ERP (1C, SAP, mahalliy tizimlar) va CSV eksporti o‘z ustun nomlari, formatlari va holat
qiymatlariga ega. Core va analitika vendor formatini bilsa, har yangi manba core’ni o‘zgartiradi.
TZ 13.10 connector faqat manbani o‘qishini, normallashtirish esa umumiy bo‘lishini talab qiladi.

## Qaror

- Connector SDK porti (`integration_runtime/ports/connector.py`): manifest, `discover_schema`,
  `read_rows` — faqat xom satrlar. Connector tip, valyuta, holatni talqin qilmaydi.
- Normallashtirish, rad etish va batch — Sync Engine va domain mapping’da (bir joyda).
- Natija — kanonik entity’lar (`contracts/canonical/*`: `sales.order_line`, `sales.return`,
  `inventory.movement`, `finance.receivable`); Core faqat shularni biladi.
- Mapping foydalanuvchi tomonidan tasdiqlanadi va versiyalanadi; noma’lum ustun taxmin qilinmaydi.

## Muqobillar

- **Har connector o‘zi kanonik yozuv qaytaradi.** Connector yozish tezroq, lekin validatsiya va
  rad etish qoidalari tarqaladi, I02 (bir xil natija) kafolatlanmaydi. Rad etildi.
- **ELT (xom ma’lumot omborga, SQL bilan transformatsiya).** Moslashuvchan, lekin qoidalar SQL’ga
  tarqaladi va sinash qiyin. P2 da katta hajmlar uchun qayta ko‘riladi.

## Trade-off

Kanonik model hamma ERP nozikliklarini qamramaydi — yangi maydon kontrakt o‘zgarishini talab
qiladi (ADR 005). Evaziga yangi connector core’ga tegmaydi.

## Oqibat va tekshiruv

- `services/integration_runtime/tests/unit/test_connector_conformance.py`: uch connector (CSV,
  demo ERP, faqat portni amalga oshirgan sintetik API) bitta kontraktdan o‘tadi (I01); CSV va
  demo ERP bayt darajasida bir xil kanonik batch beradi (I02).
- `test_mapping_real_data.py` — shablon tanish, noma’lum ustunni taxmin qilmaslik.
