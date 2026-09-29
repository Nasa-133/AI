import { describe, expect, it } from "vitest";

import { placeLabels } from "./labels";

describe("placeLabels", () => {
  it("yonma-yon agentlar yorlig‘i ustma-ust tushmaydi; muhimi joyida qoladi", () => {
    const out = placeLabels([
      { role: "ali", x: 100, y: 50, w: 40, h: 20, rank: 2 },
      { role: "dilnoza", x: 110, y: 52, w: 60, h: 20, rank: 0 },  // tanlangan
      { role: "far", x: 400, y: 50, w: 40, h: 20, rank: 2 },
    ]);
    expect(out.get("dilnoza")).toBe(0);
    expect(out.get("far")).toBe(0);
    expect(out.get("ali")).toBeLessThanOrEqual(-(2 + 20) + 2);  // dilnoza qutisi ustiga ko‘tarildi
  });
});
