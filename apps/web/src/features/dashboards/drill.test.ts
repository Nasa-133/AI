import { describe, expect, it } from "vitest";

import { canDrill, drillQuery, loadView, saveView, toSeries } from "./drill";
import type { QuerySpec } from "./types";

const base: QuerySpec = {
  metric_ids: ["net_sales"], date_range: { from: "2026-01-01", to: "2026-06-30" },
  dimensions: ["month"], filters: {}, currency: null,
};

describe("drill-down", () => {
  it("oy → filial: davr tanlangan oyga torayadi (fevral, kabisa emas)", () => {
    expect(drillQuery(base, "2026-02")).toMatchObject({
      date_range: { from: "2026-02-01", to: "2026-02-28" }, dimensions: ["branch"],
    });
  });

  it("filial → mahsulot: filtr qo‘shiladi, metrika o‘zgarmaydi", () => {
    const branch = { ...base, dimensions: ["branch"] };
    expect(drillQuery(branch, "TOS")).toMatchObject({
      dimensions: ["product"], filters: { branch_codes: ["TOS"] }, metric_ids: ["net_sales"],
    });
  });

  it("qo‘llanmagan kesim kliklanmaydi (TZ 8.1)", () => {
    expect(canDrill({ ...base, dimensions: ["customer"] }, "M1")).toBe(false);
    expect(canDrill({ ...base, dimensions: [] }, "x")).toBe(false);
    expect(canDrill(null, "x")).toBe(false);
  });

  it("toSeries nom ustunini yorliq sifatida oladi", () => {
    const s = toSeries({
      query_spec_id: "q", dataset_snapshot_ids: [], currency: "UZS", notes: [],
      columns: [
        { name: "branch", kind: "dimension", metric_id: null, unit: null },
        { name: "branch_name", kind: "dimension", metric_id: null, unit: null },
        { name: "net_sales", kind: "metric", metric_id: "net_sales", unit: "money" },
      ],
      rows: [["TOS", "Toshkent", "850.00"], ["SAM", null, null]],
    });
    expect(s.labels).toEqual(["Toshkent", "SAM"]);
    expect(s.series[0].values).toEqual([850, null]);
  });

  it("ko‘rinish holati ID bo‘yicha saqlanadi va buzilgan qiymatga chidamli", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v),
    } as unknown as Storage;
    saveView("d1", { steps: [] }, storage);
    expect(loadView("d1", storage)).toEqual({ steps: [] });
    store.set("abo.dashboard.d2", "{buzuq");
    expect(loadView("d2", storage)).toEqual({ steps: [] });
  });
});
