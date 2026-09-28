import type { AgentStateKey } from "../api";
import { buildGrid, seatOf, tileCenter, toTile, TILE, type Point } from "./map";
import { findPath, nearestOpen } from "./path";

/**
 * Agentlar harakati faqat backend holatidan: vazifa bor (navbat, o‘qish, tahlil, tayyorlash,
 * javob kutish, yakuniy holat) — o‘z stoli; `idle` — dam olish zonasidagi o‘z joyi.
 * Tasodifiy yurish yo‘q. Modul darajasidagi holat: sahifa/oyna almashganda ham saqlanadi.
 */
export type Place = "desk" | "rest";
export const SPEED = 4 * TILE; // px/s

export function placeFor(state: AgentStateKey): Place {
  return state === "idle" ? "rest" : "desk";
}

/** Stolda ishlash animatsiyasi faqat faol ish holatlarida (yakuniy holatda — to‘xtaydi). */
export const WORKING: ReadonlySet<AgentStateKey> = new Set(["reading", "analyzing", "drafting"]);

export type Walker = {
  role: string;
  pos: Point; // px, katak markazi bo‘yicha
  path: Point[]; // qolgan kataklar
  place: Place;
  target: Point; // katak
  facing: -1 | 1;
};

export class OfficeSim {
  readonly grid = buildGrid();
  readonly walkers = new Map<string, Walker>();

  /** Backend holati kelganda: joy o‘zgargan bo‘lsa yangi yo‘l. `instant` — reduced-motion. */
  sync(role: string, state: AgentStateKey, instant = false): Walker {
    const place = placeFor(state);
    const seat = seatOf(role);
    const target = place === "desk" ? seat.work : seat.rest;
    let w = this.walkers.get(role);
    if (!w) {
      // Birinchi ko‘rinish: agent o‘z joyida (yurib kelayotgandek ko‘rsatilmaydi).
      w = { role, pos: tileCenter(target), path: [], place, target, facing: 1 };
      this.walkers.set(role, w);
      return w;
    }
    if (w.place === place && w.target.x === target.x && w.target.y === target.y) return w;
    w.place = place;
    w.target = target;
    if (instant) {
      w.pos = tileCenter(target);
      w.path = [];
      return w;
    }
    const from = nearestOpen(this.grid, toTile(w.pos));
    w.path = findPath(this.grid, from, target) ?? [];
    if (!w.path.length) w.pos = tileCenter(target); // yo‘l topilmasa (bo‘lmasligi kerak) — joyiga
    return w;
  }

  /** Vaqt qadami; biror agent siljigan bo‘lsa true. */
  step(dt: number): boolean {
    let moved = false;
    for (const w of this.walkers.values()) {
      let budget = SPEED * Math.min(dt, 0.1);
      while (budget > 0 && w.path.length) {
        const next = tileCenter(w.path[0]);
        const dx = next.x - w.pos.x;
        const dy = next.y - w.pos.y;
        const dist = Math.hypot(dx, dy);
        if (dx !== 0) w.facing = dx > 0 ? 1 : -1;
        if (dist <= budget) {
          w.pos = next;
          w.path.shift();
          budget -= dist;
        } else {
          w.pos = { x: w.pos.x + (dx / dist) * budget, y: w.pos.y + (dy / dist) * budget };
          budget = 0;
        }
        moved = true;
      }
    }
    return moved;
  }

  at(role: string): Place | "walking" | null {
    const w = this.walkers.get(role);
    if (!w) return null;
    return w.path.length ? "walking" : w.place;
  }
}

export const officeSim = new OfficeSim();
