import { describe, expect, it } from "vitest";

import { formatValue } from "./number";

describe("formatValue", () => {
  it("pul, foiz, son", () => {
    expect(formatValue("1234567.5", "money", "UZS")).toBe("1 234 567,50 so‘m");
    expect(formatValue("-100.00", "money", "USD")).toBe("−100,00 USD");
    expect(formatValue("41.18", "percent")).toBe("41,18 %");
    expect(formatValue("12", "count")).toBe("12");
    expect(formatValue(null, "money", "UZS")).toBe("—");
  });
});
