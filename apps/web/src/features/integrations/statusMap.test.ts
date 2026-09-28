import { describe, expect, it } from "vitest";

import type { DiscoveredEntity } from "./api";
import { canonicalOptions, statusValues } from "./statusMap";

function entity(name: string, column: string, values: string[]): DiscoveredEntity {
  return {
    entity: name, source_name: "x", match_score: 1, columns: ["id", column],
    sample_rows: values.map((v, i) => [String(i), v]),
    suggested_mapping: [{ canonical_field: "status", source_column: column, transform: "status_map", constant: null }],
    unmapped_required_fields: [],
  } as unknown as DiscoveredEntity;
}

const asMap = (rows: { source_value: string; canonical_value: string }[]) =>
  Object.fromEntries(rows.map((r) => [r.source_value, r.canonical_value]));

describe("statusValues", () => {
  it("o‘zbekcha eksport — standart oila", () => {
    expect(asMap(statusValues(entity("sales.order_line", "Holat", ["tasdiqlangan"])))).toEqual(
      { tasdiqlangan: "confirmed", qoralama: "draft", "bekor qilingan": "cancelled" });
  });

  it("ERP API (inglizcha) — namunada yo‘q holatlar ham xaritada", () => {
    expect(asMap(statusValues(entity("sales.order_line", "state", ["posted", "posted"])))).toEqual(
      { posted: "confirmed", draft: "draft", cancelled: "cancelled" });
  });

  it("ombor harakati — tur qiymatlari, noma’lumi bo‘sh (foydalanuvchi tanlaydi)", () => {
    const rows = asMap(statusValues(entity("inventory.movement", "kind", ["sale", "write_off"])));
    expect(rows.receipt).toBe("receipt");
    expect(rows.sale).toBe("sale");
    expect(rows.write_off).toBe("");
    expect(canonicalOptions("inventory.movement")).toContain("transfer_out");
    expect(canonicalOptions("sales.return")).toEqual(["confirmed", "draft", "cancelled"]);
  });
});
