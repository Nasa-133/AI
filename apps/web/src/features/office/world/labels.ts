/** Agent yorliqlarini to‘qnashuvsiz joylash (toza funksiya — DOM’siz test qilinadi). */

export type LabelBox = { role: string; x: number; y: number; w: number; h: number; rank: number };

/**
 * Yorliqlarni to‘qnashuvsiz joylash (dunyo birliklarida, joriy masshtab bilan): muhimlik bo‘yicha
 * tartiblanadi, to‘qnashgan yorliq to‘qnashgan qutining ustiga ko‘tariladi. Natija — yuqoriga siljish.
 */
export function placeLabels(boxes: LabelBox[]): Map<string, number> {
  const placed: { l: number; r: number; top: number; bottom: number }[] = [];
  const out = new Map<string, number>();
  const order = [...boxes].sort((a, b) => a.rank - b.rank || b.y - a.y);
  for (const b of order) {
    const l = b.x - b.w / 2 - 2, r = b.x + b.w / 2 + 2;
    let bottom = b.y;
    for (let i = 0; i < 12; i++) {
      const hit = placed.find((p) => l < p.r && r > p.l && bottom > p.top && bottom - b.h < p.bottom);
      if (!hit) break;
      bottom = hit.top - 2;
    }
    placed.push({ l, r, top: bottom - b.h, bottom });
    out.set(b.role, bottom - b.y);
  }
  return out;
}
