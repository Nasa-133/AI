"use client";

import { useState } from "react";

import { useCreateSource, useSource, useSources, useSync } from "@/features/integrations/api";
import { useFreshness } from "@/features/dashboards/freshness";
import { MappingEditor } from "@/features/integrations/MappingEditor";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

const STATUS: Record<string, [string, string]> = {
  discovering: ["Fayl o‘qilmoqda", "badge badge-accent"],
  awaiting_mapping: ["Mapping tasdiqlanishi kerak", "badge badge-warning"],
  configuring: ["Mapping tekshirilmoqda", "badge badge-accent"],
  ready: ["Sinxronlashga tayyor", "badge"],
  syncing: ["Sinxronlanmoqda", "badge badge-accent"],
  synced: ["Yuklandi", "badge badge-success"],
  failed: ["Xato", "badge badge-danger"],
};

function Status({ status, id }: { status: string; id?: string }) {
  const fresh = useFreshness();
  // I03: xizmat javob bermasa jarayon “kutilmoqda” deb aniq ko‘rsatiladi (abadiy “o‘qilmoqda” emas).
  if (id && fresh.data?.waiting.some((w) => w.id === id && w.stale)) {
    return <span className="badge badge-warning" title="Integratsiya xizmati javob bermayapti">Kutilmoqda</span>;
  }
  const [label, cls] = STATUS[status] ?? [status, "badge"];
  return <span className={cls}>{label}</span>;
}

function SourceDetail({ id }: { id: string }) {
  const source = useSource(id);
  const sync = useSync(id);
  const [choice, setChoice] = useState(0);
  const s = source.data;
  if (!s) return <div className="skeleton" style={{ height: 120 }} />;
  // Eng mos entity birinchi (backend moslik bo‘yicha saralaydi); qolganlari — tanlov sifatida.
  const entities = [...(s.discovery?.entities ?? [])].sort((a, b) => b.match_score - a.match_score);
  const entity = entities[Math.min(choice, entities.length - 1)];
  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <h2 style={{ marginRight: "auto" }}>{s.name}</h2>
        {s.connector_id === "demo_erp" && <span className="badge badge-warning">DEMO — haqiqiy ERP emas</span>}
        <Status status={s.status} id={s.id} />
      </div>
      {s.error_message && (
        <div className={s.status === "failed" ? "notice notice-danger" : "notice notice-warning"}>{s.error_message}</div>
      )}
      {s.status === "awaiting_mapping" && entity && (
        <>
          {entities.length > 1 && (
            <label className="field" style={{ maxWidth: 420 }}>
              <span>Fayl turi</span>
              <select className="select" value={choice} onChange={(e) => setChoice(Number(e.target.value))}>
                {entities.map((e, i) => (
                  <option key={e.entity} value={i}>{e.entity} — moslik {Math.round(e.match_score * 100)}%</option>
                ))}
              </select>
            </label>
          )}
          <MappingEditor key={`${entity.entity}:${entity.source_name}`} sourceId={id} entity={entity} />
        </>
      )}
      {(s.status === "ready" || s.status === "synced") && (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="muted">Mapping versiyasi: {s.mapping_version} · {s.entity}</span>
          <button className="btn btn-primary" disabled={sync.isPending} onClick={() => sync.mutate()}>
            {s.status === "synced" ? "Qayta sinxronlash" : "Sinxronlash"}
          </button>
        </div>
      )}
      <ErrorNotice error={sync.error} />
    </section>
  );
}

export default function IntegrationsPage() {
  const sources = useSources();
  const create = useCreateSource();
  const [selected, setSelected] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const current = selected ?? sources.data?.[0]?.id ?? null;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100 }}>
      <h1>Integratsiyalar</h1>
      <section className="panel panel-pad" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="field" style={{ minWidth: 260 }}>
          <label htmlFor="csv">CSV fayl (UTF-8, sarlavhali)</label>
          <input id="csv" className="input" type="file" accept=".csv,text/csv"
                 onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <span className="hint">XLSX importi P1 bosqichida. Faylni Excel’dan “CSV UTF-8” sifatida saqlang.</span>
        </div>
        <button className="btn btn-primary" disabled={!file || create.isPending}
                onClick={() => file && create.mutate({ connector: "file_import", file },
                  { onSuccess: ({ id }) => { setSelected(id); setFile(null); } })}>
          Yuklash
        </button>
        <button className="btn" disabled={create.isPending}
                onClick={() => create.mutate({ connector: "demo_erp" }, { onSuccess: ({ id }) => setSelected(id) })}>
          Demo ERP ulash (sintetik)
        </button>
        <ErrorNotice error={create.error} />
      </section>
      <ErrorNotice error={sources.error} />
      {/* Tor ekranda (chat ochiq bo‘lsa ham) manbalar ro‘yxati tepaga o‘tadi. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))", gap: 16 }}>
        <nav aria-label="Manbalar" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {!sources.data?.length && !sources.isLoading && <p className="muted">Hali manba yo‘q.</p>}
          {sources.data?.map((s) => (
            <button key={s.id} className="btn" aria-current={s.id === current ? "true" : undefined}
                    style={{ justifyContent: "space-between", borderColor: s.id === current ? "var(--accent)" : undefined }}
                    onClick={() => setSelected(s.id)}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
              <Status status={s.status} id={s.id} />
            </button>
          ))}
        </nav>
        {current && <div style={{ gridColumn: "1 / -1", minWidth: 0 }}><SourceDetail id={current} /></div>}
      </div>
    </div>
  );
}
