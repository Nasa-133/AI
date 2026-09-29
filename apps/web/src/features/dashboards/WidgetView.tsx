"use client";

import { ArrowDownRight, ArrowUpRight, Download, Info, Minus, Table2 } from "lucide-react";
import { useState, type ReactElement } from "react";

import { currencyLabel, formatValue } from "@/shared/format/number";
import { Markdown } from "@/shared/markdown/Markdown";
import { ErrorBoundary } from "@/shared/ui/ErrorBoundary";

import { exportUrl } from "./api";
import { Chart, compact } from "./Chart";
import type { ChartKind } from "./charts";
import styles from "./dashboards.module.css";
import { canDrill } from "./drill";
import { higherIsBetter } from "./filters";
import { ResultTable } from "./ResultTable";
import type { QueryResult, Widget } from "./types";
import { effectiveType } from "./widgetTypes";

const CHARTS = new Set<Widget["type"]>(["line", "area", "bar", "stacked_bar", "pie", "funnel", "heatmap"]);

type Period = { from: string; to: string } | undefined;
const range = (p: Period) => (p ? `${p.from} — ${p.to}` : "");

function metricIndex(data: QueryResult): number {
  return data.columns.findIndex((c) => c.kind === "metric" || c.kind === "current");
}

/** Katta pul summasi ixcham (“1,94 mlrd so‘m”), to‘liq qiymat — sichqoncha ostida. */
function shortValue(value: string, unit: QueryResult["columns"][number]["unit"], currency: string | null): string {
  return unit === "money" && Math.abs(Number(value)) >= 1e6
    ? `${compact(Number(value))} ${currencyLabel(currency)}`.trim()
    : formatValue(value, unit, currency);
}

/**
 * KPI karta: katta qiymat va oldingi teng davr bilan taqqoslash — ikkala davr aniq yoziladi.
 * Ma’lumot yo‘q bo‘lsa bu ochiq aytiladi; u hech qachon nol deb ko‘rsatilmaydi (haqiqiy nol — son).
 */
function Kpi({ data, previous }: { data: QueryResult; previous?: QueryResult | null }) {
  const i = metricIndex(data);
  const column = data.columns[i];
  const unit = column?.unit ?? null;
  const current = data.rows[0]?.[i] ?? null;
  const prevIdx = previous ? metricIndex(previous) : -1;
  const before = previous && prevIdx >= 0 ? previous.rows[0]?.[prevIdx] ?? null : null;
  const curPeriod = data.period ?? data.current_period;
  const prevPeriod = previous?.period ?? previous?.current_period;

  if (current === null) {
    return (
      <div className={styles.kpiBody}>
        <div className={styles.empty}>Joriy davr ({range(curPeriod)}) uchun ma’lumot yo‘q</div>
      </div>
    );
  }
  let delta: ReactElement | null = null;
  if (before !== null && Number(before) !== 0) {
    const pct = ((Number(current) - Number(before)) / Math.abs(Number(before))) * 100;
    const up = pct > 0.05, down = pct < -0.05;
    const good = up ? higherIsBetter(column?.metric_id) : down ? !higherIsBetter(column?.metric_id) : null;
    const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
    delta = (
      <span className={styles.delta} data-good={good === null ? "flat" : String(good)}>
        <Icon aria-hidden /> {up ? "+" : down ? "−" : ""}{Math.abs(pct).toLocaleString("uz", { maximumFractionDigits: 1 })}%
      </span>
    );
  }
  return (
    <div className={styles.kpiBody}>
      <div className={`${styles.widgetKpi} num`} title={formatValue(current, unit, data.currency)}>
        {shortValue(current, unit, data.currency)}
      </div>
      {previous && (
        <div className={styles.compare}>
          {delta}
          <span>
            {before === null
              ? `Oldingi davr (${range(prevPeriod)}) uchun ma’lumot yo‘q`
              : <>oldingi davr ({range(prevPeriod)}): <b className="num">{shortValue(before, unit, previous.currency)}</b></>}
          </span>
        </div>
      )}
    </div>
  );
}

export function WidgetView({ widget, dashboardId, metricNames, onDrill, allowDrill, override, previous,
                             filterNote, loading, failed }: {
  widget: Widget;
  dashboardId: string;
  metricNames: Record<string, string>;
  onDrill: (widget: Widget, member: string) => void;
  allowDrill: boolean;
  /** Dashboard filtri qo‘llangan natija (bo‘lmasa — saqlangan). */
  override?: QueryResult | null;
  previous?: QueryResult | null;
  filterNote?: string | null;
  /** Filtr bo‘yicha qayta hisob kutilmoqda. */
  loading?: boolean;
  /** Filtr bo‘yicha qayta hisob muvaffaqiyatsiz. */
  failed?: boolean;
}) {
  const data = override ?? widget.data;
  const [showTable, setShowTable] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const type = effectiveType(widget, data);
  const empty = Boolean(data && !data.rows.length);
  const isChart = CHARTS.has(type) && !empty;
  const drillable = allowDrill && (type === "line" || type === "bar" || type === "area")
    && data?.rows.some((r) => canDrill(widget.query, r[0]));
  const select = drillable ? (member: string) => onDrill(widget, member) : undefined;
  const period = data?.period ?? data?.current_period;
  const tableFallback = data ? <ResultTable result={data} metricNames={metricNames} /> : null;

  return (
    <section className={`panel ${styles.widget}`} aria-label={widget.title} data-type={type}>
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
        {data && !override && !empty && (
          <a className="btn btn-sm btn-ghost btn-icon" href={exportUrl(dashboardId, widget.id)} download
             title="CSV sifatida yuklab olish" aria-label="CSV"><Download aria-hidden /></a>
        )}
      </div>
      {widget.status === "restricted" && (
        <div className="notice notice-warning">Filialga ruxsat yo‘q — widget boshqa filiallar ma’lumotini ko‘rsatadi.</div>
      )}
      {failed && <div className="notice notice-warning">Filtr bo‘yicha qayta hisoblab bo‘lmadi — saqlangan natija ko‘rsatilmoqda.</div>}
      {widget.type === "text" && widget.text && <div className={styles.textBody}><Markdown source={widget.text} /></div>}
      {loading ? (
        <div className={`skeleton ${styles.loading}`} data-kind={type === "kpi" ? "kpi" : "chart"} aria-label="Yuklanmoqda" />
      ) : (
        <>
          {widget.type !== "text" && !data && widget.status !== "restricted" && (
            <div className="notice notice-warning">Natija topilmadi — manba o‘chirilgan bo‘lishi mumkin.</div>
          )}
          {empty && (
            // Bo‘sh natija — alohida holat: bo‘sh grafik paneli yoki “0” emas.
            <div className={styles.empty}>
              Tanlangan davrda ({range(period)}) ma’lumot yo‘q.
              <span className="muted"> Boshqa davrni tanlang yoki manba yangilanganini tekshiring.</span>
            </div>
          )}
          {data && !empty && type === "kpi" && <Kpi data={data} previous={previous} />}
          {data && isChart && !showTable && (
            <ErrorBoundary fallback={
              <>
                <div className="notice notice-warning">Grafikni chizib bo‘lmadi — ma’lumot jadvalda.</div>
                {tableFallback}
              </>
            }>
              <Chart result={data} type={type as ChartKind} metricNames={metricNames} onSelect={select}
                     height={type === "heatmap" ? 340 : 280} />
            </ErrorBoundary>
          )}
          {data && !empty && (type === "table" || (isChart && showTable)) && (
            <ResultTable result={data} metricNames={metricNames} canSelect={Boolean(drillable)} onSelect={select} />
          )}
        </>
      )}
      {data && (
        <div className={styles.widgetFoot}>
          {data.comparison_period
            ? <span>Joriy: {range(data.current_period)} · Oldingi: {range(data.comparison_period)}</span>
            : period && <span>{range(period)}</span>}
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
