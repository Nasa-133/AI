import type { DiscoveredEntity } from "./api";

export const CANONICAL_STATUSES = ["confirmed", "draft", "cancelled"] as const;
const GUESS: Record<string, string> = {
  tasdiqlangan: "confirmed", qoralama: "draft", "bekor qilingan": "cancelled",
  подтвержден: "confirmed", черновик: "draft", отменен: "cancelled",
};

/** Namunaviy satrlardan status ustunining qiymatlari; tanish so‘zlar uchun taklif (tasdiqni foydalanuvchi beradi). */
export function statusValues(entity: DiscoveredEntity): { source_value: string; canonical_value: string }[] {
  const item = entity.suggested_mapping.find((m) => m.transform === "status_map");
  if (!item?.source_column) return [];
  const idx = entity.columns.indexOf(item.source_column);
  const seen = new Set<string>(["tasdiqlangan", "qoralama", "bekor qilingan"]);
  for (const row of entity.sample_rows) if (row[idx]) seen.add(row[idx]!);
  return [...seen].map((v) => ({ source_value: v, canonical_value: GUESS[v] ?? "" }));
}
