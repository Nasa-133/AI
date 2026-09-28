import type { QueryResult, QuerySpec } from "./types";

/** Drill-down ierarxiyasi: faqat dataset qo‘llaydigan kesimlar (TZ 8.1). */
const NEXT: Record<string, string> = { month: "branch", week: "branch", day: "branch", branch: "product", product: "customer" };
const FILTER_KEY: Record<string, keyof QuerySpec["filters"]> = {
  branch: "branch_codes", product: "product_codes", customer: "customer_codes",
};
export const DIMENSION_LABEL: Record<string, string> = {
  month: "Oy", week: "Hafta", day: "Kun", branch: "Filial", product: "Mahsulot",
  customer: "Mijoz", currency: "Valyuta", stage: "Bosqich", channel: "Kanal",
};

export type DrillStep = { dimension: string; member: string; label: string; spec: QuerySpec };

export function nextDimension(spec: QuerySpec): string | null {
  const first = spec.dimensions[0];
  return first ? NEXT[first] ?? null : null;
}

function monthRange(member: string): { from: string; to: string } {
  const [y, m] = member.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { from: `${member}-01`, to: `${member}-${String(last).padStart(2, "0")}` };
}

/** Tanlangan segment bo‘yicha keyingi darajadagi so‘rov (davr/filtr torayadi, metrika o‘zgarmaydi). */
export function drillQuery(spec: QuerySpec, member: string): QuerySpec | null {
  const dim = spec.dimensions[0];
  const next = nextDimension(spec);
  if (!dim || !next) return null;
  const filters = { ...spec.filters };
  let date_range = spec.date_range;
  if (dim === "month") date_range = monthRange(member);
  else if (dim === "day") date_range = { from: member, to: member };
  else if (dim === "week") return null; // ISO hafta chegaralari — keyingi versiyada
  else filters[FILTER_KEY[dim]] = [member];
  return { ...spec, date_range, dimensions: [next], filters, limit: null };
}

export function canDrill(spec: QuerySpec | null, member: string | null | undefined): boolean {
  return Boolean(spec && member && drillQuery(spec, member));
}

/** Natijadan grafik uchun seriyalar: birinchi o‘lcham — kategoriya, metrikalar — seriya. */
export function toSeries(result: QueryResult) {
  const dimIndex = result.columns.findIndex((c) => c.kind === "dimension");
  const nameIndex = result.columns.findIndex((c) => c.kind === "dimension" && c.name.endsWith("_name"));
  const metrics = result.columns
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.kind === "metric" || c.kind === "current");
  const categories = result.rows.map((r) => String(r[dimIndex] ?? ""));
  const labels = result.rows.map((r, i) => (nameIndex >= 0 && r[nameIndex] ? `${r[nameIndex]}` : categories[i]));
  return {
    categories,
    labels,
    series: metrics.map(({ c, i }) => ({
      name: c.metric_id ?? c.name,
      unit: c.unit,
      values: result.rows.map((r) => (r[i] === null ? null : Number(r[i]))),
    })),
  };
}

/** Sessiyadagi ko‘rinish holati: dashboard ID bo‘yicha (TZ 6, U07). */
export type ViewState = { steps: DrillStep[] };
const key = (id: string) => `abo.dashboard.${id}`;

export function loadView(id: string, storage: Storage | undefined = globalThis.sessionStorage): ViewState {
  try {
    const raw = storage?.getItem(key(id));
    return raw ? (JSON.parse(raw) as ViewState) : { steps: [] };
  } catch {
    return { steps: [] };
  }
}

export function saveView(id: string, view: ViewState, storage: Storage | undefined = globalThis.sessionStorage): void {
  try { storage?.setItem(key(id), JSON.stringify(view)); } catch { /* saqlanmasa ham ishlaydi */ }
}
