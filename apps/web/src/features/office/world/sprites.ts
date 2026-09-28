/**
 * Piksel-art personajlar (12×16 “piksel”, oldidan ko‘rinish). Har agentning o‘z qiyofasi:
 * soch/kiyim ranglari va belgisi (galstuk, uzun soch, kaska, ko‘zoynak). SVG’da `rect`lar
 * bilan chiziladi (`shape-rendering: crispEdges`) — rasm fayllari kerak emas.
 *
 * Belgilar: H soch, S teri, E ko‘z, M og‘iz, T kiyim, D kiyim soyasi, N galstuk/aksessuar,
 * P shim, B poyabzal, G ko‘zoynak ramkasi, Y kaska, L qo‘l (teri), “.” — bo‘sh.
 */

export const PIXEL = 3; // dunyo birligida bitta “piksel” (personaj ≈ stolning yarmi)
export const SPRITE_W = 12;
export const SPRITE_H = 16;

type Palette = Partial<Record<string, string>>;

const BASE: string[] = [
  "....HHHH....",
  "...HHHHHH...",
  "..HHHHHHHH..",
  "..HSSSSSSH..",
  "..SSESSESS..",
  "..SSSSSSSS..",
  "...SSMMSS...",
  "....SSSS....",
  "..TTTTTTTT..",
  ".TTTTTTTTTT.",
  ".LTTTTTTTTL.",
  ".LTTTTTTTTL.",
  "..DDDDDDDD..",
  "..PPP..PPP..",
  "..PPP..PPP..",
  "..BB....BB..",
];

/** Yurish kadri — oyoqlar navbat bilan (pastki 3 qator). */
export const WALK_LEGS: string[] = [
  "..PPP...PP..",
  ".PPP....PPP.",
  ".BB......BB.",
];

const LONG_HAIR: string[] = [  // Madina: yelkagacha soch
  "....HHHH....",
  "...HHHHHH...",
  "..HHHHHHHH..",
  ".HHSSSSSSHH.",
  ".HSSESSESSH.",
  ".HSSSSSSSSH.",
  ".HHSSMMSSHH.",
  ".HH.SSSS.HH.",
];

const HELMET: string[] = [  // Sardor: ombor kaskasi
  "...YYYYYY...",
  "..YYYYYYYY..",
  ".YYYYYYYYYY.",
  "..HSSSSSSH..",
];

const GLASSES_ROW = "..GEGSGEGS..";  // Dilnoza: ko‘zoynak (ko‘z qatori)

function withTie(rows: string[]): string[] {
  return rows.map((row, i) => (i >= 8 && i <= 11 ? replaceAt(row, 5, "NN") : row));
}

function replaceAt(row: string, index: number, value: string): string {
  return row.slice(0, index) + value + row.slice(index + value.length);
}

export type Look = { rows: string[]; palette: Palette; accent: string };

const SKIN = "#f2c9a0";
const common = { S: SKIN, L: SKIN, E: "#2b2230", M: "#c0605a", B: "#3b3036", G: "#3a3a48" };

export const LOOKS: Record<string, Look> = {
  // Bosh yordamchi: to‘q ko‘k kostyum, qizil galstuk.
  coordinator: {
    rows: withTie(BASE),
    palette: { ...common, H: "#3a2a22", T: "#2f4a86", D: "#263c6d", N: "#d24b4b", P: "#2a2f45" },
    accent: "#3d6fd6",
  },
  // Ali: savdo — yashil futbolka, qora soch.
  sales_analyst: {
    rows: BASE,
    palette: { ...common, H: "#1f1b1d", T: "#2e9c6a", D: "#247d55", P: "#3b4a6b" },
    accent: "#249b67",
  },
  // Madina: moliya — uzun soch, to‘q sariq kofta.
  finance_analyst: {
    rows: [...LONG_HAIR, ...BASE.slice(8)],
    palette: { ...common, H: "#5a3222", T: "#d9822b", D: "#b86a1e", P: "#4a3a52" },
    accent: "#d27a1f",
  },
  // Sardor: ombor — sariq kaska, binafsha ish kiyimi.
  inventory_analyst: {
    rows: [...HELMET, ...BASE.slice(4)],
    palette: { ...common, H: "#2d2320", Y: "#f2c230", T: "#7a54c9", D: "#6243a8", P: "#39394d" },
    accent: "#8a5cd6",
  },
  // Dilnoza: hujjatlar — ko‘zoynak, pushti kofta.
  document_assistant: {
    rows: BASE.map((row, i) => (i === 4 ? GLASSES_ROW : row)),
    palette: { ...common, H: "#2a1d1a", T: "#d9578f", D: "#b8467a", P: "#3c3552" },
    accent: "#d24d87",
  },
};

export type Pixel = { x: number; y: number; w: number; color: string; part: "body" | "legs" | "hands" };

/** Satrlarni bir xil rangli gorizontal bo‘laklarga birlashtiradi (kamroq DOM element). */
export function pixels(look: Look, rows: string[] = look.rows, yOffset = 0): Pixel[] {
  const out: Pixel[] = [];
  rows.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const ch = row[x];
      let end = x + 1;
      while (end < row.length && row[end] === ch) end++;
      const color = look.palette[ch];
      if (ch !== "." && color) {
        const part = ch === "L" ? "hands" : y + yOffset >= SPRITE_H - 3 ? "legs" : "body";
        out.push({ x, y: y + yOffset, w: end - x, color, part });
      }
      x = end;
    }
  });
  return out;
}

export function lookOf(role: string): Look {
  return LOOKS[role] ?? LOOKS.coordinator;
}
