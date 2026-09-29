/**
 * Agent javobini ekran uchun tuzish: birinchi ko‘rinishda qisqa xulosa, asosiy raqamlar va keyingi
 * qadam; qo‘shimcha bo‘limlar yig‘iladi; manbalar inson tushunadigan nom bilan, UUID/timestamp esa
 * faqat “Texnik tafsilot”da. Ma’lumot yetishmasligi haqidagi ogohlantirishlar yashirilmaydi.
 * Toza funksiyalar — DOM’siz test qilinadi.
 */
import { parseMarkdown, type Block, type Inline } from "@/shared/markdown/parse";

import type { SourceRef } from "./api";

export type Section = { title: string; note: string; blocks: Block[] };
export type SourceItem = { label: string; raw: string };
export type Answer = {
  lead: Block[];
  numbers: Section | null;
  next: Section | null;
  extra: Section[];
  notices: string[];
  sources: SourceItem[];
};

const LEAD = /^qisqa javob$/i;
const NUMBERS = /^asosiy raqamlar$/i;
const NEXT = /^(harakat variantlari|keyingi qadam(lar)?)$/i;
const SOURCES = /^(manbalar( va cheklovlar)?|cheklovlar)$/i;

const UUID = /`?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`?/gi;
const ISO_TS = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?/g;

/** Ma’lumot to‘plami nomlari (Core’dagi kanonik obyektlar). */
export const ENTITY_LABEL: Record<string, string> = {
  "sales.order_line": "Sotuvlar", "sales.return": "Qaytarishlar",
  "inventory.movement": "Ombor harakatlari", "finance.receivable": "Debitorlik",
  "crm.deal": "CRM bitimlari",
};

const text = (items: Inline[]) => items.map((i) => i.text).join("");

/** “**Sarlavha** (izoh) matn…” — sarlavha, izoh va qolgan matn. */
function sectionStart(block: Block): { title: string; note: string; rest: Inline[] } | null {
  if (block.kind === "heading") return { title: text(block.content).trim(), note: "", rest: [] };
  if (block.kind !== "paragraph" || block.content[0]?.kind !== "strong") return null;
  const title = block.content[0].text.trim();
  const tail = block.content.slice(1);
  const known = [LEAD, NUMBERS, NEXT, SOURCES].some((re) => re.test(title));
  const tailText = text(tail).trim();
  // Noma’lum qalin so‘z faqat o‘zi alohida qator bo‘lsa (yoki qavsdagi izoh bilan) sarlavha.
  const note = /^\(.*\)$/.test(tailText) ? tailText.slice(1, -1) : "";
  if (!known && tailText && !note) return null;
  return { title, note, rest: note ? [] : tail.filter((i, k) => k > 0 || i.text.trim()) };
}

export function localTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Manba qatori → inson o‘qiydigan nom (UUID va to‘liq vaqt tamg‘asisiz). */
export function humanizeSource(line: string, refs: SourceRef[], snapshotIndex: number): string {
  const m = /^(Dataset snapshot|Taqqoslash query|Hissa query|Query|Dashboard|Hujjat):\s*(.*)$/i.exec(line);
  const rest = (m ? m[2] : line)
    .replace(ISO_TS, (ts) => localTime(ts))
    .replace(UUID, "")
    .replace(/hisoblangan:/i, "hisoblandi")
    .replace(/\(\s*,\s*/g, "(").replace(/\(\s*\)/g, "").replace(/^[\s;,.:]+|[\s;,]+$/g, "")
    .replace(/;\s*/g, " · ").replace(/\s{2,}/g, " ").trim();
  if (!m) return rest;
  const kind = m[1].toLowerCase();
  if (kind === "dataset snapshot") {
    const ref = refs.filter((r) => r.kind === "dataset_snapshot")[snapshotIndex];
    const name = ref?.locator ? ENTITY_LABEL[ref.locator] ?? ref.locator : null;
    return name ? `Ma’lumot: ${name}` : "Ma’lumot to‘plami";
  }
  if (kind === "query") return rest ? `Hisob: ${rest}` : "Hisob";
  if (kind === "taqqoslash query") return "Taqqoslash hisobi";
  if (kind === "hissa query") return "Hissa hisobi";
  if (kind === "dashboard") return rest ? `Dashboard: ${rest}` : "Dashboard";
  return rest ? `Hujjat: ${rest}` : "Hujjat";
}

/** Texnik identifikator (UUID yoki to‘liq vaqt tamg‘asi) bormi — bor bo‘lsa bu manba qatori. */
const isTechnical = (line: string) => new RegExp(UUID.source, "i").test(line) || /\d{4}-\d{2}-\d{2}T\d{2}:/.test(line);

export function structureAnswer(source: string, refs: SourceRef[]): Answer | null {
  const blocks = parseMarkdown(source);
  const sections: Section[] = [];
  const before: Block[] = [];
  for (const b of blocks) {
    const start = sectionStart(b);
    if (start) {
      sections.push({ title: start.title, note: start.note, blocks: start.rest.length
        ? [{ kind: "paragraph", content: start.rest }] : [] });
    } else if (sections.length) {
      sections[sections.length - 1].blocks.push(b);
    } else {
      before.push(b);
    }
  }
  if (!sections.some((s) => [LEAD, NUMBERS, NEXT, SOURCES].some((re) => re.test(s.title)))) return null;

  const find = (re: RegExp) => sections.find((s) => re.test(s.title)) ?? null;
  const lead = [...before, ...(find(LEAD)?.blocks ?? [])];
  const sourceSection = find(SOURCES);
  const notices: string[] = [];
  const items: SourceItem[] = [];
  let snapshots = 0;
  for (const b of sourceSection?.blocks ?? []) {
    const lines = b.kind === "list" ? b.items.map(text) : b.kind === "paragraph" ? [text(b.content)] : [];
    for (const line of lines) {
      if (isTechnical(line)) {
        const label = humanizeSource(line, refs, /^dataset snapshot/i.test(line) ? snapshots++ : 0);
        items.push({ label, raw: line });
      } else if (line.trim()) {
        notices.push(line.trim());
      }
    }
  }
  const extra = sections.filter((s) => ![LEAD, NUMBERS, NEXT, SOURCES].some((re) => re.test(s.title)));
  return { lead, numbers: find(NUMBERS), next: find(NEXT), extra, notices, sources: items };
}
