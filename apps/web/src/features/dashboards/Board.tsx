"use client";

import { useState } from "react";

import { formatValue } from "@/shared/format/number";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useDashboardCards, useMetricNames } from "./api";
import { useFreshness } from "./freshness";
import styles from "./dashboards.module.css";
import type { DashboardCard } from "./types";

export function CardButton({ card, onOpen, metricNames }: {
  card: DashboardCard; onOpen: (id: string, el: HTMLElement) => void; metricNames: Record<string, string>;
}) {
  return (
    <button className={styles.card} onClick={(e) => onOpen(card.id, e.currentTarget)}
            data-dashboard-card={card.id}>
      <span className={styles.cardTitle} title={card.title}>{card.title}</span>
      {card.period && <span className="muted" style={{ fontSize: 12 }}>{card.period.from} — {card.period.to}</span>}
      {card.kpi ? (
        <>
          <span className="muted" style={{ fontSize: 12 }}>{metricNames[card.kpi.metric_id] ?? card.kpi.metric_id}</span>
          <span className={`${styles.kpi} num`}>{formatValue(card.kpi.value, card.kpi.unit, card.kpi.currency)}</span>
        </>
      ) : (
        // KPI mos bo‘lmasa majburan son qo‘yilmaydi (TZ 6).
        <span className="muted">Grafik va jadval — ochib ko‘ring</span>
      )}
      {card.status === "missing" && <span className="badge badge-warning">Natija topilmadi</span>}
      {card.status === "restricted" && <span className="badge badge-warning">Filialga ruxsat yo‘q</span>}
    </button>
  );
}

/** Ofis tepasidagi ixcham doska: barcha ruxsatli dashboardlar, qidiruv va gorizontal scroll. */
export function Board({ onOpen, onShowAll }: {
  onOpen: (id: string, el: HTMLElement) => void; onShowAll: () => void;
}) {
  const [q, setQ] = useState("");
  const cards = useDashboardCards(q);
  const metricNames = useMetricNames();
  const count = cards.data?.length ?? 0;
  const fresh = useFreshness();

  return (
    <section className={styles.board} aria-label="Dashboardlar doskasi">
      <div className={styles.boardHead}>
        <button className={styles.boardTitle} onClick={onShowAll}>Dashboardlar</button>
        <button className="btn btn-sm" onClick={onShowAll}>Barchasi ({count})</button>
        <input className={`input input-sm ${styles.boardSearch}`} type="search" placeholder="Dashboard qidirish"
               aria-label="Dashboard qidirish" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <ErrorNotice error={cards.error} />
      {fresh.data?.state === "stale" && (
        <div className="notice notice-warning" role="status">
          <strong>Eskirgan</strong> {fresh.data.message}
        </div>
      )}
      <div className={styles.strip}>
        {cards.isLoading && [1, 2, 3].map((i) => <div key={i} className={`skeleton ${styles.card}`} />)}
        {cards.data?.map((c) => <CardButton key={c.id} card={c} onOpen={onOpen} metricNames={metricNames} />)}
        {!cards.isLoading && !count && (
          <p className="muted">
            {q ? "Qidiruv bo‘yicha dashboard topilmadi." : "Hali dashboard yo‘q. Chatda “…ni dashboard qil” deb yozing."}
          </p>
        )}
      </div>
    </section>
  );
}
