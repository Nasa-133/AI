import { describe, expect, it } from "vitest";

import { clamp, fit, MAX_W, MIN_W, pan, zoomAt } from "./camera";
import { buildGrid, FURNITURE, ROOMS, SEATS, tileCenter, toTile, WORLD_W } from "./map";
import { findPath } from "./path";
import { OfficeSim, placeFor, SPEED } from "./sim";

const grid = buildGrid();

describe("xarita", () => {
  it("ish va dam olish joylari ochiq va bir-biridan yetib boriladi", () => {
    for (const seat of SEATS) {
      expect(grid[seat.work.y][seat.work.x]).toBe(false);
      expect(grid[seat.rest.y][seat.rest.x]).toBe(false);
      for (const other of SEATS) {
        expect(findPath(grid, seat.work, other.rest), `${seat.role} → ${other.role}`).not.toBeNull();
        expect(findPath(grid, seat.rest, other.work)).not.toBeNull();
      }
    }
  });

  it("har ish joyi o‘z xonasida va o‘z stoliga tegib turadi", () => {
    for (const seat of SEATS) {
      const room = ROOMS.find((r) => r.id === seat.room)!;
      expect(seat.work.x).toBeGreaterThan(room.x);
      expect(seat.work.x).toBeLessThan(room.x + room.w - 1);
      expect(seat.work.y).toBeGreaterThan(room.y);
      expect(seat.work.y).toBeLessThan(room.y + room.h - 1);
      const desk = FURNITURE.find((f) => f.owner === seat.role)!;
      expect(seat.work.y).toBe(desk.y + desk.h);  // stolning pastki chetida
      expect(seat.work.x).toBeGreaterThanOrEqual(desk.x);
      expect(seat.work.x).toBeLessThan(desk.x + desk.w);
    }
  });

  it("yo‘l devor va mebeldan o‘tmaydi, qadamlar qo‘shni kataklar", () => {
    for (const a of SEATS) for (const b of SEATS) {
      const path = findPath(grid, a.work, b.work)!;
      let prev = a.work;
      for (const p of path) {
        expect(grid[p.y][p.x]).toBe(false);
        expect(Math.abs(p.x - prev.x) + Math.abs(p.y - prev.y)).toBe(1);
        prev = p;
      }
    }
  });

  it("yopiq maqsadga yo‘l yo‘q", () => {
    const desk = FURNITURE.find((f) => f.kind === "desk")!;
    expect(findPath(grid, SEATS[0].work, { x: desk.x, y: desk.y })).toBeNull();
  });
});

describe("harakat backend holatiga bog‘liq", () => {
  it("holat → joy", () => {
    expect(placeFor("idle")).toBe("rest");
    for (const s of ["queued", "reading", "analyzing", "drafting", "awaiting_input", "completed", "failed"] as const) {
      expect(placeFor(s)).toBe("desk");
    }
  });

  it("vazifa kelganda stoliga yuradi, yetib boradi; stolida bo‘lsa joyida qoladi", () => {
    const sim = new OfficeSim();
    const w = sim.sync("finance_analyst", "idle");
    expect(sim.at("finance_analyst")).toBe("rest");  // birinchi ko‘rinish — joyida
    sim.sync("finance_analyst", "analyzing");
    expect(sim.at("finance_analyst")).toBe("walking");
    const steps = w.path.length;
    for (let i = 0; i < 400 && sim.at("finance_analyst") === "walking"; i++) {
      sim.step(0.05);
      const tile = toTile(w.pos);
      expect(grid[tile.y][tile.x]).toBe(false);  // hech qachon to‘siq ichida emas
    }
    expect(sim.at("finance_analyst")).toBe("desk");
    expect(w.pos).toEqual(tileCenter(SEATS.find((s) => s.role === "finance_analyst")!.work));
    expect(steps).toBeGreaterThan(5);

    sim.sync("finance_analyst", "drafting");  // allaqachon stolida
    expect(sim.at("finance_analyst")).toBe("desk");
    expect(sim.step(0.1)).toBe(false);
  });

  it("reduced-motion’da darhol joyiga o‘tadi; bir nechta agent mustaqil", () => {
    const sim = new OfficeSim();
    sim.sync("sales_analyst", "idle");
    sim.sync("document_assistant", "idle");
    sim.sync("sales_analyst", "reading", true);
    sim.sync("document_assistant", "drafting");
    expect(sim.at("sales_analyst")).toBe("desk");
    expect(sim.at("document_assistant")).toBe("walking");
    sim.step(0.05);
    expect(SPEED).toBeGreaterThan(0);
  });
});

describe("kamera", () => {
  it("yaqinlashtirish chegaralanadi va langar nuqta joyida qoladi", () => {
    let c = fit();
    for (let i = 0; i < 20; i++) c = zoomAt(c, 0.8);
    expect(c.w).toBeCloseTo(MIN_W);
    for (let i = 0; i < 40; i++) c = zoomAt(c, 1.25);
    expect(c.w).toBeCloseTo(MAX_W);
    const start = fit();
    const anchor = { x: 100, y: 100 };
    const z = zoomAt(start, 0.5, anchor);
    // Langarning nisbiy joyi o‘zgarmaydi.
    expect((anchor.x - z.x) / z.w).toBeCloseTo((anchor.x - start.x) / start.w);
  });

  it("surish dunyodan chiqib ketmaydi", () => {
    const c = pan(zoomAt(fit(), 0.3), 10_000, 10_000);
    expect(c.x + c.w / 2).toBeLessThanOrEqual(WORLD_W);
    expect(clamp(c)).toEqual(c);
  });
});
