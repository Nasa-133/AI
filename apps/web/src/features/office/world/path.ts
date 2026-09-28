import type { Point } from "./map";

/**
 * A* yo‘l topish (4 yo‘nalish, Manhattan evristikasi). Yopiq kataklardan (devor, mebel) o‘tmaydi.
 * Natija — boshlang‘ich katakdan keyingi kataklar ketma-ketligi (maqsad ham kiradi); yo‘l bo‘lmasa null.
 */
export function findPath(grid: boolean[][], from: Point, to: Point): Point[] | null {
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  const inside = (p: Point) => p.x >= 0 && p.y >= 0 && p.x < cols && p.y < rows;
  if (!inside(from) || !inside(to) || grid[to.y][to.x]) return null;
  if (from.x === to.x && from.y === to.y) return [];
  const key = (p: Point) => p.y * cols + p.x;
  const h = (p: Point) => Math.abs(p.x - to.x) + Math.abs(p.y - to.y);

  const g = new Map<number, number>([[key(from), 0]]);
  const came = new Map<number, number>();
  // Kichik ochiq ro‘yxat (xarita ~2000 katak) — oddiy massiv yetarli.
  const open: { p: Point; f: number }[] = [{ p: from, f: h(from) }];
  const closed = new Set<number>();
  const dirs = [{ x: 1, y: 0 }, { x: -1, y: 0 }, { x: 0, y: 1 }, { x: 0, y: -1 }];

  while (open.length) {
    let best = 0;
    for (let i = 1; i < open.length; i++) if (open[i].f < open[best].f) best = i;
    const { p } = open.splice(best, 1)[0];
    const k = key(p);
    if (p.x === to.x && p.y === to.y) {
      const path: Point[] = [];
      let cur = k;
      while (cur !== key(from)) {
        path.push({ x: cur % cols, y: Math.floor(cur / cols) });
        cur = came.get(cur)!;
      }
      return path.reverse();
    }
    if (closed.has(k)) continue;
    closed.add(k);
    for (const d of dirs) {
      const n = { x: p.x + d.x, y: p.y + d.y };
      // Boshlang‘ich katak yopiq bo‘lishi mumkin (masalan, eski joy) — undan chiqishga ruxsat.
      if (!inside(n) || grid[n.y][n.x]) continue;
      const nk = key(n);
      const cost = (g.get(k) ?? 0) + 1;
      if (cost < (g.get(nk) ?? Infinity)) {
        g.set(nk, cost);
        came.set(nk, k);
        open.push({ p: n, f: cost + h(n) });
      }
    }
  }
  return null;
}

/** Eng yaqin ochiq katak (agent qandaydir sabab bilan yopiq katakda qolsa). */
export function nearestOpen(grid: boolean[][], p: Point): Point {
  if (!grid[p.y]?.[p.x]) return p;
  for (let r = 1; r < 20; r++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        const q = { x: p.x + dx, y: p.y + dy };
        if (grid[q.y]?.[q.x] === false) return q;
      }
    }
  }
  return p;
}
