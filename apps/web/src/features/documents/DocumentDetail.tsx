"use client";

import { useState } from "react";

import { useMe } from "@/features/auth/api";
import { contextDocs } from "@/features/chat/contextDocs";
import { useMembers } from "@/features/members/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import {
  downloadUrl, useDeleteDocument, useDiff, useDocument, usePromote, useSections, useShare,
  type DocumentDetail as Detail, type Version,
} from "./api";
import styles from "./documents.module.css";
import { formatBytes, KIND_LABEL, versionStatus } from "./status";

const CHANGE_LABEL = { added: "Qo‘shildi", removed: "O‘chirildi", changed: "O‘zgardi" } as const;

function DiffView({ documentId, left, right }: { documentId: string; left: Version; right: Version }) {
  const diff = useDiff(documentId, left.id, right.id);
  return (
    <section className={styles.block} aria-label="Versiyalar farqi">
      <h3>v{left.version_no} → v{right.version_no} farqi</h3>
      <ErrorNotice error={diff.error} />
      {diff.isLoading && <div className="skeleton" style={{ height: 80 }} />}
      {diff.data && !diff.data.changes.length && <p className="muted">Matnda farq yo‘q.</p>}
      {diff.data && (
        <>
          <ul className={styles.changes}>
            {diff.data.changes.map((c) => (
              <li key={`${c.section_id}-${c.change}`} data-change={c.change}>
                <div className={styles.changeHead}>
                  <span className="badge">{c.locator}</span>
                  <span className="muted">{CHANGE_LABEL[c.change]}</span>
                </div>
                {c.before !== null && <del className={styles.before}>{c.before}</del>}
                {c.after !== null && <ins className={styles.after}>{c.after}</ins>}
              </li>
            ))}
          </ul>
          <span className="hint">O‘zgarmagan bo‘limlar: {diff.data.unchanged_count}</span>
        </>
      )}
    </section>
  );
}

function SectionsView({ documentId, version }: { documentId: string; version: Version }) {
  const sections = useSections(documentId, version.parse_status === "ready" ? version.id : null);
  if (version.parse_status !== "ready") return null;
  return (
    <section className={styles.block} aria-label="Hujjat matni">
      <h3>v{version.version_no} matni</h3>
      <ErrorNotice error={sections.error} />
      {sections.isLoading && <div className="skeleton" style={{ height: 120 }} />}
      <div className={styles.sections}>
        {sections.data?.map((s) => (
          <p key={s.section_id} data-kind={s.kind}>
            <span className={styles.locator}>{s.locator}</span>
            {/* Matn oddiy matn sifatida: hujjatdagi HTML/markdown talqin qilinmaydi. */}
            {s.text}
          </p>
        ))}
      </div>
    </section>
  );
}

function ShareControls({ doc }: { doc: Detail }) {
  const me = useMe();
  const share = useShare(doc.id);
  const manager = me.data?.role === "owner" || me.data?.role === "admin";
  const members = useMembers(manager);
  const [open, setOpen] = useState(false);
  const others = (members.data ?? []).filter((m) => m.user_id !== me.data?.user_id);
  const toggleUser = (id: string) => {
    const next = doc.shared_with.includes(id)
      ? doc.shared_with.filter((u) => u !== id) : [...doc.shared_with, id];
    share.mutate({ visibility: doc.visibility, user_ids: next });
  };
  return (
    <div className={styles.share}>
      <button className="btn btn-sm" aria-expanded={open} onClick={() => setOpen(!open)}>Ulashish</button>
      {open && (
        <div className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label className={styles.check}>
            <input type="radio" name="visibility" checked={doc.visibility === "private"}
                   onChange={() => share.mutate({ visibility: "private", user_ids: doc.shared_with })} />
            Faqat men va tanlanganlar
          </label>
          <label className={styles.check}>
            <input type="radio" name="visibility" checked={doc.visibility === "tenant"}
                   onChange={() => share.mutate({ visibility: "tenant", user_ids: doc.shared_with })} />
            Butun korxona
          </label>
          {doc.visibility === "private" && others.map((m) => (
            <label key={m.user_id} className={styles.check}>
              <input type="checkbox" checked={doc.shared_with.includes(m.user_id)}
                     onChange={() => toggleUser(m.user_id)} />
              {m.email}
            </label>
          ))}
          <ErrorNotice error={share.error} />
        </div>
      )}
    </div>
  );
}

export function DocumentDetail({ id, compare, onCompare, onDeleted }: {
  id: string; compare: string | null; onCompare: (versionId: string | null) => void;
  onDeleted: () => void;
}) {
  const doc = useDocument(id);
  const promote = usePromote(id);
  const remove = useDeleteDocument();
  const [viewing, setViewing] = useState<string | null>(null);
  const d = doc.data;
  if (doc.error) return <ErrorNotice error={doc.error} />;
  if (!d) return <div className="skeleton" style={{ height: 200 }} />;

  const current = d.versions.find((v) => v.is_current) ?? d.versions[0];
  const compared = compare ? d.versions.find((v) => v.id === compare) : undefined;
  const shown = d.versions.find((v) => v.id === viewing) ?? compared ?? current;
  const ready = current?.parse_status === "ready";

  return (
    <section className={`panel panel-pad ${styles.detail}`} aria-label={d.title}>
      <div className={styles.head}>
        <h2>{d.title}</h2>
        <span className="badge">{d.visibility === "tenant" ? "Korxona" : "Shaxsiy"}</span>
        <div className={styles.actions}>
          <button className="btn btn-sm btn-primary" disabled={!ready}
                  title={ready ? undefined : "Hujjat hali tayyor emas"}
                  onClick={() => contextDocs.add({ id: d.id, title: d.title })}>
            Chatda so‘rash
          </button>
          {current && <a className="btn btn-sm" href={downloadUrl(d.id, current.id)}>Yuklab olish</a>}
          {d.can_promote && <ShareControls doc={d} />}
          {d.can_promote && (
            <button className="btn btn-sm" disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm(`“${d.title}” o‘chirilsinmi? Qidiruvdan darhol olib tashlanadi.`)) {
                        remove.mutate(d.id, { onSuccess: onDeleted });
                      }
                    }}>
              O‘chirish
            </button>
          )}
        </div>
      </div>
      <ErrorNotice error={remove.error} />

      <div className={styles.tableWrap}>
        <table className="table">
          <thead>
            <tr><th>Versiya</th><th>Turi</th><th>Holat</th><th>Hajm</th><th>Izoh</th><th /></tr>
          </thead>
          <tbody>
            {d.versions.map((v) => {
              const st = versionStatus(v);
              return (
                <tr key={v.id} aria-current={v.id === shown?.id ? "true" : undefined}>
                  <td>
                    v{v.version_no} {v.is_current && <span className="badge badge-success">joriy</span>}
                  </td>
                  <td>{KIND_LABEL[v.kind] ?? v.kind}</td>
                  <td><span className={st.cls} title={st.hint ?? undefined}>{st.label}</span></td>
                  <td>{formatBytes(v.size_bytes)}</td>
                  <td className={styles.comment}>{v.comment ?? ""}</td>
                  <td className={styles.rowActions}>
                    <button className="btn btn-sm btn-ghost" onClick={() => { setViewing(v.id); onCompare(null); }}>
                      Ko‘rish
                    </button>
                    {!v.is_current && current && (
                      <button className="btn btn-sm btn-ghost" onClick={() => { setViewing(null); onCompare(v.id); }}>
                        Solishtirish
                      </button>
                    )}
                    {!v.is_current && d.can_promote && v.parse_status === "ready" && current && (
                      <button className="btn btn-sm" disabled={promote.isPending}
                              onClick={() => promote.mutate({ version_id: v.id, expected_current_version_id: current.id },
                                                            { onSuccess: () => onCompare(null) })}>
                        Joriy qilish
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ErrorNotice error={promote.error} />
      {current && versionStatus(current).hint && (
        <div className="notice notice-warning">{versionStatus(current).hint}</div>
      )}
      {compared && current && compared.id !== current.id && (
        <DiffView documentId={d.id} left={current} right={compared} />
      )}
      {shown && <SectionsView documentId={d.id} version={shown} />}
    </section>
  );
}
