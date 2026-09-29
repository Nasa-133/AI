"use client";

import { useState } from "react";

import { currencyLabel, formatValue } from "@/shared/format/number";

import { compact } from "./Chart";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useDashboardCards, useMetricNames } from "./api";
import { useFreshness } from "./freshness";
import styles from "./dashboards.module.css";
import type { DashboardCard } from "./types";

/** Mini grafik: haqiqiy vaqt qatori nuqtalari (o‘q va yozuvsiz). */
function Sparkline({ points, label }: { points: string[]; label: string }) {
  const ys = points.map(Number);
  const min = Math.min(...ys), max = Math.max(...ys);
  const w = 88, h = 28, span = max - min || 1;
  const path = ys.map((y, i) => `${((i / (ys.length - 1)) * w).toFixed(1)},${(h - 2 - ((y - min) / span) * (h - 4)).toFixed(1)}`);
  return (
    <svg className={styles.spark} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label}>
      <title>{label}</title>
      <polyline points={path.join(" ")} fill="none" stroke="currentColor" strokeWidth={1.6}
                strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Katta pul summasi kartochkada ixcham (“1,94 mlrd so‘m”), to‘liq qiymat — title’da. */
function kpiText(kpi: NonNullable<DashboardCard["kpi"]>): string {
  const n = Number(kpi.value);
  if (kpi.value !== null && kpi.unit === "money" && Math.abs(n) >= 1e6) {
    return `${compact(n)} ${currencyLabel(kpi.currency)}`.trim();
  }
  return formatValue(kpi.value, kpi.unit, kpi.currency);
}

export function CardButton({ card, onOpen, metricNames }: {
  card: DashboardCard; onOpen: (id: string, el: HTMLElement) => void; metricNames: Record<string, string>;
}) {
  const name = (id: string) => metricNames[id] ?? id;
  return (
    <button className={styles.card} onClick={(e) => onOpen(card.id, e.currentTarget)}
            data-dashboard-card={card.id} data-status={card.status}>
      <span className={styles.cardTitle} title={card.title}>{card.title}</span>
      <span className={styles.cardBody}>
        {card.kpi ? (
          <span className={styles.cardKpi}>
            <span className={`${styles.kpi} num`} title={formatValue(card.kpi.value, card.kpi.unit, card.kpi.currency)}>
              {kpiText(card.kpi)}
            </span>
            <span className={styles.cardMetric}>{name(card.kpi.metric_id)}</span>
          </span>
        ) : card.status === "empty" ? (
          <span className={styles.cardEmpty}>Tanlangan davrda ma’lumot yo‘q</span>
        ) : card.status === "missing" ? (
          <span className="badge badge-warning">Natija topilmadi</span>
        ) : card.status === "restricted" ? (
          <span className="badge badge-warning">Filialga ruxsat yo‘q</span>
        ) : (
          // KPI mos bo‘lmasa majburan son qo‘yilmaydi (TZ 6).
          <span className={styles.cardMetric}>{card.spark ? name(card.spark.metric_id) : "Grafik va jadval"}</span>
        )}
        {card.spark && <Sparkline points={card.spark.points} label={`${name(card.spark.metric_id)} — trend`} />}
      </span>
      {card.period && <span className={styles.cardPeriod}>{card.period.from} — {card.period.to}</span>}
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
        <h2 className={styles.boardTitle}>Dashboardlar</h2>
        <button className="btn btn-sm btn-ghost" onClick={onShowAll}>Barchasi ({count})</button>
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
          <p className={`muted ${styles.stripEmpty}`}>
            {q ? "Qidiruv bo‘yicha dashboard topilmadi." : "Hali dashboard yo‘q. Chatda “…ni dashboard qil” deb yozing."}
          </p>
        )}
      </div>
    </section>
  );
}
