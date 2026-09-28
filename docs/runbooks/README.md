# Runbook’lar

| Runbook | Qachon |
|---|---|
| [deploy.md](deploy.md) | Yangi versiyani chiqarish, migratsiya, orqaga qaytarish |
| [backup-restore.md](backup-restore.md) | Zaxira, tiklash, tiklash mashqi (RPO/RTO) |
| [replay.md](replay.md) | Outbox eventlarini qayta yuborish, DLQ’dan qaytarish |
| [incidents.md](incidents.md) | AI/OpenAI, broker, Integration, budjet, osilgan vazifa, kalit almashtirish, tenant ma’lumotini o‘chirish |

Umumiy tamoyillar:

- Avval **ko‘rish**, keyin o‘zgartirish: har runbook “Tashxis” bo‘limidan boshlanadi.
- Har o‘zgartirish audit jurnalida yoki commit/PR’da qayd etiladi.
- Qayta yuborish (replay) xavfsiz: yetkazish at-least-once, consumer’lar `event_id` bo‘yicha dedup
  qiladi (ADR 004). Lekin tashqi yon ta’sirlar (masalan, kelajakdagi email) uchun tur bo‘yicha
  filtrlang.
- Vaqt oynalari **DB soati** bo‘yicha (`SELECT now()`), host soati bo‘yicha emas.
