import { describe, expect, it } from "vitest";

import { contextDocs } from "./contextDocs";

describe("contextDocs", () => {
  it("dublikatsiz qo‘shadi, olib tashlaydi va tozalaydi", () => {
    let calls = 0;
    const off = contextDocs.subscribe(() => { calls += 1; });
    contextDocs.add({ id: "a", title: "A" });
    contextDocs.add({ id: "a", title: "A" });
    contextDocs.add({ id: "b", title: "B" });
    expect(contextDocs.get().map((d) => d.id)).toEqual(["a", "b"]);
    contextDocs.remove("a");
    expect(contextDocs.get().map((d) => d.id)).toEqual(["b"]);
    contextDocs.clear();
    expect(contextDocs.get()).toEqual([]);
    expect(calls).toBe(4);
    off();
  });

  it("10 tadan ko‘p saqlamaydi", () => {
    for (let i = 0; i < 12; i++) contextDocs.add({ id: String(i), title: String(i) });
    expect(contextDocs.get()).toHaveLength(10);
    expect(contextDocs.get()[0].id).toBe("2");
    contextDocs.clear();
  });
});
