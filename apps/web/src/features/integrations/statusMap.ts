import type { DiscoveredEntity } from "./api";

export const CANONICAL_STATUSES = ["confirmed", "draft", "cancelled"] as const;
export const MOVEMENT_TYPES = ["receipt", "sale", "return", "transfer_in", "transfer_out", "adjustment"] as const;
export const DEAL_STATUSES = ["open", "won", "lost"] as const;

/** Tanish manba qiymatlari oilalari (o‘zbekcha eksport, ruscha 1C, inglizcha ERP API). */
const FAMILIES: Record<string, string>[] = [
  { tasdiqlangan: "confirmed", qoralama: "draft", "bekor qilingan": "cancelled" },
  { подтвержден: "confirmed", черновик: "draft", отменен: "cancelled" },
  { posted: "confirmed", draft: "draft", cancelled: "cancelled" },
  { kirim: "receipt", sotuv: "sale", qaytarish: "return", "ko‘chirish_kirim": "transfer_in",
    "ko‘chirish_chiqim": "transfer_out", tuzatish: "adjustment" },
  { receipt: "receipt", sale: "sale", return: "return", transfer_in: "transfer_in",
    transfer_out: "transfer_out", adjustment: "adjustment" },
  { open: "open", won: "won", lost: "lost" },
  { ochiq: "open", yutildi: "won", yutqazildi: "lost" },
];

/** Obyekt uchun ruxsat etilgan kanonik qiymatlar (ombor harakati — tur, qolganlari — holat). */
export function canonicalOptions(entity: string): readonly string[] {
  if (entity === "inventory.movement") return MOVEMENT_TYPES;
  return entity === "crm.deal" ? DEAL_STATUSES : CANONICAL_STATUSES;
}

/**
 * Namunaviy satrlardan status/tur ustunining qiymatlari; tanish so‘zlar uchun taklif (tasdiqni
 * foydalanuvchi beradi). Namunada bitta oila qiymati uchrasa, oilaning barcha qiymatlari
 * qo‘shiladi — namunaga tushmagan holatlar ham xaritada bo‘lsin (aks holda satr karantinga tushadi).
 */
export function statusValues(entity: DiscoveredEntity): { source_value: string; canonical_value: string }[] {
  const item = entity.suggested_mapping.find((m) => m.transform === "status_map");
  if (!item?.source_column) return [];
  const allowed = new Set(canonicalOptions(entity.entity));
  const families = FAMILIES.filter((f) => Object.values(f).every((v) => allowed.has(v)));
  const idx = entity.columns.indexOf(item.source_column);
  const samples = entity.sample_rows.map((row) => row[idx]).filter((v): v is string => !!v);
  const matched = families.filter((f) => samples.some((v) => v in f));
  const seen = new Set<string>();
  for (const f of matched.length ? matched : families.slice(0, 1)) for (const k of Object.keys(f)) seen.add(k);
  for (const v of samples) seen.add(v);
  const guess = Object.assign({}, ...families) as Record<string, string>;
  return [...seen].map((v) => ({ source_value: v, canonical_value: guess[v] ?? "" }));
}
