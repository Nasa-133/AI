"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useDashboard, useMetricNames, useRefreshDashboard, useRunQuery } from "./api";
import { EditPanel, SharePanel, VersionsPanel } from "./DashboardPanels";
import { DIMENSION_LABEL, drillQuery, loadView, saveView, type DrillStep } from "./drill";
import styles from "./dashboards.module.css";
import { ResultTable } from "./ResultTable";
import type { QueryResult, Widget } from "./types";
import { WidgetView } from "./WidgetView";

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

  return (
    <div className={styles.overlay} role="region" aria-label="Dashboard oynasi">
      <div className={styles.windowHead}>
        <h2 ref={heading} tabIndex={-1} className={styles.windowTitle}>{d?.title ?? "Dashboard"}</h2>
        {steps.length > 0 && (
          <button className="btn btn-sm" onClick={() => { setSteps([]); setResults({}); }}>Filtrlarni tiklash</button>
        )}
        {d?.can_edit && (
          <>
            <button className="btn btn-sm" aria-pressed={panel === "edit"} onClick={() => setPanel(panel === "edit" ? null : "edit")}>Tahrirlash</button>
            <button className="btn btn-sm" aria-pressed={panel === "share"} onClick={() => setPanel(panel === "share" ? null : "share")}>
              Ulashish{d.visibility === "private" ? " 🔒" : ""}
            </button>
            <button className="btn btn-sm" disabled={refresh.isPending}
                    title="Oxirgi yuklangan ma’lumot bilan qayta hisoblash (yangi versiya)"
                    onClick={() => { setSteps([]); setResults({}); refresh.mutate(); }}>
              {refresh.isPending ? "Yangilanmoqda…" : "Yangilash"}
            </button>
          </>
        )}
        {d && <button className="btn btn-sm" aria-pressed={panel === "versions"} onClick={() => setPanel(panel === "versions" ? null : "versions")}>v{d.version}</button>}
        <button className="btn btn-sm" onClick={onShowAll}>Barcha dashboardlar</button>
        <button className="btn btn-sm btn-primary" onClick={onClose}>Ofisga qaytish</button>
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
          <div className={styles.grid}>
            {d?.widgets.map((w) => (
              <WidgetView key={w.id} widget={w} dashboardId={id} metricNames={metricNames} allowDrill={allowDrill}
                          onDrill={(widget, member) => drill(widget.query, member, 0)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
