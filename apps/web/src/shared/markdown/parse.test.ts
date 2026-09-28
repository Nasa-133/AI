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

describe("iqtibos va kursiv", () => {
  it("> satrlarini matn sifatida iqtibosga yig‘adi", () => {
    const blocks = parseMarkdown("Hujjatda:\n\n> To‘lov **30** kun\n> <b>x</b>\n\n— *Shartnoma*, v1");
    expect(blocks[1]).toEqual({ kind: "quote", text: "To‘lov **30** kun\n<b>x</b>" });
    expect(blocks[2]).toEqual({ kind: "paragraph", content: [
      { kind: "text", text: "— " }, { kind: "em", text: "Shartnoma" }, { kind: "text", text: ", v1" }] });
  });

  it("ko‘paytirish belgisini kursiv deb olmaydi", () => {
    expect(parseInline("2 * 3 = 6")).toEqual([{ kind: "text", text: "2 * 3 = 6" }]);
  });
});
