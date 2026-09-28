"use client";

import { CheckCheck, Database, FileSpreadsheet, RefreshCw, Server, Upload } from "lucide-react";
import { useState } from "react";

import { useConnectErp, useCreateSource, useSource, useSources, useSync, useUseSource, type Source } from "@/features/integrations/api";
import { useFreshness } from "@/features/dashboards/freshness";
import { MappingEditor } from "@/features/integrations/MappingEditor";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { FilePicker } from "@/shared/ui/FilePicker";

import styles from "./integrations.module.css";

const STATUS: Record<string, [string, string]> = {
  discovering: ["Manba o‘qilmoqda", "badge badge-accent"],
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

/** Takroriy baza: shu ma’lumot boshqa manbada ham bor — ikki marta sanalmaydi. */
function DuplicateNotice({ s }: { s: Source }) {
  const use = useUseSource(s.id);
  if (!s.usage || s.usage.counted) return null;
  const pct = s.usage.overlap != null ? ` (yozuvlarning ${Math.round(s.usage.overlap * 100)}% bir xil)` : "";
  return (
    <div className="notice notice-warning" role="status">
      <strong>Takroriy baza — hisobga olinmaydi</strong>
      <span>
        Bu manba {s.usage.duplicate_of_name ? `“${s.usage.duplicate_of_name}”` : "boshqa manba"} bilan bir xil
        ma’lumotni beradi{pct}. Raqamlar ikki marta sanalmasligi uchun faqat bittasi ishlatiladi.
      </span>
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn btn-sm" disabled={use.isPending} onClick={() => use.mutate()}>
          <CheckCheck aria-hidden /> Shu manbani ishlatish
        </button>
        <span className="hint">Boshqasi hisobdan chiqadi (o‘chirilmaydi).</span>
      </div>
      <ErrorNotice error={use.error} />
    </div>
  );
}

function SourceDetail({ id }: { id: string }) {
  const source = useSource(id);
  const sync = useSync(id);
  const [choice, setChoice] = useState<number | null>(null);
  const s = source.data;
  if (!s) return <div className="skeleton" style={{ height: 120 }} />;
  // Eng mos entity birinchi (backend moslik bo‘yicha saralaydi); qolganlari — tanlov sifatida.
  const entities = [...(s.discovery?.entities ?? [])].sort((a, b) => b.match_score - a.match_score);
  // Ko‘p obyektli manba (ERP): yaratishda ko‘rsatilgan obyekt oldindan tanlanadi.
  const hinted = entities.findIndex((e) => e.entity === s.entity);
  const index = choice ?? (hinted >= 0 ? hinted : 0);
  const entity = entities[Math.min(index, entities.length - 1)];
  const canSync = s.status === "ready" || s.status === "synced" || (s.status === "failed" && s.mapping_version != null);
  return (
    <section className="panel panel-pad stack">
      <div className="panel-head">
        <h2>{s.name}</h2>
        {s.connector_id === "demo_erp" && <span className="badge badge-warning">DEMO — haqiqiy ERP emas</span>}
        {s.connector_id === "erp_api" && <span className="badge" title="Integration Runtime sozlamasidagi ERP API">ERP API</span>}
        <Status status={s.status} id={s.id} />
      </div>
      <DuplicateNotice s={s} />
      {s.error_message && (
        <div className={s.status === "failed" ? "notice notice-danger" : "notice notice-warning"}>{s.error_message}</div>
      )}
      {s.status === "awaiting_mapping" && entity && (
        <>
          {entities.length > 1 && (
            <label className="field" style={{ maxWidth: 420 }}>
              <span>Obyekt turi</span>
              <select className="select" value={index} onChange={(e) => setChoice(Number(e.target.value))}>
                {entities.map((e, i) => (
                  <option key={`${e.entity}:${e.source_name}`} value={i}>{e.entity} ← {e.source_name} — moslik {Math.round(e.match_score * 100)}%</option>
                ))}
              </select>
            </label>
          )}
          <MappingEditor key={`${entity.entity}:${entity.source_name}`} sourceId={id} entity={entity} />
        </>
      )}
      {canSync && (
        <div className="row">
          <button className="btn btn-primary" disabled={sync.isPending} onClick={() => sync.mutate()}>
            <RefreshCw aria-hidden /> {s.status === "ready" ? "Sinxronlash" : "Qayta sinxronlash"}
          </button>
          <span className="muted">Mapping v{s.mapping_version} · <span className="mono">{s.entity}</span></span>
          {s.connector_id === "erp_api" && <span className="hint">· ERP har 15 daqiqada avtomatik qayta o‘qiladi</span>}
        </div>
      )}
      <ErrorNotice error={sync.error} />
    </section>
  );
}

export default function IntegrationsPage() {
  const sources = useSources();
  const create = useCreateSource();
  const connectErp = useConnectErp(sources.data ?? []);
  const [selected, setSelected] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const current = selected ?? sources.data?.[0]?.id ?? null;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Integratsiyalar</h1>
          <p>Ma’lumot manbalari: ERP yoki fayl. Mapping tasdiqlangach sinxronlanadi.</p>
        </div>
      </div>
      <div className={styles.connect}>
        <section className="panel panel-pad stack">
          <div className="icon-text"><Server aria-hidden /><h2>ERP tizimi (API)</h2></div>
          <p className="muted">Sotuvlar, qaytarishlar, ombor va debitorlik — har biri alohida manba sifatida ulanadi va avtomatik yangilanadi.</p>
          <div className="row">
            <button className="btn btn-primary" disabled={connectErp.isPending}
                    title="ERP REST API: sotuvlar, qaytarishlar, ombor, debitorlik — har biri alohida manba"
                    onClick={() => connectErp.mutate(undefined, { onSuccess: (list) => setSelected(list[0]?.id ?? null) })}>
              <Database aria-hidden /> ERP ulash (API)
            </button>
            <button className="btn" disabled={create.isPending}
                    onClick={() => create.mutate({ connector: "demo_erp" }, { onSuccess: ({ id }) => setSelected(id) })}>
              Demo ERP ulash (sintetik fayl)
            </button>
          </div>
        </section>
        <section className="panel panel-pad stack">
          <div className="icon-text"><FileSpreadsheet aria-hidden /><h2>CSV fayl</h2></div>
          <div className="field">
            <label htmlFor="csv">CSV fayl (UTF-8, sarlavhali)</label>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <FilePicker id="csv" accept=".csv,text/csv" file={file} onChange={setFile} />
              <button className="btn btn-primary" disabled={!file || create.isPending}
                      onClick={() => file && create.mutate({ connector: "file_import", file },
                        { onSuccess: ({ id }) => { setSelected(id); setFile(null); } })}>
                <Upload aria-hidden /> Yuklash
              </button>
            </div>
            <span className="hint">XLSX importi P1 bosqichida. Excel’dan “CSV UTF-8” sifatida saqlang.</span>
          </div>
        </section>
      </div>
      <ErrorNotice error={create.error ?? connectErp.error} />
      <ErrorNotice error={sources.error} />
      <div className={styles.sources}>
        <nav aria-label="Manbalar" className={`panel ${styles.list}`}>
          <span className="section-title" style={{ padding: "4px 8px" }}>Manbalar</span>
          {!sources.data?.length && !sources.isLoading && <p className="muted" style={{ padding: 8 }}>Hali manba yo‘q.</p>}
          {sources.data?.map((s) => (
            <button key={s.id} className={styles.item} aria-current={s.id === current ? "true" : undefined}
                    onClick={() => setSelected(s.id)}>
              <span className={styles.itemName}>{s.name}</span>
              <span className="row" style={{ gap: 4 }}>
                <Status status={s.status} id={s.id} />
                {s.usage && !s.usage.counted && <span className="badge badge-warning" title="Boshqa manba bilan bir xil ma’lumot">Takroriy</span>}
              </span>
            </button>
          ))}
        </nav>
        <div style={{ minWidth: 0 }}>{current && <SourceDetail key={current} id={current} />}</div>
      </div>
    </div>
  );
}
