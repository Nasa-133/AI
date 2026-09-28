import { realDimensions, valueColumns } from "./charts";
import type { Widget } from "./types";

const TIME = new Set(["month", "week", "day"]);

/** Natija shakliga mos widget turlari — backend ham xuddi shu qoidani tekshiradi (TZ 8.2). */
export function allowedTypes(widget: Widget): Widget["type"][] {
  if (widget.type === "text" || !widget.data) return [widget.type];
  const data = widget.data;
  const dims = realDimensions(data).map((i) => data.columns[i].name);
  const values = valueColumns(data);
  const percent = values.some((i) => data.columns[i].unit === "percent");
  const types: Widget["type"][] = [];
  if (dims.length && TIME.has(dims[0])) types.push("line", "area");
  if (dims.length) types.push("bar");
  if (dims.length === 2 && values.length === 1) types.push("stacked_bar", "heatmap");
  if (dims.length === 1 && values.length === 1 && !percent) {
    if (data.rows.length <= 12) types.push("pie");
    types.push("funnel");
  }
  if (data.rows.length === 1) types.push("kpi");
  types.push("table");
  return types;
}

export const TYPE_LABEL: Record<Widget["type"], string> = {
  kpi: "KPI karta", line: "Chiziqli grafik", area: "Maydonli grafik", bar: "Ustunli grafik",
  stacked_bar: "Ustma-ust ustunlar", pie: "Doiraviy (ulush)", funnel: "Voronka",
  heatmap: "Issiqlik xaritasi", table: "Jadval", text: "Matn",
};
