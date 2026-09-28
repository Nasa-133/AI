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
  tile: Point; // oxirgi to‘liq turgan katak
  claim: Point | null; // hozir kirayotgan katak (band)
  waiting: number; // band katak oldida kutilgan vaqt, s
};

const REROUTE_AFTER = 0.5;
const same = (a: Point, b: Point) => a.x === b.x && a.y === b.y;

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
      w = { role, pos: tileCenter(target), path: [], place, target, facing: 1, tile: target,
            claim: null, waiting: 0 };
      this.walkers.set(role, w);
      return w;
    }
    if (w.place === place && same(w.target, target)) return w;
    w.place = place;
    w.target = target;
    if (instant) {
      w.pos = tileCenter(target);
      w.tile = target;
      w.claim = null;
      w.path = [];
      return w;
    }
    // Yarim yo‘lda bo‘lsa — band qilgan katagidan davom etadi (orqaga “sakramaydi”).
    const from = nearestOpen(this.grid, w.claim ?? w.tile ?? toTile(w.pos));
    const path = findPath(this.grid, from, target) ?? [];
    w.path = w.claim && !same(from, w.tile) ? [from, ...path] : path;
    w.waiting = 0;
    if (!w.path.length && !same(w.tile, target)) {
      w.pos = tileCenter(target); // yo‘l topilmasa (bo‘lmasligi kerak) — joyiga
      w.tile = target;
    }
    return w;
  }

  /**
   * Vaqt qadami; biror agent siljigan bo‘lsa true.
   * To‘qnashuvdan qochish: agent boshqa agent turgan yoki band qilgan katakka kirmaydi (kutadi);
   * `REROUTE_AFTER` dan uzoq kutsa, boshqa agentlarni to‘siq deb hisoblab yangi yo‘l topadi.
   */
  step(dt: number): boolean {
    let moved = false;
    const clamped = Math.min(dt, 0.1);
    for (const w of this.walkers.values()) {
      let budget = SPEED * clamped;
      while (budget > 0 && w.path.length) {
        const nextTile = w.path[0];
        if (!w.claim || !same(w.claim, nextTile)) {
          if (this.occupied(w, nextTile)) {
            w.waiting += clamped;
            if (w.waiting >= REROUTE_AFTER) this.reroute(w);
            break;
          }
          w.claim = nextTile;  // katak band qilindi — boshqalar kirmaydi
          w.waiting = 0;
        }
        const next = tileCenter(nextTile);
        const dx = next.x - w.pos.x;
        const dy = next.y - w.pos.y;
        const dist = Math.hypot(dx, dy);
        if (dx !== 0) w.facing = dx > 0 ? 1 : -1;
        if (dist <= budget) {
          w.pos = next;
          w.tile = nextTile;
          w.claim = null;
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

  /** Boshqa agent shu katakda turibdi yoki unga kirish uchun band qilgan. */
  private occupied(self: Walker, tile: Point): boolean {
    for (const other of this.walkers.values()) {
      if (other === self) continue;
      if (same(other.tile, tile) || (other.claim && same(other.claim, tile))) return true;
    }
    return false;
  }

  private reroute(w: Walker): void {
    w.waiting = 0;
    const grid = this.grid.map((row) => [...row]);
    for (const other of this.walkers.values()) {
      if (other === w) continue;
      for (const t of [other.tile, other.claim]) if (t && !same(t, w.target)) grid[t.y][t.x] = true;
    }
    const alternative = findPath(grid, w.tile, w.target);
    if (alternative?.length) w.path = alternative;  // aylanib o‘tish; bo‘lmasa kutishda davom
  }

  at(role: string): Place | "walking" | null {
    const w = this.walkers.get(role);
    if (!w) return null;
    return w.path.length ? "walking" : w.place;
  }
}

export const officeSim = new OfficeSim();
