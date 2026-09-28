"use client";

import { useState } from "react";

import { useMe } from "@/features/auth/api";
import { useMembers } from "@/features/members/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useDashboardVersions, useEditDashboard, useShareDashboard } from "./api";
import type { DashboardDetail, WidgetEdit } from "./types";
import { allowedTypes, TYPE_LABEL } from "./widgetTypes";

/** Tahrir: nom, widget nomi/turi/tartibi, o‘chirish. Saqlash — yangi versiya (TZ 8.2). */
export function EditPanel({ dashboard, onDone }: { dashboard: DashboardDetail; onDone: () => void }) {
  const edit = useEditDashboard(dashboard.id);
  const [title, setTitle] = useState(dashboard.title);
  const [items, setItems] = useState<WidgetEdit[]>(
    dashboard.widgets.map((w) => ({ id: w.id, title: w.title, type: w.type })));
  const byId = Object.fromEntries(dashboard.widgets.map((w) => [w.id, w]));
  const move = (i: number, delta: number) => {
    const next = [...items];
    [next[i], next[i + delta]] = [next[i + delta], next[i]];
    setItems(next);
  };

  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}
             aria-label="Dashboardni tahrirlash">
      <label className="field">
        <span>Nomi</span>
        <input className="input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
      </label>
      {items.map((it, i) => (
        <div key={it.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input className="input" style={{ flex: "1 1 200px" }} aria-label={`Widget ${i + 1} nomi`}
                 value={it.title} maxLength={200}
                 onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
          <select className="select" style={{ width: "auto" }} aria-label={`Widget ${i + 1} turi`} value={it.type}
                  onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, type: e.target.value as WidgetEdit["type"] } : x))}>
            {allowedTypes(byId[it.id]).map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
          </select>
          <button className="btn btn-sm" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Yuqoriga">↑</button>
          <button className="btn btn-sm" disabled={i === items.length - 1} onClick={() => move(i, 1)} aria-label="Pastga">↓</button>
          <button className="btn btn-sm" disabled={items.length === 1}
                  onClick={() => setItems(items.filter((_, j) => j !== i))}>O‘chirish</button>
        </div>
      ))}
      <ErrorNotice error={edit.error} />
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" disabled={!title.trim() || edit.isPending}
                onClick={() => edit.mutate({ title, widgets: items }, { onSuccess: onDone })}>
          Saqlash (yangi versiya)
        </button>
        <button className="btn" onClick={onDone}>Bekor qilish</button>
      </div>
    </section>
  );
}

/** Ulashish: butun korxona yoki tanlangan a’zolar (TZ 8.2, ruxsat bilan). */
export function SharePanel({ dashboard, onDone }: { dashboard: DashboardDetail; onDone: () => void }) {
  const me = useMe();
  const members = useMembers();
  const share = useShareDashboard(dashboard.id);
  const [visibility, setVisibility] = useState(dashboard.visibility);
  const [users, setUsers] = useState(new Set(dashboard.shared_with));
  const others = (members.data ?? []).filter((m) => m.user_id !== me.data?.user_id);

  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}
             aria-label="Ulashish">
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        <legend className="sr-only">Kimga ko‘rinadi</legend>
        <label><input type="radio" checked={visibility === "tenant"} onChange={() => setVisibility("tenant")} />
          {" "}Korxonaning barcha a’zolari</label>
        <label><input type="radio" checked={visibility === "private"} onChange={() => setVisibility("private")} />
          {" "}Faqat men, rahbarlar va tanlanganlar</label>
      </fieldset>
      {visibility === "private" && (
        members.data === null ? (
          <p className="muted">A’zolar ro‘yxatini faqat Owner yoki Admin ko‘radi — aniq a’zoga ulashishni ular bajaradi.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 220, overflowY: "auto" }}>
            {others.map((m) => (
              <label key={m.user_id}>
                <input type="checkbox" checked={users.has(m.user_id)}
                       onChange={(e) => {
                         const next = new Set(users);
                         if (e.target.checked) next.add(m.user_id); else next.delete(m.user_id);
                         setUsers(next);
                       }} /> {m.email} <span className="muted">· {m.role}</span>
              </label>
            ))}
            {!others.length && <p className="muted">Boshqa a’zolar yo‘q.</p>}
          </div>
        )
      )}
      <ErrorNotice error={members.error ?? share.error} />
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" disabled={share.isPending}
                onClick={() => share.mutate({ visibility, user_ids: visibility === "private" ? [...users] : [] },
                                            { onSuccess: onDone })}>
          Saqlash
        </button>
        <button className="btn" onClick={onDone}>Yopish</button>
      </div>
    </section>
  );
}

export function VersionsPanel({ dashboard, onDone }: { dashboard: DashboardDetail; onDone: () => void }) {
  const versions = useDashboardVersions(dashboard.id, true);
  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 8 }}
             aria-label="Versiyalar">
      <ErrorNotice error={versions.error} />
      <table className="table">
        <thead><tr><th>Versiya</th><th>Nomi</th><th>Sana</th></tr></thead>
        <tbody>
          {versions.data?.map((v) => (
            <tr key={v.version}>
              <td>{v.version}{v.version === dashboard.version && <span className="badge badge-accent" style={{ marginLeft: 6 }}>joriy</span>}</td>
              <td>{v.title}</td>
              <td className="muted">{new Date(v.created_at).toLocaleString("uz")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="btn" style={{ alignSelf: "flex-start" }} onClick={onDone}>Yopish</button>
    </section>
  );
}
