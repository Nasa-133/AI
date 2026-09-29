/**
 * Dashboard filtrlari (Superset/Power BI “slicer”): davr va filial butun dashboardga qo‘llanadi.
 * Saqlangan so‘rov spec’i o‘zgartirilib Core’da qayta hisoblanadi — raqamlar yana semantik qatlamdan.
 */
import type { QuerySpec, Widget } from "./types";
import { effectiveType } from "./widgetTypes";

export type PeriodPreset = "saved" | "mtd" | "last_month" | "last_3" | "last_12" | "ytd";
export type DashboardFilter = { period: PeriodPreset; branches: string[] };
export const NO_FILTER: DashboardFilter = { period: "saved", branches: [] };

export const PERIOD_LABEL: Record<PeriodPreset, string> = {
  saved: "Saqlangan davr", mtd: "Shu oy", last_month: "O‘tgan oy", last_3: "Oxirgi 3 oy",
  last_12: "Oxirgi 12 oy", ytd: "Yil boshidan",
};

const iso = (d: Date) => d.toISOString().slice(0, 10);
const utc = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d));

export function periodRange(preset: PeriodPreset, today: Date): { from: string; to: string } | null {
  const y = today.getUTCFullYear(), m = today.getUTCMonth();
  const lastMonthEnd = utc(y, m, 0);
  switch (preset) {
    case "saved": return null;
    case "mtd": return { from: iso(utc(y, m, 1)), to: iso(today) };
    case "last_month": return { from: iso(utc(y, m - 1, 1)), to: iso(lastMonthEnd) };
    case "last_3": return { from: iso(utc(y, m - 3, 1)), to: iso(lastMonthEnd) };
    case "last_12": return { from: iso(utc(y, m - 12, 1)), to: iso(lastMonthEnd) };
    case "ytd": return { from: iso(utc(y, 0, 1)), to: iso(today) };
  }
}

export function isActive(f: DashboardFilter): boolean {
  return f.period !== "saved" || f.branches.length > 0;
}

/** Filtr qo‘llangan so‘rov; o‘zgarish bo‘lmasa — null (saqlangan natija ko‘rsatiladi). */
export function applyFilter(spec: QuerySpec, f: DashboardFilter, today: Date): QuerySpec | null {
  if (!isActive(f)) return null;
  const range = periodRange(f.period, today);
  return {
    ...spec,
    date_range: range ?? spec.date_range,
    filters: { ...spec.filters, branch_codes: f.branches.length ? f.branches : spec.filters.branch_codes ?? null },
  };
}

/** KPI taqqoslash uchun oldingi teng davr: to‘liq oylar — oldingi shuncha oy; aks holda kunlar siljiydi. */
export function previousRange(range: { from: string; to: string }): { from: string; to: string } {
  const from = new Date(`${range.from}T00:00:00Z`), to = new Date(`${range.to}T00:00:00Z`);
  const fullMonths = from.getUTCDate() === 1 && utc(to.getUTCFullYear(), to.getUTCMonth() + 1, 0).getTime() === to.getTime();
  if (fullMonths) {
    const months = (to.getUTCFullYear() - from.getUTCFullYear()) * 12 + to.getUTCMonth() - from.getUTCMonth() + 1;
    return { from: iso(utc(from.getUTCFullYear(), from.getUTCMonth() - months, 1)),
             to: iso(utc(from.getUTCFullYear(), from.getUTCMonth(), 0)) };
  }
  const days = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
  return { from: iso(new Date(from.getTime() - days * 86_400_000)), to: iso(new Date(from.getTime() - 86_400_000)) };
}

/** Kattaroq qiymat yaxshimi (KPI o‘zgarish rangi uchun). Qaytarish, tannarx, qarz — kamaygani yaxshi. */
export function higherIsBetter(metricId: string | null | undefined): boolean {
  return !["returns", "cogs", "discounts", "receivables_open", "receivables_overdue"].includes(metricId ?? "");
}

/** 12 ustunli to‘rda kenglik: KPI kichik, grafiklar yarim, keng jadval/matn — to‘liq. */
export function spanFor(widget: Widget): number {
  if (widget.data && !widget.data.rows.length) return widget.type === "kpi" ? 3 : 6;  // bo‘sh — ixcham
  switch (effectiveType(widget, widget.data)) {
    case "kpi": return 3;
    case "pie": case "funnel": return 6;
    case "text": return 12;
    case "heatmap": return 12;
    case "table": return (widget.data?.columns.length ?? 0) > 5 ? 12 : 6;
    default: return 6;
  }
}
