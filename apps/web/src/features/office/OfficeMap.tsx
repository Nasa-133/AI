"use client";

import { Maximize2, Minimize2, Scan, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent, type PointerEvent } from "react";

import { stateLabel, type OfficeAgent } from "./api";
import styles from "./officeMap.module.css";
import { centerOn, fit, initialFor, pan, zoomAt, zoomLevel, type Camera } from "./world/camera";
import { accentOf, AgentLabel, AgentSprite, OfficeStatic } from "./OfficeArt";
import { PIXEL, SPRITE_H } from "./world/sprites";
import { ROOMS, seatOf, TILE, type Point } from "./world/map";
import { officeSim, WORKING } from "./world/sim";

// Kamera sessiya davomida saqlanadi: dashboard oynasi yoki boshqa sahifadan qaytganda joyida.
let savedCamera: Camera | null = null;

let pendingFocus: string | null = null;
/** Kamerani agentga olib borish. So‘rov saqlanadi: xarita hali chizilmagan bo‘lsa ham
 * (masalan, ro‘yxatdan xaritaga o‘tishda) kadr siklida bajariladi. */
export const officeFocus = {
  show(role: string) { pendingFocus = role; },
};

function subscribeMotion(cb: () => void) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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

  const [full, setFull] = useState(false);
  const setCamera = (update: (c: Camera) => Camera) => {
    setCameraState((c) => { const next = update(c); savedCamera = next; return next; });
  };


  // Tor ekranda (telefon) birinchi ochilishda butun ofis juda mayda — agentlar turgan joyga
  // yaqinlashtiriladi (agentlar ma’lum bo‘lgach, kadr siklida bir marta).
  const autoFrame = useRef(false);
  const measure = (el: HTMLDivElement | null) => {
    // Ekran kengligi (telefon) bo‘yicha: element o‘lchami birinchi chizishda hali barqaror emas.
    if (el && !savedCamera && window.innerWidth < 600) {
      autoFrame.current = true;
      setCamera(() => initialFor(window.innerWidth));
    }
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
      // “Xaritada ko‘rsatish” (agent kartasi/ro‘yxatdan): kamera agentga yaqinlashadi.
      const focusWalker = pendingFocus ? officeSim.walkers.get(pendingFocus) : undefined;
      if (focusWalker) {
        pendingFocus = null;
        setCamera((c) => centerOn(c, focusWalker.pos, 220));
      }
      if (autoFrame.current && agentsRef.current.length) {
        autoFrame.current = false;
        const focus = agentsFocus(agentsRef.current);
        if (focus) setCamera((c) => centerOn(c, focus, 200));
      }
      const svg = svgRef.current;
      const scale = svg?.getScreenCTM()?.a || 1;
      // Yorliqlar ekranda doimiy o‘lchamda, lekin juda uzoqlashtirilganda biroz kichrayadi;
      // ixcham rejimda bo‘sh agentlar yorlig‘i faqat tanlanganda/fokusda (ustma-ust tushmasin).
      const labelScale = (1 / Math.max(scale, 0.45)).toFixed(3);
      if (svg) {
        svg.dataset.compact = String(scale < 0.72);
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
        // Dam olish joyida qo‘shni yorliqlar ustma-ust tushmasligi uchun ba’zilari pastda.
        el.dataset.labelBelow = String(at === "rest" && Boolean(seatOf(a.role_key).restLabelBelow));
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
    <div className={styles.frame} data-full={full}
         onKeyDown={(e) => { if (full && e.key === "Escape") { e.stopPropagation(); setFull(false); } }}>
      <div className={styles.controls} role="group" aria-label="Xarita boshqaruvi">
        <span className={styles.hint}>G‘ildirak yoki +/− — masshtab, sichqoncha bilan torting — surish.</span>
        <div className="btn-group">
          <button className="btn btn-sm btn-icon" aria-label="Uzoqlashtirish" title="Uzoqlashtirish" onClick={() => setCamera((c) => zoomAt(c, 1.25))}><ZoomOut aria-hidden /></button>
          <span className={`btn btn-sm ${styles.zoom}`} aria-live="polite">{zoomLevel(camera)}%</span>
          <button className="btn btn-sm btn-icon" aria-label="Yaqinlashtirish" title="Yaqinlashtirish" onClick={() => setCamera((c) => zoomAt(c, 0.8))}><ZoomIn aria-hidden /></button>
        </div>
        <button className="btn btn-sm" onClick={() => setCamera(() => fit())}><Scan aria-hidden /> Butun ofis</button>
        <button className="btn btn-sm" aria-pressed={full} onClick={() => setFull(!full)}>
          {full ? <Minimize2 aria-hidden /> : <Maximize2 aria-hidden />} {full ? "Kichraytirish" : "To‘liq ekran"}
        </button>
      </div>
      <div className={styles.wrap} ref={measure}>
      <svg ref={svgRef} className={styles.map} viewBox={`${camera.x} ${camera.y} ${camera.w} ${camera.h}`}
           preserveAspectRatio="xMidYMid meet" tabIndex={0} role="application" data-reduced-motion={reduce}
           aria-label="Ofis xaritasi. Plyus/minus — yaqinlashtirish, strelkalar — surish, 0 — butun ofis. Agentlarga Tab bilan o‘ting."
           onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
           onPointerCancel={onPointerUp} onKeyDown={onKey}>
        <OfficeStatic />
        <g data-room-labels><RoomLabels /></g>
        {agents.map((a) => (
          <g key={a.role_key} ref={(el) => { if (el) agentRefs.current.set(a.role_key, el); else agentRefs.current.delete(a.role_key); }}
             className={styles.agent} data-agent={a.role_key} data-state={a.state}
             data-selected={selected === a.role_key} role="button" tabIndex={0}
             aria-label={`${a.name}, ${a.title}: ${stateLabel(a)}`} aria-pressed={selected === a.role_key}
             style={{ ["--agent" as string]: accentOf(a.role_key) }}
             onClick={() => select(a.role_key)}
             onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(a.role_key); } }}>
            <circle r={24} cy={-14} className={styles.hit} />
            <AgentSprite agent={a} />
            {/* Siljish masshtabdan tashqarida: yaqinlashtirganda ham nishon boshdan yuqorida. */}
            <g data-label-offset transform={`translate(0,${LABEL_ANCHOR})`}>
              <g data-label className={styles.label}>
                <AgentLabel agent={a} />
              </g>
            </g>
          </g>
        ))}
      </svg>
      </div>
      <ul className={styles.statusBar} aria-label="Agentlar holati">
        {agents.map((a) => (
          <li key={a.role_key}>
            <button type="button" data-state={a.state} aria-pressed={selected === a.role_key}
                    onClick={() => { officeFocus.show(a.role_key); onSelect(a.role_key); }}>
              <span className={styles.dot} style={{ background: accentOf(a.role_key) }} aria-hidden />
              <strong>{a.name}</strong> · <span className={styles.statusText}>{stateLabel(a)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const LABEL_ANCHOR = 8 - SPRITE_H * PIXEL - 3;  // sprite boshi ustida

/** Faol agentlar (bo‘lmasa hammasi) markazi — kamerani shu yerga qaratish uchun. */
function agentsFocus(agents: OfficeAgent[]): Point | null {
  const active = agents.filter((a) => a.state !== "idle");
  const pts = (active.length ? active : agents)
    .map((a) => officeSim.walkers.get(a.role_key)?.pos).filter((p): p is Point => Boolean(p));
  if (!pts.length) return null;
  return { x: pts.reduce((s, p) => s + p.x, 0) / pts.length, y: pts.reduce((s, p) => s + p.y, 0) / pts.length };
}

function toWorld(svg: SVGSVGElement, clientX: number, clientY: number): Point {
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}
