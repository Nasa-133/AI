import type { Widget } from "./types";

const TIME = new Set(["month", "week", "day"]);

/** Natija shakliga mos widget turlari — backend ham xuddi shu qoidani tekshiradi (TZ 8.2). */
export function allowedTypes(widget: Widget): Widget["type"][] {
  if (widget.type === "text" || !widget.data) return [widget.type];
  const dims = widget.data.columns.filter((c) => c.kind === "dimension").map((c) => c.name);
  const types: Widget["type"][] = ["table"];
  if (widget.data.rows.length === 1) types.unshift("kpi");
  if (dims.length) types.unshift("bar");
  if (dims.length && TIME.has(dims[0])) types.unshift("line");
  return types;
}

export const TYPE_LABEL: Record<Widget["type"], string> = {
  kpi: "KPI", line: "Chiziqli grafik", bar: "Ustunli grafik", table: "Jadval", text: "Matn",
};
