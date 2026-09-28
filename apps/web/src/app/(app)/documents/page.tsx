"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { useMe } from "@/features/auth/api";
import { useDocuments, useSearch, useUploadDocument } from "@/features/documents/api";
import { DocumentDetail } from "@/features/documents/DocumentDetail";
import styles from "@/features/documents/documents.module.css";
import { versionStatus } from "@/features/documents/status";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

const ACCEPT = ".docx,.pdf,.txt,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function Documents() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const me = useMe();
  const [filter, setFilter] = useState("");
  const documents = useDocuments(filter.trim());
  const upload = useUploadDocument();
  const search = useSearch();
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);  // yuklangach fayl maydoni tozalanadi
  const selected = params.get("doc") ?? documents.data?.[0]?.id ?? null;
  const compare = params.get("compare");
  const canUpload = me.data?.role !== "viewer";

  const go = (doc: string | null, cmp: string | null = null) => {
    const q = new URLSearchParams();
    if (doc) q.set("doc", doc);
    if (cmp) q.set("compare", cmp);
    router.push(q.size ? `${pathname}?${q}` : pathname, { scroll: false });
  };

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    if (query.trim()) search.mutate(query.trim());
  }

  return (
    <div className={styles.page}>
      <h1>Hujjatlar</h1>
      {canUpload && (
        <section className="panel panel-pad" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div className="field" style={{ minWidth: 260, flex: 1 }}>
            <label htmlFor="doc-file">Hujjat (DOCX, PDF yoki TXT, 25 MB gacha)</label>
            <input key={inputKey} id="doc-file" className="input" type="file" accept={ACCEPT}
                   onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span className="hint">Skaner qilingan PDF matnsiz bo‘lsa, “OCR kerak” deb belgilanadi.</span>
          </div>
          <button className="btn btn-primary" disabled={!file || upload.isPending}
                  onClick={() => file && upload.mutate(file, {
                    onSuccess: ({ id }) => { setFile(null); setInputKey((k) => k + 1); go(id); },
                  })}>
            {upload.isPending ? "Yuklanmoqda…" : "Yuklash"}
          </button>
          <ErrorNotice error={upload.error} />
        </section>
      )}

      <form className="panel panel-pad" style={{ display: "flex", gap: 8, flexWrap: "wrap" }} onSubmit={submitSearch}
            role="search" aria-label="Hujjat qidiruvi">
        <label className="sr-only" htmlFor="doc-search">Hujjatlar ichida qidirish</label>
        <input id="doc-search" className="input" style={{ flex: 1, minWidth: 200 }} value={query}
               placeholder="Masalan: to‘lov muddati" onChange={(e) => setQuery(e.target.value)} />
        <button className="btn" disabled={!query.trim() || search.isPending}>Qidirish</button>
        <ErrorNotice error={search.error} />
        {search.data && (
          <div style={{ flexBasis: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
            {search.data.notes.map((n) => <div key={n} className="notice notice-warning">{n}</div>)}
            {!search.data.results.length && <p className="muted">Hech narsa topilmadi.</p>}
            <ul className={styles.hits}>
              {search.data.results.map((h) => (
                <li key={h.chunk_id}>
                  <button type="button" className="btn" onClick={() => go(h.document_id)}>
                    <strong>{h.document_title} · v{h.version_no} · {h.locator}</strong>
                    <span className="muted">{h.text.length > 240 ? `${h.text.slice(0, 240)}…` : h.text}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>

      <ErrorNotice error={documents.error} />
      <div className={styles.layout}>
        <nav className={styles.list} aria-label="Hujjatlar ro‘yxati">
          <label className="sr-only" htmlFor="doc-filter">Nomi bo‘yicha filtr</label>
          <input id="doc-filter" className="input" placeholder="Nomi bo‘yicha filtr" value={filter}
                 onChange={(e) => setFilter(e.target.value)} />
          {!documents.data?.length && !documents.isLoading && <p className="muted">Hali hujjat yo‘q.</p>}
          {documents.data?.map((d) => {
            const st = d.current ? versionStatus(d.current) : null;
            return (
              <button key={d.id} className={`btn ${styles.item}`}
                      aria-current={d.id === selected ? "true" : undefined} onClick={() => go(d.id)}>
                <span className={styles.itemTitle}>{d.title}</span>
                {st && <span className={st.cls}>{st.label}</span>}
              </button>
            );
          })}
        </nav>
        <div className={styles.main}>
          {selected && (
            <DocumentDetail key={selected} id={selected} compare={compare}
                            onCompare={(v) => go(selected, v)} onDeleted={() => go(null)} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  return <Suspense><Documents /></Suspense>;
}
