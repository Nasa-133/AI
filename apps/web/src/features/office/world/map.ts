/**
 * Ofis xaritasi (tepadan ko‘rinish): xonalar, devorlar, eshiklar, mebel va agent joylari.
 * Hammasi katak (tile) koordinatalarida; to‘siqlar (devor, mebel) yo‘l topishda yopiq kataklar.
 */

export const TILE = 16;
export const COLS = 60;
export const ROWS = 36;
export const WORLD_W = COLS * TILE;
export const WORLD_H = ROWS * TILE;

export type Point = { x: number; y: number };
export type Rect = { x: number; y: number; w: number; h: number };

export type RoomKind = "department" | "meeting" | "lounge" | "hall";
export type Room = Rect & {
  id: string; name: string; kind: RoomKind;
  /** Devordagi eshik kataklari (devor chizig‘ida ochiq qoladi). */
  doors: Point[];
};

export type FurnitureKind = "desk" | "table" | "sofa" | "plant" | "cabinet" | "coffee";
export type Furniture = Rect & { kind: FurnitureKind; owner?: string };

/** Agentning ish joyi (stol oldidagi stul) va bo‘sh vaqtdagi joyi (dam olish zonasi). */
/** `restLabelBelow` — dam olish joyida yorliq agent ostida (qo‘shnilar bilan ustma-ust tushmasin). */
export type Seat = { role: string; room: string; work: Point; rest: Point; restLabelBelow?: boolean };

const doorRow = (x: number, y: number, n = 3): Point[] =>
  Array.from({ length: n }, (_, i) => ({ x: x + i, y }));

export const ROOMS: Room[] = [
  { id: "coordinator", name: "Koordinator kabineti", kind: "department", x: 0, y: 0, w: 16, h: 15,
    doors: doorRow(6, 14) },
  { id: "sales", name: "Savdo bo‘limi", kind: "department", x: 15, y: 0, w: 19, h: 15,
    doors: doorRow(23, 14) },
  { id: "finance", name: "Moliya bo‘limi", kind: "department", x: 33, y: 0, w: 19, h: 15,
    doors: doorRow(41, 14) },
  { id: "meeting", name: "Majlis xonasi", kind: "meeting", x: 51, y: 0, w: 9, h: 15,
    doors: doorRow(54, 14) },
  { id: "inventory", name: "Ombor bo‘limi", kind: "department", x: 0, y: 21, w: 21, h: 15,
    doors: doorRow(9, 21) },
  { id: "documents", name: "Hujjatlar bo‘limi", kind: "department", x: 20, y: 21, w: 21, h: 15,
    doors: doorRow(29, 21) },
  { id: "lounge", name: "Dam olish zonasi", kind: "lounge", x: 40, y: 21, w: 20, h: 15,
    doors: doorRow(45, 21, 5) },
];

/** Koridor: xonalar orasidagi ochiq zal (devorsiz, faqat tashqi devor). */
export const HALL: Rect = { x: 0, y: 14, w: COLS, h: 8 };

function deskGroup(x: number, y: number, owner?: string): Furniture[] {
  return [{ kind: "desk", x, y, w: 4, h: 2, owner }];
}

export const FURNITURE: Furniture[] = [
  // Koordinator
  ...deskGroup(6, 4, "coordinator"),
  { kind: "cabinet", x: 1, y: 1, w: 4, h: 1 },
  { kind: "plant", x: 13, y: 1, w: 1, h: 1 },
  { kind: "table", x: 5, y: 9, w: 5, h: 2 },
  // Savdo: agent stoli va hamkasblar stollari (bo‘sh)
  ...deskGroup(18, 4, "sales_analyst"), ...deskGroup(25, 4), ...deskGroup(18, 9), ...deskGroup(25, 9),
  { kind: "plant", x: 31, y: 1, w: 1, h: 1 },
  // Moliya
  ...deskGroup(36, 4, "finance_analyst"), ...deskGroup(43, 4), ...deskGroup(36, 9), ...deskGroup(43, 9),
  { kind: "cabinet", x: 49, y: 2, w: 1, h: 4 },
  // Majlis
  { kind: "table", x: 53, y: 4, w: 4, h: 6 },
  // Ombor
  ...deskGroup(4, 25, "inventory_analyst"),
  { kind: "cabinet", x: 12, y: 23, w: 1, h: 6 }, { kind: "cabinet", x: 16, y: 23, w: 1, h: 6 },
  { kind: "cabinet", x: 12, y: 31, w: 6, h: 1 },
  // Hujjatlar
  ...deskGroup(24, 25, "document_assistant"), ...deskGroup(31, 25), ...deskGroup(24, 30),
  { kind: "cabinet", x: 38, y: 23, w: 1, h: 5 },
  // Dam olish
  // Divan va stol orasida ikki qator bo‘sh joy: o‘tirgan agentlar yo‘lni to‘sib qo‘ymaydi.
  { kind: "sofa", x: 42, y: 27, w: 13, h: 1 }, { kind: "table", x: 44, y: 30, w: 9, h: 1 },
  { kind: "sofa", x: 42, y: 34, w: 13, h: 1 },
  { kind: "coffee", x: 56, y: 23, w: 2, h: 1 },
  { kind: "plant", x: 57, y: 33, w: 1, h: 1 }, { kind: "plant", x: 57, y: 26, w: 1, h: 1 },
];

/** Ish joyi — stolning pastki chetidagi stul (stoldan keyingi qator, o‘rtada). */
export const SEATS: Seat[] = [
  // Dam olish joylari bir-biridan 4 katak uzoqda — ism yorliqlari ustma-ust tushmaydi.
  { role: "coordinator", room: "coordinator", work: { x: 8, y: 6 }, rest: { x: 43, y: 28 } },
  { role: "sales_analyst", room: "sales", work: { x: 20, y: 6 }, rest: { x: 48, y: 28 },
    restLabelBelow: true },
  { role: "finance_analyst", room: "finance", work: { x: 38, y: 6 }, rest: { x: 53, y: 28 } },
  { role: "inventory_analyst", room: "inventory", work: { x: 6, y: 27 }, rest: { x: 45, y: 33 },
    restLabelBelow: true },
  { role: "document_assistant", room: "documents", work: { x: 26, y: 27 }, rest: { x: 51, y: 33 } },
];

export function seatOf(role: string): Seat {
  return SEATS.find((s) => s.role === role) ?? SEATS[0];
}

/** Yopiq kataklar: tashqi devor, xona devorlari (eshiklardan tashqari), mebel. */
export function buildGrid(): boolean[][] {
  const blocked = Array.from({ length: ROWS }, () => Array<boolean>(COLS).fill(false));
  const mark = (x: number, y: number, v = true) => {
    if (x >= 0 && y >= 0 && x < COLS && y < ROWS) blocked[y][x] = v;
  };
  for (const room of ROOMS) {
    for (let x = room.x; x < room.x + room.w; x++) { mark(x, room.y); mark(x, room.y + room.h - 1); }
    for (let y = room.y; y < room.y + room.h; y++) { mark(room.x, y); mark(room.x + room.w - 1, y); }
  }
  for (let x = 0; x < COLS; x++) { mark(x, 0); mark(x, ROWS - 1); }
  for (let y = 0; y < ROWS; y++) { mark(0, y); mark(COLS - 1, y); }
  for (const room of ROOMS) for (const d of room.doors) mark(d.x, d.y, false);
  for (const f of FURNITURE) {
    for (let y = f.y; y < f.y + f.h; y++) for (let x = f.x; x < f.x + f.w; x++) mark(x, y);
  }
  return blocked;
}

export const tileCenter = (p: Point): Point => ({ x: (p.x + 0.5) * TILE, y: (p.y + 0.5) * TILE });
export const toTile = (p: Point): Point => ({ x: Math.floor(p.x / TILE), y: Math.floor(p.y / TILE) });

/** Devor kataklarini chizish uchun gorizontal bo‘laklarga birlashtirish. */
export function wallRuns(grid: boolean[][]): Rect[] {
  const furniture = new Set<string>();
  for (const f of FURNITURE) {
    for (let y = f.y; y < f.y + f.h; y++) for (let x = f.x; x < f.x + f.w; x++) furniture.add(`${x},${y}`);
  }
  const runs: Rect[] = [];
  for (let y = 0; y < ROWS; y++) {
    let start = -1;
    for (let x = 0; x <= COLS; x++) {
      const wall = x < COLS && grid[y][x] && !furniture.has(`${x},${y}`);
      if (wall && start < 0) start = x;
      if (!wall && start >= 0) { runs.push({ x: start, y, w: x - start, h: 1 }); start = -1; }
    }
  }
  return runs;
}
