"use client";

import { memo, useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent, type PointerEvent } from "react";

import { stateLabel, type OfficeAgent } from "./api";
import styles from "./officeMap.module.css";
import { fit, pan, zoomAt, zoomLevel, type Camera } from "./world/camera";
import { FURNITURE, ROOMS, TILE, WORLD_H, WORLD_W, wallRuns, type Point } from "./world/map";
import { officeSim, WORKING } from "./world/sim";

const COLORS: Record<string, string> = {
  coordinator: "var(--chart-1)", sales_analyst: "var(--chart-2)", finance_analyst: "var(--chart-3)",
  inventory_analyst: "var(--chart-4)", document_assistant: "var(--chart-5)",
};

// Kamera sessiya davomida saqlanadi: dashboard oynasi yoki boshqa sahifadan qaytganda joyida.
let savedCamera: Camera | null = null;

function subscribeMotion(cb: () => void) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Statik qatlam: pol, devorlar, eshiklar, mebel, xona nomlari. Bir marta chiziladi. */
const StaticLayer = memo(function StaticLayer() {
  const walls = wallRuns(officeSim.grid);
  return (
    <g>
      <rect x={0} y={0} width={WORLD_W} height={WORLD_H} className={styles.hall} />
      {ROOMS.map((r) => (
        <rect key={r.id} x={r.x * TILE} y={r.y * TILE} width={r.w * TILE} height={r.h * TILE}
              className={styles.room} data-kind={r.kind} />
      ))}
      {walls.map((w, i) => (
        <rect key={i} x={w.x * TILE} y={w.y * TILE} width={w.w * TILE} height={w.h * TILE} className={styles.wall} />
      ))}
      {FURNITURE.map((f, i) => (
        <g key={i} data-owner={f.owner} className={styles.furniture} data-kind={f.kind}>
          <rect x={f.x * TILE + 1} y={f.y * TILE + 1} width={f.w * TILE - 2} height={f.h * TILE - 2} rx={f.kind === "plant" ? 7 : 3} />
          {f.kind === "desk" && (
            <rect className={styles.monitor} x={(f.x + f.w / 2 - 0.9) * TILE} y={f.y * TILE + 3}
                  width={1.8 * TILE} height={TILE * 0.55} rx={2} />
          )}
        </g>
      ))}
    </g>
  );
});

function RoomLabels() {
  return (
    <g>
      {ROOMS.map((r) => (
        <g key={r.id} className={styles.roomLabel} data-label transform={`translate(${(r.x + 1.3) * TILE},${(r.y + r.h - 1.35) * TILE})`}>
          <text>{r.name}</text>
        </g>
      ))}
    </g>
  );
}

/**
 * Tepadan ko‘rinadigan ofis. Agent joylashuvi `officeSim`dan (backend holati → joy → A* yo‘l),
 * kadrlar requestAnimationFrame’da DOM transform bilan yangilanadi (React qayta chizmaydi).
 * Yorliqlar ekranda doimiy o‘lchamda (kamera masshtabiga teskari).
 */
export function OfficeMap({ agents, selected, onSelect }: {
  agents: OfficeAgent[]; selected: string | null; onSelect: (role: string | null) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const agentRefs = useRef(new Map<string, SVGGElement>());
  const [camera, setCameraState] = useState<Camera>(() => savedCamera ?? fit());
  const reduce = useSyncExternalStore(subscribeMotion, reducedMotion, () => false);
  const drag = useRef<{ pointers: Map<number, Point>; moved: boolean; last: Point | null; dist: number | null }>(
    { pointers: new Map(), moved: false, last: null, dist: null });
  const agentsRef = useRef(agents);

  const setCamera = (update: (c: Camera) => Camera) => {
    setCameraState((c) => { const next = update(c); savedCamera = next; return next; });
  };

  // Backend holati → maqsad joy. Holat o‘zgarmasa yo‘l qayta hisoblanmaydi.
  useEffect(() => {
    agentsRef.current = agents;
    for (const a of agents) officeSim.sync(a.role_key, a.state, reduce);
  }, [agents, reduce]);

  // Kadr sikli: joylashuv, yo‘nalish, “stolda ishlayapti” belgisi, yorliqlar masshtabi.
  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      officeSim.step((now - last) / 1000);
      last = now;
      const svg = svgRef.current;
      const scale = svg?.getScreenCTM()?.a || 1;
      // Yorliqlar ekranda doimiy o‘lchamda, lekin juda uzoqlashtirilganda biroz kichrayadi;
      // ixcham rejimda bo‘sh agentlar yorlig‘i faqat tanlanganda/fokusda (ustma-ust tushmasin).
      const labelScale = (1 / Math.max(scale, 0.45)).toFixed(3);
      if (svg) {
        svg.dataset.compact = String(scale < 0.55);
        svg.dataset.tiny = String(scale < 0.42);
      }
      for (const a of agentsRef.current) {
        const el = agentRefs.current.get(a.role_key);
        const w = officeSim.walkers.get(a.role_key);
        if (!el || !w) continue;
        el.setAttribute("transform", `translate(${w.pos.x.toFixed(1)},${w.pos.y.toFixed(1)})`);
        const at = officeSim.at(a.role_key) ?? "rest";
        el.dataset.at = at;
        el.dataset.working = String(at === "desk" && WORKING.has(a.state));
        el.querySelector<SVGGElement>("[data-label]")?.setAttribute("transform", `scale(${labelScale})`);
        el.querySelector<SVGGElement>("[data-body]")?.setAttribute("transform", `scale(${w.facing},1)`);
        svg?.querySelector(`[data-owner="${a.role_key}"]`)?.setAttribute(
          "data-active", String(at === "desk" && WORKING.has(a.state)));
      }
      svg?.querySelectorAll<SVGGElement>("[data-room-labels] [data-label]").forEach((g) => {
        const base = g.getAttribute("transform")?.replace(/ scale\(.*\)$/, "") ?? "";
        g.setAttribute("transform", `${base} scale(${labelScale})`);
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  // G‘ildirak bilan yaqinlashtirish (passive emas — sahifa scroll qilinmaydi).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const anchor = toWorld(svg, e.clientX, e.clientY);
      setCamera((c) => zoomAt(c, e.deltaY > 0 ? 1.15 : 1 / 1.15, anchor));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  function onPointerDown(e: PointerEvent<SVGSVGElement>) {
    drag.current.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    drag.current.moved = false;
    drag.current.last = { x: e.clientX, y: e.clientY };
    drag.current.dist = null;
  }

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    const d = drag.current;
    if (!d.pointers.has(e.pointerId) || !svgRef.current) return;
    d.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const svg = svgRef.current;
    if (d.pointers.size === 2) {
      // Ikki barmoq: pinch bilan masshtab.
      const [a, b] = [...d.pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (d.dist) {
        const anchor = toWorld(svg, (a.x + b.x) / 2, (a.y + b.y) / 2);
        setCamera((c) => zoomAt(c, d.dist! / dist, anchor));
      }
      d.dist = dist;
      d.moved = true;
      return;
    }
    if (!d.last) return;
    const dx = e.clientX - d.last.x;
    const dy = e.clientY - d.last.y;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    if (!d.moved) svg.setPointerCapture(e.pointerId);
    d.moved = true;
    const k = 1 / (svg.getScreenCTM()?.a || 1);
    setCamera((c) => pan(c, -dx * k, -dy * k));
    d.last = { x: e.clientX, y: e.clientY };
  }

  function onPointerUp(e: PointerEvent<SVGSVGElement>) {
    drag.current.pointers.delete(e.pointerId);
    drag.current.last = null;
    drag.current.dist = null;
  }

  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    if (e.target !== e.currentTarget) return;  // agent tugmasida Enter — o‘ziniki
    const step = camera.w * 0.1;
    const actions: Record<string, (c: Camera) => Camera> = {
      "+": (c) => zoomAt(c, 0.8), "=": (c) => zoomAt(c, 0.8), "-": (c) => zoomAt(c, 1.25),
      "0": () => fit(), ArrowLeft: (c) => pan(c, -step, 0), ArrowRight: (c) => pan(c, step, 0),
      ArrowUp: (c) => pan(c, 0, -step), ArrowDown: (c) => pan(c, 0, step),
    };
    const act = actions[e.key];
    if (!act) return;
    e.preventDefault();
    setCamera(act);
  }

  const select = (role: string) => {
    if (drag.current.moved) return;  // surish tugadi — bosish emas
    onSelect(selected === role ? null : role);
  };

  return (
    <div className={styles.frame}>
      <div className={styles.controls} role="group" aria-label="Xarita boshqaruvi">
        <span className={styles.hint}>G‘ildirak yoki +/− — masshtab, sichqoncha bilan torting — surish.</span>
        <button className="btn btn-sm" aria-label="Yaqinlashtirish" onClick={() => setCamera((c) => zoomAt(c, 0.8))}>+</button>
        <span className={styles.zoom} aria-live="polite">{zoomLevel(camera)}%</span>
        <button className="btn btn-sm" aria-label="Uzoqlashtirish" onClick={() => setCamera((c) => zoomAt(c, 1.25))}>−</button>
        <button className="btn btn-sm" onClick={() => setCamera(() => fit())}>Butun ofis</button>
      </div>
      <div className={styles.wrap}>
      <svg ref={svgRef} className={styles.map} viewBox={`${camera.x} ${camera.y} ${camera.w} ${camera.h}`}
           preserveAspectRatio="xMidYMid meet" tabIndex={0} role="application" data-reduced-motion={reduce}
           aria-label="Ofis xaritasi. Plyus/minus — yaqinlashtirish, strelkalar — surish, 0 — butun ofis. Agentlarga Tab bilan o‘ting."
           onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
           onPointerCancel={onPointerUp} onKeyDown={onKey}>
        <StaticLayer />
        <g data-room-labels><RoomLabels /></g>
        {agents.map((a) => (
          <g key={a.role_key} ref={(el) => { if (el) agentRefs.current.set(a.role_key, el); else agentRefs.current.delete(a.role_key); }}
             className={styles.agent} data-agent={a.role_key} data-state={a.state}
             data-selected={selected === a.role_key} role="button" tabIndex={0}
             aria-label={`${a.name}, ${a.title}: ${stateLabel(a)}`} aria-pressed={selected === a.role_key}
             style={{ ["--agent" as string]: COLORS[a.role_key] ?? "var(--accent)" }}
             onClick={() => select(a.role_key)}
             onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(a.role_key); } }}>
            <circle r={20} className={styles.hit} />
            <ellipse cx={0} cy={9} rx={14} ry={5} className={styles.shadow} />
            <g data-body>
              {/* Tepadan: yelkalar, bosh, stolga cho‘zilgan qo‘llar (faqat ishlayotganda). */}
              <ellipse cx={0} cy={2} rx={14} ry={10} className={styles.body} />
              <circle cx={0} cy={-1} r={8} className={styles.head} />
              <circle cx={-8} cy={-11} r={3} className={styles.hand} data-hand="l" />
              <circle cx={8} cy={-11} r={3} className={styles.hand} data-hand="r" />
            </g>
            <g data-label className={styles.label}>
              <g transform="translate(0,-20)">
                <text className={styles.name} textAnchor="middle" y={-12}>{a.name}</text>
                {a.state !== "idle" && (
                  <g className={styles.pill} data-state={a.state}>
                    <rect x={-pillWidth(a) / 2} y={-8} width={pillWidth(a)} height={16} rx={8} />
                    <text textAnchor="middle" y={3.5}>{stateLabel(a)}</text>
                  </g>
                )}
              </g>
            </g>
          </g>
        ))}
      </svg>
      </div>
    </div>
  );
}

/** Holat yorlig‘i kengligi matn uzunligiga qarab (10.5px shrift, ~6.3px harf). */
function pillWidth(a: OfficeAgent): number {
  return Math.max(56, stateLabel(a).length * 6.3 + 18);
}

function toWorld(svg: SVGSVGElement, clientX: number, clientY: number): Point {
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}
