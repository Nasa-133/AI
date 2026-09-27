import { describe, expect, it } from "vitest";

import { initialStream, reduceStream } from "./taskStream";

describe("reduceStream", () => {
  it("bosqichlar va yakun", () => {
    let s = reduceStream(initialStream, { type: "task.created", data: { status: "queued" } });
    s = reduceStream(s, { type: "task.progress", data: { phase: "computing", tool_calls_used: 2 } });
    expect(s).toMatchObject({ status: "running", phase: "computing", toolCalls: 2 });
    s = reduceStream(s, { type: "task.completed", data: { status: "partial", limitations: ["x"] } });
    expect(s).toMatchObject({ status: "partial", limitations: ["x"], connection: "closed" });
  });

  it("yopilgan oqimni ulanish xatosi qayta ochmaydi", () => {
    const closed = { ...initialStream, connection: "closed" as const };
    expect(reduceStream(closed, { type: "connection", data: { state: "reconnecting" } }).connection)
      .toBe("closed");
  });
});
