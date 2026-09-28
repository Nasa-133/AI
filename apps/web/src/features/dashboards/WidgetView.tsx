"use client";

import { formatValue } from "@/shared/format/number";
import { Markdown } from "@/shared/markdown/Markdown";

import { exportUrl } from "./api";
import { Chart } from "./Chart";
import { canDrill } from "./drill";
import styles from "./dashboards.module.css";
import { ResultTable } from "./ResultTable";
import type { Widget } from "./types";

export function WidgetView({ widget, dashboardId, metricNames, onDrill, allowDrill }: {
  widget: Widget;
  dashboardId: string;
  metricNames: Record<string, string>;
  onDrill: (widget: Widget, member: string) => void;
  allowDrill: boolean;
}) {
  const { data } = widget;
  const drillable = allowDrill && data?.rows.some((r) => canDrill(widget.query, r[0]));
  const select = drillable ? (member: string) => onDrill(widget, member) : undefined;

  return (
    <section className={`panel ${styles.widget}`} aria-label={widget.title}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h3 style={{ marginRight: "auto" }}>{widget.title}</h3>
        {data && (
          <a className="btn btn-sm" href={exportUrl(dashboardId, widget.id)} download
             title="Jadvalni CSV sifatida yuklab olish">CSV</a>
        )}
      </div>
      {widget.type === "text" && widget.text && <Markdown source={widget.text} />}
      {widget.status === "restricted" && (
        <div className="notice notice-warning">Filialga ruxsat yo‘q — widget boshqa filiallar ma’lumotini ko‘rsatadi.</div>
      )}
      {widget.type !== "text" && !data && widget.status !== "restricted" && (
        <div className="notice notice-warning">Natija topilmadi — manba o‘chirilgan bo‘lishi mumkin.</div>
      )}
      {data && widget.type === "kpi" && (() => {
        const i = data.columns.findIndex((c) => c.kind === "metric" || c.kind === "current");
        return (
          <div className={`${styles.widgetKpi} num`}>
            {formatValue(data.rows[0]?.[i] ?? null, data.columns[i]?.unit ?? null, data.currency)}
          </div>
        );
      })()}
      {data && (widget.type === "line" || widget.type === "bar") && (
        <Chart result={data} type={widget.type} metricNames={metricNames} onSelect={select} />
      )}
      {data && widget.type !== "kpi" && (
        <ResultTable result={data} metricNames={metricNames} canSelect={Boolean(drillable)} onSelect={select} />
      )}
      {data && (
        <p className="muted" style={{ fontSize: 12 }}>
          Davr: {(data.period ?? data.current_period)?.from} — {(data.period ?? data.current_period)?.to}
          {data.currency ? ` · ${data.currency}` : ""} · snapshot: {data.dataset_snapshot_ids.length} ta
          {data.notes.map((n) => <span key={n} style={{ display: "block" }}>⚠ {n}</span>)}
        </p>
      )}
    </section>
  );
}
