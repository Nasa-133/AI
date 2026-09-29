/**
 * Ofisning piksel-art ko‘rinishi (tepadan): pol, devor, derazalar, mebel va personajlar.
 * Faqat chizish — holat va harakat OfficeMap/officeSim’da. Sahna palitrasi UI’ga uyg‘un: neytral,
 * past kontrastli pol va devorlar (xonalar yengil ohang bilan farqlanadi) — e’tibor agentlarda.
 *
 * Vizual uslub KbWen/agent-virtual-office (MIT) ilhomida; kod va sprite’lar mustaqil yozilgan.
 */

import { memo } from "react";

import { stateLabel, type OfficeAgent } from "./api";
import styles from "./officeMap.module.css";
import { DECOR, FURNITURE, ROOMS, TILE, WORLD_H, WORLD_W, wallRuns, type Furniture } from "./world/map";
import { officeSim } from "./world/sim";
import { lookOf, PIXEL, pixels, SPRITE_H, SPRITE_W, WALK_LEGS } from "./world/sprites";

const T = TILE;
const FLOOR: Record<string, string> = {
  coordinator: "floor-wood", sales: "floor-wood", finance: "floor-wood2",
  meeting: "floor-lavender", inventory: "floor-concrete", documents: "floor-library",
  lounge: "floor-green",
};

function Patterns() {
  const tile = (id: string, base: string, line: string) => (
    <pattern id={id} width={T} height={T} patternUnits="userSpaceOnUse">
      <rect width={T} height={T} fill={base} />
      <path d={`M0 ${T - 0.5}H${T}M${T - 0.5} 0V${T}`} stroke={line} strokeWidth={1} />
    </pattern>
  );
  return (
    <defs>
      {tile("floor-wood", "#efe7da", "#e8dfd0")}
      {tile("floor-wood2", "#ece5d9", "#e4dccd")}
      {tile("floor-lavender", "#e6e5f1", "#dedcec")}
      {tile("floor-library", "#e3e9f1", "#dae2ec")}
      {tile("floor-concrete", "#e8e9eb", "#e0e2e5")}
      {tile("floor-green", "#e3eee1", "#dae7d7")}
      {tile("floor-hall", "#f5f6f8", "#eff1f4")}
    </defs>
  );
}

function Desk({ f }: { f: Furniture }) {
  const x = f.x * T, y = f.y * T, w = f.w * T, h = f.h * T;
  const cx = x + w / 2;
  return (
    <g data-owner={f.owner} className={styles.desk}>
      <rect x={x + 1} y={y + 2} width={w - 2} height={h - 3} fill="#c2a383" />
      <rect x={x + 1} y={y + 2} width={w - 2} height={3} fill="#d2b797" />
      <rect x={x + 1} y={y + h - 3} width={w - 2} height={2} fill="#a88a6c" />
      {/* monitor, klaviatura, krujka */}
      <rect className={styles.screen} x={cx - 9} y={y + 3} width={18} height={11} fill="#2b2d3a" />
      <rect x={cx - 2} y={y + 14} width={4} height={2} fill="#2b2d3a" />
      <rect x={cx - 7} y={y + 19} width={14} height={4} fill="#dcd6cf" />
      <rect x={x + 6} y={y + 8} width={5} height={6} fill="#f4f1ea" />
      <rect x={x + w - 11} y={y + 10} width={5} height={5} fill={f.owner ? "#e9e1d3" : "#cfc6b8"} />
    </g>
  );
}

function Plant({ f }: { f: Furniture }) {
  const x = f.x * T, y = f.y * T;
  return (
    <g>
      <rect x={x + 4} y={y + 9} width={8} height={6} fill="#b8643c" />
      <rect x={x + 3} y={y + 8} width={10} height={2} fill="#9c5231" />
      <circle cx={x + 5} cy={y + 6} r={4} fill="#4f9a4a" />
      <circle cx={x + 11} cy={y + 6} r={4} fill="#5daa55" />
      <circle cx={x + 8} cy={y + 3} r={4} fill="#6bbb5f" />
    </g>
  );
}

const BOOKS = ["#d98c8c", "#8fa9dd", "#e2bf7f", "#86bea0", "#b09ad9", "#dc9ab8"];

function Shelf({ f, books }: { f: Furniture; books: boolean }) {
  const x = f.x * T, y = f.y * T, w = f.w * T, h = f.h * T;
  const vertical = h > w;
  const slots = Math.floor((vertical ? h : w) / 4);
  return (
    <g>
      <rect x={x + 1} y={y + 1} width={w - 2} height={h - 2} fill="#a9927a" />
      {Array.from({ length: slots }, (_, i) => {
        const color = books ? BOOKS[(i * 7 + f.x) % BOOKS.length] : ["#d3bb9c", "#c7ae8e", "#dcc6a9"][i % 3];
        return vertical
          ? <rect key={i} x={x + 3} y={y + 2 + i * 4} width={w - 6} height={3} fill={color} />
          : <rect key={i} x={x + 2 + i * 4} y={y + 3} width={3} height={h - 6} fill={color} />;
      })}
    </g>
  );
}

function Sofa({ f }: { f: Furniture }) {
  const x = f.x * T, y = f.y * T, w = f.w * T;
  return (
    <g>
      <rect x={x} y={y - 2} width={w} height={T + 4} rx={3} fill="#a3968a" />
      {Array.from({ length: Math.floor(f.w / 2) }, (_, i) => (
        <rect key={i} x={x + 3 + i * 2 * T} y={y + 2} width={2 * T - 6} height={T - 5} rx={2} fill="#c4b8ab" />
      ))}
    </g>
  );
}

function Table({ f }: { f: Furniture }) {
  const x = f.x * T, y = f.y * T, w = f.w * T, h = f.h * T;
  return (
    <g>
      <rect x={x + 1} y={y + 1} width={w - 2} height={h - 2} rx={3} fill="#cdb393" />
      <rect x={x + 4} y={y + 4} width={w - 8} height={h - 8} rx={2} fill="#dac4a8" />
    </g>
  );
}

function FurniturePiece({ f }: { f: Furniture }) {
  switch (f.kind) {
    case "desk": return <Desk f={f} />;
    case "plant": return <Plant f={f} />;
    case "bookshelf": return <Shelf f={f} books />;
    case "shelf": return <Shelf f={f} books={false} />;
    case "sofa": return <Sofa f={f} />;
    case "table": return <Table f={f} />;
    case "coffee":
      return (
        <g>
          <rect x={f.x * T + 1} y={f.y * T} width={f.w * T - 2} height={T} fill="#3b3a44" />
          <rect x={f.x * T + 4} y={f.y * T + 3} width={8} height={5} fill="#35c46a" />
          <circle cx={f.x * T + 22} cy={f.y * T + 8} r={3} fill="#d24b4b" />
        </g>
      );
    default:
      return <rect x={f.x * T + 1} y={f.y * T + 1} width={f.w * T - 2} height={f.h * T - 2} fill="#8d7a66" />;
  }
}

function DecorPiece({ d }: { d: (typeof DECOR)[number] }) {
  const x = d.x * T, y = d.y * T, w = d.w * T, h = d.h * T;
  switch (d.kind) {
    case "window":
      return (
        <g>
          <rect x={x + 1} y={y + 3} width={w - 2} height={h - 6} fill="#8fd0ee" stroke="#e8f4fb" strokeWidth={1.5} />
          <path d={`M${x + w / 2} ${y + 3}V${y + h - 3}`} stroke="#e8f4fb" strokeWidth={1.5} />
        </g>
      );
    case "rug":
      return <rect x={x} y={y} width={w} height={h} rx={4} fill="#9db493" opacity={0.28} />;
    case "kanban":
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} fill="#b3a28f" />
          {[["#f2cf5b", 0, 0], ["#f09a9a", 1, 0], ["#9fd8b8", 0, 1], ["#9cc8f0", 1, 1], ["#f2cf5b", 2, 1]]
            .map(([c, i, j], k) => (
              <rect key={k} x={x + 4 + Number(i) * 18} y={y + 4 + Number(j) * 13} width={14} height={9} fill={String(c)} />
            ))}
        </g>
      );
    case "whiteboard":
      return (
        <g>
          <rect x={x} y={y + 2} width={w} height={h - 2} fill="#f4f6f8" stroke="#9aa3ad" />
          <path d={`M${x + 5} ${y + 7}h${w - 16}`} stroke="#5b8ad6" strokeWidth={1.5} />
          <rect x={x + w - 9} y={y + 4} width={6} height={6} fill="#f2cf5b" />
        </g>
      );
    case "cooler":
      return (
        <g>
          <rect x={x + 3} y={y + 5} width={10} height={10} fill="#e9eef2" />
          <circle cx={x + 8} cy={y + 5} r={4} fill="#8fd0ee" />
        </g>
      );
    case "clock":
      return <circle cx={x + 8} cy={y + 8} r={5} fill="#f4f1ea" stroke="#8a929e" strokeWidth={1.5} />;
  }
}

/** Statik qatlam: pol, devor, derazalar, bezak va mebel. Bir marta chiziladi. */
export const OfficeStatic = memo(function OfficeStatic() {
  const walls = wallRuns(officeSim.grid);
  return (
    <g shapeRendering="crispEdges" className={styles.static}>
      <Patterns />
      <rect x={0} y={0} width={WORLD_W} height={WORLD_H} fill="url(#floor-hall)" />
      {ROOMS.map((r) => (
        <rect key={r.id} x={r.x * T} y={r.y * T} width={r.w * T} height={r.h * T}
              fill={`url(#${FLOOR[r.id] ?? "floor-wood"})`} data-room={r.id} />
      ))}
      {DECOR.filter((d) => d.kind === "rug").map((d, i) => <DecorPiece key={`r${i}`} d={d} />)}
      {walls.map((w, i) => (
        <g key={i}>
          <rect x={w.x * T} y={w.y * T} width={w.w * T} height={w.h * T} fill="#aab2bd" />
          <rect x={w.x * T} y={w.y * T} width={w.w * T} height={3} fill="#c0c7d0" />
        </g>
      ))}
      {DECOR.filter((d) => d.kind !== "rug").map((d, i) => <DecorPiece key={`d${i}`} d={d} />)}
      {FURNITURE.map((f, i) => <FurniturePiece key={i} f={f} />)}
    </g>
  );
});

/** Personaj: piksel sprite, stul soyasi, ish paytida qo‘llar, yurishda oyoqlar almashadi. */
export function AgentSprite({ agent }: { agent: OfficeAgent }) {
  const look = lookOf(agent.role_key);
  const body = pixels(look).filter((p) => p.part !== "legs");
  const legs = pixels(look).filter((p) => p.part === "legs");
  const walk = pixels(look, WALK_LEGS, SPRITE_H - 3);
  const ox = -(SPRITE_W * PIXEL) / 2;
  const oy = 8 - SPRITE_H * PIXEL;  // oyoqlar katak markazidan biroz pastda
  const px = (p: (typeof body)[number], i: number, extra?: object) => (
    <rect key={i} x={ox + p.x * PIXEL} y={oy + p.y * PIXEL} width={p.w * PIXEL} height={PIXEL}
          fill={p.color} {...extra} />
  );
  return (
    <g shapeRendering="crispEdges">
      <ellipse cx={0} cy={9} rx={15} ry={5} className={styles.shadow} />
      <g data-body>
        {body.filter((p) => p.part === "body").map((p, i) => px(p, i))}
        <g data-hand="l">{body.filter((p) => p.part === "hands" && p.x < SPRITE_W / 2).map((p, i) => px(p, i))}</g>
        <g data-hand="r">{body.filter((p) => p.part === "hands" && p.x >= SPRITE_W / 2).map((p, i) => px(p, i))}</g>
        <g data-legs="stand">{legs.map((p, i) => px(p, i))}</g>
        <g data-legs="walk">{walk.map((p, i) => px(p, i))}</g>
      </g>
    </g>
  );
}

/** Nom nishoni (agent rangi) va nutq pufakchasi (haqiqiy holat; o‘z vazifangiz nomi bilan).
 * 0 nuqta — nishonning pastki cheti; masshtab (kameraga teskari) shu nuqta atrofida. */
export function AgentLabel({ agent }: { agent: OfficeAgent }) {
  const look = lookOf(agent.role_key);
  const nameW = agent.name.length * 7.2 + 16;
  const task = agent.current_task?.mine ? agent.current_task.title : null;
  const line2 = task && task.length > 30 ? `${task.slice(0, 29)}…` : task;
  const status = stateLabel(agent);
  const bubbleW = Math.max(status.length * 6.4, (line2?.length ?? 0) * 5.6) + 20;
  const bubbleH = line2 ? 30 : 18;
  return (
    <g>
      {agent.state !== "idle" && (
        <g className={styles.bubble} data-state={agent.state} transform={`translate(0,${-26 - bubbleH})`}>
          <rect x={-bubbleW / 2} y={0} width={bubbleW} height={bubbleH} rx={8} />
          <path d={`M-5 ${bubbleH - 0.5}L0 ${bubbleH + 6}L5 ${bubbleH - 0.5}`} />
          <text className={styles.bubbleStatus} textAnchor="middle" y={12.5}>{status}</text>
          {line2 && <text className={styles.bubbleTask} textAnchor="middle" y={24.5}>{line2}</text>}
        </g>
      )}
      <g className={styles.nameTag}>
        <rect x={-nameW / 2} y={-19} width={nameW} height={18} rx={9} fill={look.accent} />
        <text className={styles.name} textAnchor="middle" y={-6}>{agent.name}</text>
        <circle className={styles.workDot} cx={nameW / 2 - 2} cy={-17} r={4} />
      </g>
    </g>
  );
}

export function accentOf(role: string): string {
  return lookOf(role).accent;
}
