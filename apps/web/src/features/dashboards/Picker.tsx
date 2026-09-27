"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useDashboardCards, useMetricNames } from "./api";
import { CardButton } from "./Board";
import styles from "./dashboards.module.css";

/** Barcha dashboardlarni tanlash oynasi (TZ 6): qidiruv va saralash; ustma-ust modal yo‘q. */
export function Picker({ onOpen, onClose }: { onOpen: (id: string) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"recent" | "title">("recent");
  const cards = useDashboardCards(q);
  const metricNames = useMetricNames();
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => { search.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sorted = useMemo(() => {
    const list = [...(cards.data ?? [])];
    return sort === "title" ? list.sort((a, b) => a.title.localeCompare(b.title, "uz")) : list;
  }, [cards.data, sort]);

  return (
    <div className={styles.overlay} role="region" aria-label="Barcha dashboardlar">
      <div className={styles.windowHead}>
        <h2 className={styles.windowTitle}>Barcha dashboardlar ({sorted.length})</h2>
        <input ref={search} className="input" style={{ maxWidth: 260 }} type="search"
               placeholder="Nomi bo‘yicha qidirish" aria-label="Qidirish" value={q}
               onChange={(e) => setQ(e.target.value)} />
        <select className="select" style={{ width: "auto" }} aria-label="Saralash" value={sort}
                onChange={(e) => setSort(e.target.value as "recent" | "title")}>
          <option value="recent">Oxirgi yangilangan</option>
          <option value="title">Nomi bo‘yicha</option>
        </select>
        <button className="btn btn-sm btn-primary" onClick={onClose}>Ofisga qaytish</button>
      </div>
      <div className={styles.windowBody}>
        <ErrorNotice error={cards.error} />
        <div className={styles.pickerGrid}>
          {sorted.map((c) => <CardButton key={c.id} card={c} metricNames={metricNames} onOpen={(id) => onOpen(id)} />)}
        </div>
        {!cards.isLoading && !sorted.length && <p className="muted">Dashboard topilmadi.</p>}
      </div>
    </div>
  );
}
