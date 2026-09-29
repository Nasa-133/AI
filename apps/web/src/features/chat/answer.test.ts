import { describe, expect, it } from "vitest";

import { formatNumbersInText } from "@/shared/format/number";

import { humanizeSource, structureAnswer } from "./answer";

const SNAP = "223873e1-b944-403c-9d6b-f3757fbe54cf";
const Q = "773fb3ab-021c-4e82-a598-6dbb9d6454d2";
const ANSWER = [
  "**Qisqa javob**", "Avgust: eng yuqori — TOS.", "",
  "**Asosiy raqamlar**", "| Filial | Sof savdo |", "|---|---|", "| TOS | 623174295.00 |", "",
  "**Taqqoslash** (oldingi davr: 2026-07-01 — 2026-07-31)", "| Filial | Joriy |", "|---|---|", "| TOS | 1.00 |", "",
  "**Harakat variantlari**", "- Dashboard yaratish.", "",
  "**Manbalar va cheklovlar**",
  `- Dataset snapshot: \`${SNAP}\``,
  `- Query: \`${Q}\`; davr: 2026-08-01 — 2026-08-31; valyuta: UZS; hisoblangan: 2026-09-29T04:38:33.669661+00:00`,
  "- Bir nechta valyuta: natija valyuta bo‘yicha ajratilgan, qo‘shilmagan.",
].join("\n");
const REFS = [{ kind: "dataset_snapshot", id: SNAP, version_id: null, locator: "sales.order_line" },
              { kind: "query_result", id: Q, version_id: null, locator: null }];

describe("structureAnswer", () => {
  it("xulosa, raqamlar, keyingi qadam alohida; qo‘shimcha bo‘lim yig‘iladi", () => {
    const a = structureAnswer(ANSWER, REFS)!;
    expect(a.lead).toHaveLength(1);
    expect(a.numbers?.blocks[0].kind).toBe("table");
    expect(a.next?.title).toBe("Harakat variantlari");
    expect(a.extra.map((s) => [s.title, s.note])).toEqual([["Taqqoslash", "oldingi davr: 2026-07-01 — 2026-07-31"]]);
  });

  it("manbalar insoniy nom bilan; UUID faqat raw’da; ogohlantirish yashirilmaydi", () => {
    const a = structureAnswer(ANSWER, REFS)!;
    expect(a.sources.map((s) => s.label)).toEqual([
      "Ma’lumot: Sotuvlar",
      expect.stringMatching(/^Hisob: davr: 2026-08-01 — 2026-08-31 · valyuta: UZS · hisoblandi \d\d\.09\.2026 \d\d:\d\d$/),
    ]);
    expect(a.sources.every((s) => !s.label.includes(SNAP) && !s.label.includes(Q))).toBe(true);
    expect(a.sources[1].raw).toContain(Q);
    expect(a.notices).toEqual(["Bir nechta valyuta: natija valyuta bo‘yicha ajratilgan, qo‘shilmagan."]);
  });

  it("bir qatordagi “**Qisqa javob** matn” ham tushuniladi; tuzilmasiz javob — null", () => {
    const a = structureAnswer("**Qisqa javob** Dashboard yaratildi: **X**.\n\n**Manbalar va cheklovlar**\n"
      + `- Dashboard yaratildi: X (\`${Q}\`, versiya 1).`, [])!;
    expect(a.lead[0].kind).toBe("paragraph");
    expect(a.sources[0].label).toBe("Dashboard yaratildi: X (versiya 1).");
    expect(structureAnswer("Oddiy javob, **muhim** so‘z bilan.", [])).toBeNull();
  });

  it("humanizeSource: noma’lum manba nomisiz qolmaydi", () => {
    expect(humanizeSource(`Dataset snapshot: \`${SNAP}\``, [], 0)).toBe("Ma’lumot to‘plami");
  });
});

describe("formatNumbersInText", () => {
  it("o‘nli sonlarni guruhlaydi, sana va yilga tegmaydi", () => {
    expect(formatNumbersInText("TOS (623174295.00) va 4336.83, -96033635.00; 19.58%").replace(/\s/g, " "))
      .toBe("TOS (623 174 295,00) va 4 336,83, −96 033 635,00; 19,58%");
    expect(formatNumbersInText("2026-08-01 — 2026-08-31, 2026 yil, v1")).toBe("2026-08-01 — 2026-08-31, 2026 yil, v1");
  });
});
