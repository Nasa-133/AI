import { describe, expect, it } from "vitest";

import { buildOption, colorRange, isHorizontal } from "./charts";
import { applyFilter, NO_FILTER, periodRange, previousRange, spanFor } from "./filters";
import type { QueryResult, QuerySpec, Widget } from "./types";

const theme = { text: "#555", border: "#ddd", surface: "#fff", colors: ["#1", "#2"] };
const fmt = (v: number | null) => String(v);
const axis = (v: number) => String(v);

function result(dims: string[], rows: (string | null)[][], unit: "money" | "percent" = "money"): QueryResult {
  return {
    query_spec_id: "q", dataset_snapshot_ids: [], currency: "UZS", notes: [],
    columns: [...dims.map((d) => ({ name: d, kind: "dimension", metric_id: null, unit: null })),
              { name: "m", kind: "metric", metric_id: "net_sales", unit }],
    rows,
  };
}

describe("buildOption", () => {
  it("doiraviy: nom ustuni yorliq, qiymatlar ulush", () => {
    const o = buildOption(result(["branch", "branch_name"], [["TOS", "Toshkent", "70"], ["SAM", "Samarqand", "30"]]),
                          "pie", {}, theme, fmt, axis) as { series: { type: string; data: unknown[] }[] };
    expect(o.series[0].type).toBe("pie");
    expect(o.series[0].data).toEqual([{ name: "Toshkent", value: 70 }, { name: "Samarqand", value: 30 }]);
  });
  it("issiqlik xaritasi: x — birinchi kesim, y — ikkinchi", () => {
    const o = buildOption(result(["month", "branch"], [["2026-01", "TOS", "20"], ["2026-01", "SAM", "-8"],
                                                       ["2026-02", "TOS", "22"]], "percent"),
                          "heatmap", {}, theme, fmt, axis) as {
      xAxis: { data: string[] }; yAxis: { data: string[] }; series: { data: number[][] }[] };
    expect(o.xAxis.data).toEqual(["2026-01", "2026-02"]);
    expect(o.yAxis.data).toEqual(["TOS", "SAM"]);
    expect(o.series[0].data).toContainEqual([0, 1, -8]);
  });
  it("ustma-ust: ikkinchi kesim — qatlamlar, bo‘sh katak null", () => {
    const o = buildOption(result(["month", "branch"], [["2026-01", "TOS", "5"], ["2026-02", "SAM", "3"]]),
                          "stacked_bar", {}, theme, fmt, axis) as { series: { name: string; data: (number | null)[] }[] };
    expect(o.series.map((s) => s.name)).toEqual(["TOS", "SAM"]);
    expect(o.series[0].data).toEqual([5, null]);
  });
  it("ko‘p a’zoli ustunli grafik yotiq bo‘ladi (top-N)", () => {
    expect(isHorizontal(["A", "B"])).toBe(false);
    expect(isHorizontal(Array.from({ length: 10 }, (_, i) => `P${i}`))).toBe(true);
    expect(isHorizontal(["Kungaboqar yog‘i 50 li"])).toBe(true);
  });
});

describe("filters", () => {
  const today = new Date(Date.UTC(2026, 8, 28));
  it("davr presetlari", () => {
    expect(periodRange("last_month", today)).toEqual({ from: "2026-08-01", to: "2026-08-31" });
    expect(periodRange("last_3", today)).toEqual({ from: "2026-06-01", to: "2026-08-31" });
    expect(periodRange("ytd", today)).toEqual({ from: "2026-01-01", to: "2026-09-28" });
  });
  it("oldingi teng davr", () => {
    expect(previousRange({ from: "2026-06-01", to: "2026-08-31" })).toEqual({ from: "2026-03-01", to: "2026-05-31" });
    expect(previousRange({ from: "2026-09-01", to: "2026-09-28" })).toEqual({ from: "2026-08-04", to: "2026-08-31" });
  });
  it("filtr so‘rovga qo‘llanadi; filtrsiz — null", () => {
    const spec: QuerySpec = { metric_ids: ["net_sales"], date_range: { from: "2026-01-01", to: "2026-01-31" },
                              dimensions: ["month"], filters: {}, currency: "UZS" };
    expect(applyFilter(spec, NO_FILTER, today)).toBeNull();
    const f = applyFilter(spec, { period: "last_month", branches: ["SAM"] }, today)!;
    expect(f.date_range).toEqual({ from: "2026-08-01", to: "2026-08-31" });
    expect(f.filters.branch_codes).toEqual(["SAM"]);
  });
  it("to‘r kengligi turiga qarab", () => {
    const w = (type: Widget["type"]) => ({ type, data: null } as unknown as Widget);
    expect([spanFor(w("kpi")), spanFor(w("pie")), spanFor(w("bar")), spanFor(w("text"))]).toEqual([3, 6, 6, 12]);
  });
});

describe("colorRange", () => {
  it("bitta keskin qiymat shkalani cho‘zmaydi", () => {
    const r = colorRange([-28, 21, 22, 22.5, 23, 23.5, 24, 24.5, 25, 25.3]);
    expect(r.min).toBeGreaterThan(20);
    expect(r.max).toBeLessThanOrEqual(25.3);
  });
  it("bo‘sh yoki bir xil qiymatlar", () => {
    expect(colorRange([])).toEqual({ min: 0, max: 1 });
    expect(colorRange([5, 5])).toEqual({ min: 5, max: 6 });
  });
});
