import { describe, expect, it } from "vitest";

import { stateLabel } from "./api";

describe("stateLabel", () => {
  it("qisman natijani alohida ko‘rsatadi", () => {
    expect(stateLabel({ state: "completed", partial: true })).toBe("Qisman bajardi");
    expect(stateLabel({ state: "completed", partial: false })).toBe("Bajardi");
    expect(stateLabel({ state: "awaiting_input", partial: false })).toBe("Javobingizni kutmoqda");
  });
});
