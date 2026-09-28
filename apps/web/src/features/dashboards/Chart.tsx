"use client";

import { BarChart, FunnelChart, HeatmapChart, LineChart, PieChart } from "echarts/charts";
import {
  GridComponent, LegendComponent, TooltipComponent, VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { formatValue } from "@/shared/format/number";

import { buildOption, type ChartKind } from "./charts";
import type { QueryResult } from "./types";

echarts.use([BarChart, LineChart, PieChart, FunnelChart, HeatmapChart, GridComponent,
  TooltipComponent, LegendComponent, VisualMapComponent, CanvasRenderer]);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** O‘q yozuvlari: 1 250 000 000 → “1,25 mlrd”, 480 000 → “480 ming”. */
export function compact(value: number): string {
  const abs = Math.abs(value);
  // Kasr — vergul bilan (butun ilovadagi `1 234,50` formatiga mos).
  const dec = (v: number) => String(Math.round(v * 100) / 100).replace(".", ",");
  const fmt = (v: number, unit: string) => `${dec(v)} ${unit}`;
  if (abs >= 1e9) return fmt(value / 1e9, "mlrd");
  if (abs >= 1e6) return fmt(value / 1e6, "mln");
  if (abs >= 1e4) return fmt(value / 1e3, "ming");
  return dec(value);
}

export function Chart({ result, type, metricNames, onSelect, height = 280 }: {
  result: QueryResult;
  type: ChartKind;
  metricNames: Record<string, string>;
  onSelect?: (member: string) => void;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const theme = {
      text: cssVar("--text-muted"), border: cssVar("--border"), surface: cssVar("--surface"),
      colors: [1, 2, 3, 4, 5].map((i) => cssVar(`--chart-${i}`)),
    };
    const option = buildOption(result, type, metricNames, theme,
                               (v, unit) => formatValue(v === null ? null : String(v), unit, result.currency),
                               compact) as Record<string, unknown> & { categories?: string[] };
    const { categories, ...rest } = option;
    chart.setOption({
      ...rest,
      animationDuration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300,
    });
    if (onSelect && categories) {
      chart.getZr().setCursorStyle("pointer");
      chart.on("click", (p) => onSelect(categories[p.dataIndex as number]));
    }
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [result, type, metricNames, onSelect]);

  return <div ref={ref} style={{ width: "100%", height }} role="img"
              aria-label="Grafik; aniq qiymatlar “Ma’lumot” jadvalida" />;
}
