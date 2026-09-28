import { WORLD_H, WORLD_W, type Point } from "./map";

/** Kamera — dunyo koordinatalaridagi ko‘rinadigan to‘rtburchak (SVG viewBox). */
export type Camera = { x: number; y: number; w: number; h: number };

export const MIN_W = WORLD_W / 5; // eng yaqin
export const MAX_W = WORLD_W * 1.2; // eng uzoq (butun ofis + chet)

export function fit(): Camera {
  const pad = 16;
  return { x: -pad, y: -pad, w: WORLD_W + pad * 2, h: WORLD_H + pad * 2 };
}

/** Kamera dunyodan juda uzoqqa ketmasin: markaz dunyo chegarasida qoladi. */
export function clamp(c: Camera): Camera {
  const cx = Math.min(Math.max(c.x + c.w / 2, 0), WORLD_W);
  const cy = Math.min(Math.max(c.y + c.h / 2, 0), WORLD_H);
  return { ...c, x: cx - c.w / 2, y: cy - c.h / 2 };
}

/** `factor` < 1 — yaqinlashtirish. `anchor` (dunyo nuqtasi) ekranda joyida qoladi. */
export function zoomAt(c: Camera, factor: number, anchor?: Point): Camera {
  const w = Math.min(Math.max(c.w * factor, MIN_W), MAX_W);
  const k = w / c.w;
  const h = c.h * k;
  const a = anchor ?? { x: c.x + c.w / 2, y: c.y + c.h / 2 };
  return clamp({ x: a.x - (a.x - c.x) * k, y: a.y - (a.y - c.y) * k, w, h });
}

export function pan(c: Camera, dx: number, dy: number): Camera {
  return clamp({ ...c, x: c.x + dx, y: c.y + dy });
}

export function zoomLevel(c: Camera): number {
  return Math.round((fit().w / c.w) * 100);
}
