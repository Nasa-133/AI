"use client";

import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { formatValue } from "@/shared/format/number";

import { toSeries } from "./drill";
import type { QueryResult } from "./types";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** O‘q yozuvlari: 1 250 000 000 → “1,25 mlrd”, 480 000 → “480 ming”. */
function compact(value: number): string {
  const abs = Math.abs(value);
  const fmt = (v: number, unit: string) => `${v.toLocaleString("uz", { maximumFractionDigits: 2 })} ${unit}`;
  if (abs >= 1e9) return fmt(value / 1e9, "mlrd");
  if (abs >= 1e6) return fmt(value / 1e6, "mln");
  if (abs >= 1e4) return fmt(value / 1e3, "ming");
  return value.toLocaleString("uz", { maximumFractionDigits: 2 });
}

export function Chart({ result, type, metricNames, onSelect, height = 260 }: {
  result: QueryResult;
  type: "line" | "bar";
  metricNames: Record<string, string>;
  onSelect?: (member: string) => void;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const { categories, labels, series } = toSeries(result);
    const text = cssVar("--text-muted");
    const colors = [1, 2, 3, 4, 5].map((i) => cssVar(`--chart-${i}`));
    chart.setOption({
      color: colors,
      animationDuration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300,
      grid: { left: 8, right: 8, top: series.length > 1 ? 40 : 16, bottom: 8, containLabel: true },
      legend: { show: series.length > 1, top: 0, left: 0, icon: "roundRect", itemWidth: 12,
                itemHeight: 8, textStyle: { color: text } },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => formatValue(v === null ? null : String(v),
                                                    series[0]?.unit ?? null, result.currency),
      },
      xAxis: { type: "category", data: labels, axisLabel: { color: text } },
      yAxis: { type: "value", axisLabel: { color: text, formatter: compact },
                splitLine: { lineStyle: { color: cssVar("--border") } } },
      series: series.map((s) => ({
        name: metricNames[s.name] ?? s.name, type, data: s.values, connectNulls: false,
        cursor: onSelect ? "pointer" : "default",
      })),
    });
    if (onSelect) chart.on("click", (p) => onSelect(categories[p.dataIndex as number]));
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [result, type, metricNames, onSelect]);

  return <div ref={ref} style={{ width: "100%", height }} role="img"
              aria-label="Grafik; aniq qiymatlar pastdagi jadvalda" />;
}
