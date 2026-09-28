"use client";

import { useState, useSyncExternalStore } from "react";

import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { AgentPanel } from "./AgentPanel";
import { stateLabel, useOffice, type OfficeAgent } from "./api";
import styles from "./office.module.css";
import { OfficeMap, officeFocus } from "./OfficeMap";

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

/**
 * Ofis (TZ 6): tepadan ko‘rinadigan xarita — xonalar, stollar va backend holatiga bog‘langan
 * agentlar. “Ro‘yxat” — xaritasiz muqobil yo‘l (U01). Tanlangan agent kartasi yonida.
 */
export function OfficeFloor() {
  const office = useOffice();
  const [selected, setSelected] = useState<string | null>(null);
  const view = useSyncExternalStore(subscribeView, readView, () => "scene" as View);
  const agents = office.data?.agents ?? [];
  const current = agents.find((a) => a.role_key === selected) ?? null;

  const changeView = writeView;

  function close() {
    const role = selected;
    setSelected(null);
    // Fokus kartani ochgan agentga (xaritada yoki ro‘yxatda) qaytadi.
    requestAnimationFrame(() => document.querySelector<HTMLElement | SVGElement>(
      `[data-agent="${role}"], [data-agent-row="${role}"]`)?.focus());
  }

  return (
    <section aria-label="Ofis" className={styles.office}>
      <div className={styles.head}>
        <h2>Ofis</h2>
        <span className="muted">Agentlar vazifa kelganda o‘z stoliga borib ishlaydi; holat backend’dagi vazifadan.</span>
        <div className={styles.viewSwitch} role="group" aria-label="Ko‘rinish">
          <button className="btn btn-sm" aria-pressed={view === "scene"} onClick={() => changeView("scene")}>Xarita</button>
          <button className="btn btn-sm" aria-pressed={view === "list"} onClick={() => changeView("list")}>Ro‘yxat</button>
        </div>
      </div>
      <ErrorNotice error={office.error} />

      <div className={styles.layout}>
        {view === "scene" ? (
          <OfficeMap agents={agents} selected={selected} onSelect={setSelected} />
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
                    <td><button className="btn btn-sm" data-agent-row={a.role_key} onClick={() => setSelected(a.role_key)}>Ochish</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {current && (
          <AgentPanel agent={current} onClose={close} onShowOnMap={() => {
            officeFocus.show(current.role_key);  // xarita chizilgach kadr siklida bajariladi
            changeView("scene");
          }} />
        )}
      </div>
    </section>
  );
}
