import type { Version } from "./api";

/** Hujjat versiyasi holati foydalanuvchi tilida (TZ 9.2): nima bo‘ldi va nima qilish kerak. */
export function versionStatus(v: Version): { label: string; cls: string; hint: string | null } {
  switch (v.parse_status) {
    case "pending":
    case "parsing":
      return { label: "O‘qilmoqda", cls: "badge badge-accent", hint: null };
    case "needs_ocr":
      return { label: "Skaner (OCR kerak)", cls: "badge badge-warning",
               hint: "Fayl rasm ko‘rinishida — matn topilmadi. Matnli PDF yoki DOCX yuklang." };
    case "failed":
      return { label: "O‘qib bo‘lmadi", cls: "badge badge-danger",
               hint: v.parse_error ?? "Fayl buzilgan yoki qo‘llab-quvvatlanmaydi." };
    default:
      break;
  }
  if (v.embedding_status === "pending") {
    return { label: "Indekslanmoqda", cls: "badge badge-accent",
             hint: "Matnli qidiruv hozir ishlaydi; semantik qidiruv tez orada qo‘shiladi." };
  }
  if (v.embedding_status === "failed") {
    return { label: "Tayyor (faqat matnli qidiruv)", cls: "badge badge-warning",
             hint: "Semantik indeks yaratilmadi — qidiruv kalit so‘zlar bo‘yicha ishlaydi." };
  }
  return { label: "Tayyor", cls: "badge badge-success", hint: null };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

export const KIND_LABEL: Record<string, string> = {
  original: "Asl nusxa", draft: "Draft",
};
