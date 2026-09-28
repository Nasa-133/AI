import { describe, expect, it } from "vitest";

import type { Widget } from "./types";
import { allowedTypes } from "./widgetTypes";

const widget = (dims: string[], rows: number): Widget => ({
  id: "w1", title: "t", type: "table", query_spec_id: "q", text: null, query: null, status: "ready",
  data: {
    query_spec_id: "q", dataset_snapshot_ids: [], currency: "UZS", notes: [],
    columns: [...dims.map((d) => ({ name: d, kind: "dimension", metric_id: null, unit: null })),
              { name: "net_sales", kind: "metric", metric_id: "net_sales", unit: "money" as const }],
    rows: Array.from({ length: rows }, () => [...dims.map(() => "x"), "1"]),
  },
});

describe("allowedTypes", () => {
  it("oy kesimi: chiziqli, maydonli, ustunli, ulush emas (vaqt)", () => {
    expect(allowedTypes(widget(["month"], 4))).toEqual(["line", "area", "bar", "pie", "funnel", "table"]);
  });
  it("kesimsiz bitta qator: KPI yoki jadval", () => {
    expect(allowedTypes(widget([], 1))).toEqual(["kpi", "table"]);
  });
  it("filial kesimi: ustunli, doiraviy, voronka", () => {
    expect(allowedTypes(widget(["branch"], 3))).toEqual(["bar", "pie", "funnel", "table"]);
  });
  it("ikki kesim: ustma-ust va issiqlik xaritasi; ko‘p a’zoda doiraviy yo‘q", () => {
    expect(allowedTypes(widget(["month", "branch"], 20))).toEqual(
      ["line", "area", "bar", "stacked_bar", "heatmap", "table"]);
    expect(allowedTypes(widget(["product"], 40))).toEqual(["bar", "funnel", "table"]);
  });
});
