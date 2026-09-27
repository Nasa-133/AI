import { describe, expect, it } from "vitest";

import { parseInline, parseMarkdown } from "./parse";

describe("parseMarkdown", () => {
  it("TZ 7.3 javob formatini tuzilmaga ajratadi", () => {
    const blocks = parseMarkdown(
      "**Qisqa javob**\nSof savdo — 850.00 (UZS).\n\n| net_sales |\n|---|\n| 850.00 |\n\n- Birinchi\n- `id` bilan",
    );
    expect(blocks.map((b) => b.kind)).toEqual(["paragraph", "table", "list"]);
    const table = blocks[1];
    expect(table.kind === "table" && table.rows[0][0][0].text).toBe("850.00");
  });

  it("HTML matn sifatida qoladi, teg sifatida emas", () => {
    const [block] = parseMarkdown("<img src=x onerror=alert(1)> **salom**");
    expect(block.kind).toBe("paragraph");
    expect(block.kind === "paragraph" && block.content[0]).toEqual({
      kind: "text", text: "<img src=x onerror=alert(1)> ",
    });
  });

  it("inline bold va code", () => {
    expect(parseInline("a **b** `c`").map((x) => x.kind)).toEqual(["text", "strong", "text", "code"]);
  });
});
