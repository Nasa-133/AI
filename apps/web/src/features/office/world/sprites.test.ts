import { describe, expect, it } from "vitest";

import { LOOKS, pixels, SPRITE_H, SPRITE_W, WALK_LEGS } from "./sprites";

describe("piksel personajlar", () => {
  it("har qiyofa 12×16 va barcha belgilar palitrada", () => {
    for (const [role, look] of Object.entries(LOOKS)) {
      expect(look.rows, role).toHaveLength(SPRITE_H);
      for (const row of look.rows) {
        expect(row, role).toHaveLength(SPRITE_W);
        for (const ch of row) if (ch !== ".") expect(look.palette[ch], `${role}: ${ch}`).toBeTruthy();
      }
    }
    for (const row of WALK_LEGS) expect(row).toHaveLength(SPRITE_W);
  });

  it("qiyofalar bir-biridan farq qiladi va qo‘l piksellari ajratiladi", () => {
    const signatures = Object.values(LOOKS).map((l) => JSON.stringify(pixels(l)));
    expect(new Set(signatures).size).toBe(signatures.length);
    expect(pixels(LOOKS.coordinator).some((p) => p.part === "hands")).toBe(true);
    expect(pixels(LOOKS.coordinator).some((p) => p.part === "legs")).toBe(true);
  });
});
