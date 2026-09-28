"use client";

import { ArrowDownRight, ArrowUpRight, Download, Info, Minus, Table2 } from "lucide-react";
import { useState, type ReactElement } from "react";

import { currencyLabel, formatValue } from "@/shared/format/number";
import { Markdown } from "@/shared/markdown/Markdown";

import { exportUrl } from "./api";
import { Chart, compact } from "./Chart";
import type { ChartKind } from "./charts";
import styles from "./dashboards.module.css";
import { canDrill } from "./drill";
import { higherIsBetter } from "./filters";
import { ResultTable } from "./ResultTable";
import type { QueryResult, Widget } from "./types";

const CHARTS = new Set<Widget["type"]>(["line", "area", "bar", "stacked_bar", "pie", "funnel", "heatmap"]);

function metricIndex(data: QueryResult): number {
  return data.columns.findIndex((c) => c.kind === "metric" || c.kind === "current");
}

/** KPI karta: katta qiymat + oldingi teng davrga nisbatan o‘zgarish (yaxshi — yashil). */
function Kpi({ data, previous }: { data: QueryResult; previous?: QueryResult | null }) {
  const i = metricIndex(data);
  const column = data.columns[i];
  const current = data.rows[0]?.[i] ?? null;
  const before = previous ? previous.rows[0]?.[metricIndex(previous)] ?? null : null;
  let delta: ReactElement | null = null;
  if (current !== null && before !== null && Number(before) !== 0) {
    const pct = ((Number(current) - Number(before)) / Math.abs(Number(before))) * 100;
    const up = pct > 0.05, down = pct < -0.05;
    const good = up ? higherIsBetter(column?.metric_id) : down ? !higherIsBetter(column?.metric_id) : null;
    const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
    delta = (
      <span className={styles.delta} data-good={good === null ? "flat" : String(good)}
            title={`Oldingi davr: ${formatValue(before, column?.unit ?? null, data.currency)}`}>
        <Icon aria-hidden /> {Math.abs(pct).toLocaleString("uz", { maximumFractionDigits: 1 })}% oldingi davrga
      </span>
    );
  }
  // Katta pul summasi ixcham (“1,94 mlrd so‘m”), to‘liq qiymat — sichqoncha ostida.
  const full = formatValue(current, column?.unit ?? null, data.currency);
  const shown = current !== null && column?.unit === "money" && Math.abs(Number(current)) >= 1e6
    ? `${compact(Number(current))} ${currencyLabel(data.currency)}`.trim() : full;
  return (
    <div className={styles.kpiBody}>
      <div className={`${styles.widgetKpi} num`} title={full}>{shown}</div>
      {delta}
    </div>
  );
}

export function WidgetView({ widget, dashboardId, metricNames, onDrill, allowDrill, override, previous,
                             filterNote }: {
  widget: Widget;
  dashboardId: string;
  metricNames: Record<string, string>;
  onDrill: (widget: Widget, member: string) => void;
  allowDrill: boolean;
  /** Dashboard filtri qo‘llangan natija (bo‘lmasa — saqlangan). */
  override?: QueryResult | null;
  previous?: QueryResult | null;
  filterNote?: string | null;
}) {
  const data = override ?? widget.data;
  const [showTable, setShowTable] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const isChart = CHARTS.has(widget.type);
  const drillable = allowDrill && (widget.type === "line" || widget.type === "bar" || widget.type === "area")
    && data?.rows.some((r) => canDrill(widget.query, r[0]));
  const select = drillable ? (member: string) => onDrill(widget, member) : undefined;
  const period = data?.period ?? data?.current_period;

  return (
    <section className={`panel ${styles.widget}`} aria-label={widget.title} data-type={widget.type}>
      <div className={styles.widgetHead}>
        <h3 className={styles.widgetTitle} title={widget.title}>{widget.title}</h3>
        {data && isChart && (
          <button className="btn btn-sm btn-ghost btn-icon btn-toggle" aria-pressed={showTable}
                  title="Ma’lumot (jadval)" aria-label="Ma’lumot jadvali" onClick={() => setShowTable(!showTable)}>
            <Table2 aria-hidden />
          </button>
        )}
        {data && data.notes.length > 0 && (
          <button className="btn btn-sm btn-ghost btn-icon btn-toggle" aria-pressed={showNotes}
                  title="Izohlar" aria-label="Izohlar" onClick={() => setShowNotes(!showNotes)}>
            <Info aria-hidden />
          </button>
        )}
        {data && !override && (
          <a className="btn btn-sm btn-ghost btn-icon" href={exportUrl(dashboardId, widget.id)} download
             title="CSV sifatida yuklab olish" aria-label="CSV"><Download aria-hidden /></a>
        )}
      </div>
      {widget.status === "restricted" && (
        <div className="notice notice-warning">Filialga ruxsat yo‘q — widget boshqa filiallar ma’lumotini ko‘rsatadi.</div>
      )}
      {widget.type === "text" && widget.text && <div className={styles.textBody}><Markdown source={widget.text} /></div>}
      {widget.type !== "text" && !data && widget.status !== "restricted" && (
        <div className="notice notice-warning">Natija topilmadi — manba o‘chirilgan bo‘lishi mumkin.</div>
      )}
      {data && widget.type === "kpi" && <Kpi data={data} previous={previous} />}
      {data && isChart && !showTable && (
        <Chart result={data} type={widget.type as ChartKind} metricNames={metricNames} onSelect={select}
               height={widget.type === "heatmap" ? 340 : 280} />
      )}
      {data && (widget.type === "table" || (isChart && showTable)) && (
        <ResultTable result={data} metricNames={metricNames} canSelect={Boolean(drillable)} onSelect={select} />
      )}
      {data && (
        <div className={styles.widgetFoot}>
          {period && <span>{period.from} — {period.to}</span>}
          {data.currency && <span>· {data.currency}</span>}
          {filterNote && <span className="badge badge-warning">{filterNote}</span>}
          {override && <span className="badge badge-accent">Filtr qo‘llangan</span>}
        </div>
      )}
      {data && showNotes && (
        <ul className={styles.notes}>{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      )}
    </section>
  );
}
