"use client";

import { ArrowLeft, Filter, History, LayoutGrid, Lock, Pencil, RefreshCw, RotateCcw, Share2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useDashboard, useMetricNames, useRefreshDashboard, useRunQuery } from "./api";
import { EditPanel, SharePanel, VersionsPanel } from "./DashboardPanels";
import { DIMENSION_LABEL, drillQuery, loadView, saveView, type DrillStep } from "./drill";
import styles from "./dashboards.module.css";
import {
  applyFilter, isActive, NO_FILTER, PERIOD_LABEL, previousRange, spanFor,
  type DashboardFilter, type PeriodPreset,
} from "./filters";
import { useFreshness } from "./freshness";
import { ResultTable } from "./ResultTable";
import type { QueryResult, Widget } from "./types";
import { WidgetView } from "./WidgetView";
import { effectiveType } from "./widgetTypes";

/**
 * Dashboard tafsiloti — ilova ichidagi oyna (TZ 6): markaziy hudud ustida, chat faol qoladi.
 * Drill-down holati sessiyada dashboard ID bo‘yicha saqlanadi (U07).
 */
export function DashboardWindow({ id, allowDrill, onShowAll, onClose }: {
  id: string;
  allowDrill: boolean;
  onShowAll: () => void;
  onClose: () => void;
}) {
  const dashboard = useDashboard(id);
  const metricNames = useMetricNames();
  const run = useRunQuery();
  const fresh = useFreshness();
  const [steps, setSteps] = useState<DrillStep[]>(() => loadView(id).steps);
  const [results, setResults] = useState<Record<number, QueryResult>>({});
  const heading = useRef<HTMLHeadingElement>(null);
  const [panel, setPanel] = useState<"edit" | "share" | "versions" | null>(null);
  const refresh = useRefreshDashboard(id);

  useEffect(() => { heading.current?.focus(); }, [id]);
  useEffect(() => { saveView(id, { steps }); }, [id, steps]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Tiklangan drill-down qadamlari uchun natijalar qayta so‘raladi (saqlangan spec bo‘yicha).
  const { mutateAsync } = run;
  const inFlight = useRef(new Set<string>());
  useEffect(() => {
    steps.forEach((s, i) => {
      const key = `${i}:${JSON.stringify(s.spec)}`;
      if (results[i] || inFlight.current.has(key)) return;
      inFlight.current.add(key);
      void mutateAsync(s.spec)
        .then((r) => setResults((prev) => ({ ...prev, [i]: r })))
        .finally(() => inFlight.current.delete(key));
    });
  }, [steps, results, mutateAsync]);

  const drill = useCallback((spec: Widget["query"], member: string, depth: number) => {
    const next = spec ? drillQuery(spec, member) : null;
    if (!next) return;
    const step: DrillStep = { dimension: next.dimensions[0], member, label: member, spec: next };
    setSteps((prev) => [...prev.slice(0, depth), step]);
    setResults((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => Number(k) < depth)));
  }, []);

  const d = dashboard.data;
  const last = steps.length ? results[steps.length - 1] : undefined;

  // --- Dashboard filtrlari (davr, filial) va KPI taqqoslash — faqat so‘rov huquqi borlarga. ---
  const filterKey = `abo.dashboard.filter.${id}`;
  const [filter, setFilter] = useState<DashboardFilter>(() => {
    try { return JSON.parse(sessionStorage.getItem(filterKey) ?? "null") ?? NO_FILTER; } catch { return NO_FILTER; }
  });
  useEffect(() => {
    try { sessionStorage.setItem(filterKey, JSON.stringify(filter)); } catch { /* saqlanmasa ham ishlaydi */ }
  }, [filterKey, filter]);
  const [results2, setResults2] = useState<Record<string, QueryResult>>({});
  const [fetchedBranches, setFetchedBranches] = useState<Record<string, string>>({});
  const [failedKeys, setFailedKeys] = useState<Set<string>>(new Set());
  const today = useMemo(() => new Date(), []);
  const active = allowDrill && isActive(filter);
  const sig = `${d?.version ?? 0}|${JSON.stringify(filter)}`;

  // Filial ro‘yxati: widget natijalaridan; bo‘lmasa (masalan, faqat KPI) — bitta yengil so‘rovdan.
  const dataBranches = useMemo(() => {
    const names: Record<string, string> = {};
    for (const w of d?.widgets ?? []) {
      const cols = w.data?.columns ?? [];
      const code = cols.findIndex((c) => c.name === "branch"), name = cols.findIndex((c) => c.name === "branch_name");
      if (code >= 0) w.data!.rows.forEach((row) => { if (row[code]) names[row[code]!] = (name >= 0 && row[name]) || row[code]!; });
    }
    return names;
  }, [d]);
  const branchOptions = Object.keys(dataBranches).length ? dataBranches : fetchedBranches;

  useEffect(() => {
    if (!d || !allowDrill) return;
    let cancelled = false;
    const queried = d.widgets.filter((w) => w.query && w.status === "ready");
    const keep = (key: string) => (r: QueryResult) => {
      if (!cancelled) setResults2((prev) => ({ ...prev, [key]: r }));
    };
    if (!Object.keys(dataBranches).length && queried[0]?.query) {
      const q = queried[0].query;
      void mutateAsync({ ...q, dimensions: ["branch"], filters: {}, limit: null, order_by: null })
        .then((r) => {
          if (cancelled) return;
          const c = r.columns.findIndex((x) => x.name === "branch"), n = r.columns.findIndex((x) => x.name === "branch_name");
          setFetchedBranches(Object.fromEntries(r.rows.map((row) => [row[c]!, (n >= 0 && row[n]) || row[c]!])));
        }).catch(() => undefined);
    }
    for (const w of queried) {
      const spec = applyFilter(w.query!, filter, today);
      if (spec) {
        const key = `${sig}|cur|${w.id}`;
        void mutateAsync(spec).then(keep(key)).catch(() => {
          if (!cancelled) setFailedKeys((prev) => new Set(prev).add(key));
        });
      }
      if (effectiveType(w, w.data) === "kpi") {
        const base = spec ?? w.query!;
        void mutateAsync({ ...base, date_range: previousRange(base.date_range) })
          .then(keep(`${sig}|prev|${w.id}`)).catch(() => undefined);
      }
    }
    return () => { cancelled = true; };
  }, [d, allowDrill, filter, today, mutateAsync, sig, dataBranches]);
  const overrideOf = (wid: string) => (active ? results2[`${sig}|cur|${wid}`] ?? null : null);
  // Filtr qo‘llangan, lekin natija hali kelmagan (yoki xato) — eski raqam “yangi”dek ko‘rsatilmaydi.
  const loadingOf = (w: Widget) => active && Boolean(w.query) && w.status === "ready"
    && !(`${sig}|cur|${w.id}` in results2) && !failedKeys.has(`${sig}|cur|${w.id}`);
  const failedOf = (w: Widget) => active && failedKeys.has(`${sig}|cur|${w.id}`);
  const previousOf = (wid: string) => results2[`${sig}|prev|${wid}`] ?? null;

  const toggleBranch = (code: string) => setFilter((f) => ({
    ...f, branches: f.branches.includes(code) ? f.branches.filter((b) => b !== code) : [...f.branches, code],
  }));

  return (
    <div className={styles.overlay} role="region" aria-label="Dashboard oynasi">
      <div className={styles.windowHead}>
        <button className="btn btn-sm btn-ghost" onClick={onClose} title="Ofisga qaytish (Esc)">
          <ArrowLeft aria-hidden /> Ofisga qaytish
        </button>
        <span className={styles.headDivider} aria-hidden />
        <h2 ref={heading} tabIndex={-1} className={styles.windowTitle}>{d?.title ?? "Dashboard"}</h2>
        {fresh.data?.state === "stale" && (
          <span className="badge badge-warning" title={fresh.data.message ?? undefined}>Eskirgan</span>
        )}
        <div className={styles.headActions}>
          {steps.length > 0 && (
            <button className="btn btn-sm" aria-label="Filtrlarni tiklash" title="Filtrlarni tiklash" onClick={() => { setSteps([]); setResults({}); }}><RotateCcw aria-hidden /><span className={styles.lbl}>Filtrlarni tiklash</span></button>
          )}
          {d?.can_edit && (
            <>
              <button className="btn btn-sm btn-toggle" aria-label="Tahrirlash" title="Tahrirlash" aria-pressed={panel === "edit"} onClick={() => setPanel(panel === "edit" ? null : "edit")}><Pencil aria-hidden /><span className={styles.lbl}>Tahrirlash</span></button>
              <button className="btn btn-sm btn-toggle" aria-pressed={panel === "share"} onClick={() => setPanel(panel === "share" ? null : "share")}
                      title="Ulashish" aria-label={d.visibility === "private" ? "Ulashish (yopiq)" : "Ulashish"}>
                {d.visibility === "private" ? <Lock aria-hidden /> : <Share2 aria-hidden />}<span className={styles.lbl}>Ulashish</span>
              </button>
              <button className="btn btn-sm" disabled={refresh.isPending}
                      aria-label="Yangilash" title="Oxirgi yuklangan ma’lumot bilan qayta hisoblash (yangi versiya)"
                      onClick={() => { setSteps([]); setResults({}); refresh.mutate(); }}>
                <RefreshCw aria-hidden /><span className={styles.lbl}>{refresh.isPending ? "Yangilanmoqda…" : "Yangilash"}</span>
              </button>
            </>
          )}
          {d && <button className="btn btn-sm btn-toggle" aria-pressed={panel === "versions"} title="Versiyalar tarixi" aria-label={`v${d.version} — versiyalar tarixi`}
                        onClick={() => setPanel(panel === "versions" ? null : "versions")}><History aria-hidden /><span className={styles.lbl}>v{d.version}</span></button>}
          <button className="btn btn-sm" aria-label="Barcha dashboardlar" title="Barcha dashboardlar" onClick={onShowAll}><LayoutGrid aria-hidden /><span className={styles.lbl}>Barcha dashboardlar</span></button>
        </div>
      </div>
      <div className={styles.windowBody}>
        <ErrorNotice error={dashboard.error ?? run.error ?? refresh.error} />
        {refresh.data && (
          <div className="notice" role="status">
            {refresh.data.version}-versiya yaratildi.
            {refresh.data.not_refreshed.length > 0 && ` Yangilanmagan: ${refresh.data.not_refreshed.join(", ")}.`}
          </div>
        )}
        {d && panel === "edit" && <EditPanel key={d.version} dashboard={d} onDone={() => setPanel(null)} />}
        {d && panel === "share" && <SharePanel dashboard={d} onDone={() => setPanel(null)} />}
        {d && panel === "versions" && <VersionsPanel dashboard={d} onDone={() => setPanel(null)} />}
        {dashboard.isLoading && <div className="skeleton" style={{ height: 240 }} />}
        {steps.length > 0 && (
          <nav className={styles.crumbs} aria-label="Drill-down yo‘li">
            <button className="btn btn-ghost btn-sm" onClick={() => setSteps([])}>Umumiy</button>
            {steps.map((s, i) => (
              <span key={i} className={styles.crumbs}>
                › <button className="btn btn-ghost btn-sm" aria-current={i === steps.length - 1 ? "step" : undefined}
                          onClick={() => setSteps(steps.slice(0, i + 1))}>
                  {s.label} → {DIMENSION_LABEL[s.dimension]}
                </button>
              </span>
            ))}
          </nav>
        )}
        {steps.length > 0 ? (
          <section className={`panel ${styles.widget}`}>
            <h3>{steps.map((s) => s.label).join(" › ")}: {DIMENSION_LABEL[steps.at(-1)!.dimension]} kesimida</h3>
            {!last && <div className="skeleton" style={{ height: 160 }} />}
            {last && (
              <ResultTable result={last} metricNames={metricNames} canSelect={allowDrill}
                           onSelect={(m) => drill(steps.at(-1)!.spec, m, steps.length)} />
            )}
          </section>
        ) : (
          <>
            {allowDrill && d && d.widgets.some((w) => w.query) && (
              <div className={styles.filterBar} role="group" aria-label="Dashboard filtrlari">
                <span className="icon-text muted"><Filter aria-hidden /> Filtr</span>
                <label className="sr-only" htmlFor="dash-period">Davr</label>
                <select id="dash-period" className="select select-sm select-auto" value={filter.period}
                        onChange={(e) => setFilter((f) => ({ ...f, period: e.target.value as PeriodPreset }))}>
                  {(Object.keys(PERIOD_LABEL) as PeriodPreset[]).map((p) => <option key={p} value={p}>{PERIOD_LABEL[p]}</option>)}
                </select>
                <div className={styles.chips} aria-label="Filiallar">
                  {Object.entries(branchOptions).sort(([a], [b]) => a.localeCompare(b)).map(([code, name]) => (
                    <button key={code} className="btn btn-sm btn-toggle" aria-pressed={filter.branches.includes(code)}
                            onClick={() => toggleBranch(code)} title={name}>{name}</button>
                  ))}
                </div>
                {isActive(filter) && (
                  <button className="btn btn-sm btn-ghost" onClick={() => setFilter(NO_FILTER)}><X aria-hidden /> Tozalash</button>
                )}
              </div>
            )}
            <div className={styles.grid}>
              {d?.widgets.map((w) => (
                <div key={w.id} className={styles.cell} style={{ "--span": spanFor(w) } as CSSProperties}>
                  <WidgetView widget={w} dashboardId={id} metricNames={metricNames} allowDrill={allowDrill}
                              override={overrideOf(w.id)} previous={previousOf(w.id)}
                              loading={loadingOf(w)} failed={failedOf(w)}
                              filterNote={active && !w.query && w.type !== "text" ? "Filtr qo‘llanmaydi" : null}
                              onDrill={(widget, member) => drill(widget.query, member, 0)} />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
