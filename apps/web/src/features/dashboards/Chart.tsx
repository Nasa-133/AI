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
      grid: { left: 8, right: 8, top: 28, bottom: 8, containLabel: true },
      legend: { show: series.length > 1, textStyle: { color: text } },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: unknown) => formatValue(v === null ? null : String(v),
                                                    series[0]?.unit ?? null, result.currency),
      },
      xAxis: { type: "category", data: labels, axisLabel: { color: text } },
      yAxis: { type: "value", axisLabel: { color: text } },
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
