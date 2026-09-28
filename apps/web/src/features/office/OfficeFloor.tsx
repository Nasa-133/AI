"use client";

import { useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";

import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { AgentAvatar } from "./AgentAvatar";
import { AgentPanel } from "./AgentPanel";
import { stateLabel, useOffice, type OfficeAgent } from "./api";
import styles from "./office.module.css";

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
const VIEW_KEY = "abo.office.view";

type View = "scene" | "list";
const viewListeners = new Set<() => void>();

function readView(): View {
  try { return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "scene"; } catch { return "scene"; }
}

function writeView(next: View) {
  try { localStorage.setItem(VIEW_KEY, next); } catch { /* shaxsiy rejim — muhim emas */ }
  viewListeners.forEach((l) => l());
}

function subscribeView(listener: () => void) {
  viewListeners.add(listener);
  return () => { viewListeners.delete(listener); };
}

function taskLine(a: OfficeAgent): string {
  const t = a.current_task;
  if (!t) return "Vazifa yo‘q";
  if (!t.mine) return "Boshqa foydalanuvchi vazifasi";
  return t.title ?? "";
}

function load(a: OfficeAgent): string {
  const parts = [`${a.active_count}/${a.limit}`];
  if (a.queue_length) parts.push(`+${a.queue_length} navbatda`);
  return parts.join(" · ");
}

/**
 * Ofis (TZ 6): 5 ta stol, holat backend’dan. Klaviatura: strelkalar stollar orasida,
 * Enter/Space — kartani ochish. “Ro‘yxat” ko‘rinishi — sahnasiz muqobil yo‘l (U01).
 */
export function OfficeFloor() {
  const office = useOffice();
  const [selected, setSelected] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);
  const view = useSyncExternalStore(subscribeView, readView, () => "scene" as View);
  const desks = useRef<(HTMLButtonElement | null)[]>([]);
  const agents = office.data?.agents ?? [];
  const current = agents.find((a) => a.role_key === selected) ?? null;

  const changeView = writeView;

  function close() {
    const index = agents.findIndex((a) => a.role_key === selected);
    setSelected(null);
    requestAnimationFrame(() => desks.current[index]?.focus());
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    let next: number | null = null;
    if (step) next = (focusIndex + step + agents.length) % agents.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = agents.length - 1;
    if (next === null) return;
    e.preventDefault();
    setFocusIndex(next);
    desks.current[next]?.focus();
  }

  return (
    <section aria-label="Ofis" className={styles.office}>
      <div className={styles.head}>
        <h2>Ofis</h2>
        <span className="muted">Holat vazifa bosqichlaridan olinadi; foiz taxmin qilinmaydi.</span>
        <div className={styles.viewSwitch} role="group" aria-label="Ko‘rinish">
          <button className="btn btn-sm" aria-pressed={view === "scene"} onClick={() => changeView("scene")}>Sahna</button>
          <button className="btn btn-sm" aria-pressed={view === "list"} onClick={() => changeView("list")}>Ro‘yxat</button>
        </div>
      </div>
      <ErrorNotice error={office.error} />
      {office.isLoading && <div className="skeleton" style={{ height: 180 }} />}

      <div className={styles.layout}>
        {view === "scene" ? (
          <div className={styles.floor} role="group" aria-label="Agentlar stollari" onKeyDown={onKey}>
            {agents.map((a, i) => (
              <button key={a.role_key} ref={(el) => { desks.current[i] = el; }}
                      className={styles.deskCard} data-state={a.state}
                      tabIndex={i === focusIndex ? 0 : -1} aria-pressed={selected === a.role_key}
                      aria-label={`${a.name}, ${a.title}: ${stateLabel(a)}. Joriy ishlar ${a.active_count} / ${a.limit}${a.queue_length ? `, navbatda ${a.queue_length}` : ""}. ${taskLine(a)}`}
                      onFocus={() => setFocusIndex(i)}
                      onClick={() => setSelected(selected === a.role_key ? null : a.role_key)}>
                <span className={styles.stateTag} data-state={a.state}>{stateLabel(a)}</span>
                <AgentAvatar state={a.state} color={COLORS[i % COLORS.length]} />
                <strong>{a.name}</strong>
                <span className="muted">{a.title}</span>
                <span className={styles.load}>{load(a)}</span>
                <span className={styles.taskLine}>{taskLine(a)}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className={styles.listWrap}>
            <table className="table">
              <caption className="sr-only">Agentlar holati</caption>
              <thead>
                <tr><th>Agent</th><th>Holat</th><th>Joriy ishlar</th><th>Navbat</th><th>Vazifa</th><th /></tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.role_key}>
                    <td><strong>{a.name}</strong> <span className="muted">{a.title}</span></td>
                    <td><span className={styles.stateTag} data-state={a.state}>{stateLabel(a)}</span></td>
                    <td>{a.active_count} / {a.limit}</td>
                    <td>{a.queue_length}</td>
                    <td className={styles.taskCell}>{taskLine(a)}</td>
                    <td><button className="btn btn-sm" onClick={() => setSelected(a.role_key)}>Ochish</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {current && <AgentPanel agent={current} onClose={close} />}
      </div>
    </section>
  );
}
