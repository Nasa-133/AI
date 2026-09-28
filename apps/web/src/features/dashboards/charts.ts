/**
 * Natija → ECharts sozlamasi (Power BI / Superset uslubidagi vizual turlar). Toza funksiyalar:
 * DOM’siz test qilinadi; Chart komponenti faqat chizadi.
 */
import type { QueryResult, Unit } from "./types";

export type ChartKind = "line" | "area" | "bar" | "stacked_bar" | "pie" | "funnel" | "heatmap";
export type Theme = { text: string; border: string; colors: string[]; surface: string };
type Formatter = (value: number | null, unit: Unit | null) => string;

/** Haqiqiy kesim ustunlari (nom va valyuta yordamchi ustunlarisiz). */
export function realDimensions(result: QueryResult): number[] {
  return result.columns
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.kind === "dimension" && !c.name.endsWith("_name") && c.name !== "currency")
    .map(({ i }) => i);
}

export function valueColumns(result: QueryResult): number[] {
  return result.columns.map((c, i) => ({ c, i }))
    .filter(({ c }) => c.kind === "metric" || c.kind === "current").map(({ i }) => i);
}

/** A’zo yorlig‘i: nom ustuni bo‘lsa — nomi (masalan, “Toshkent”), aks holda kodi. */
export function memberLabel(result: QueryResult, row: (string | null)[], dimIndex: number): string {
  const name = result.columns.findIndex((c) => c.name === `${result.columns[dimIndex].name}_name`);
  return String((name >= 0 && row[name]) || row[dimIndex] || "—");
}

const num = (v: string | null | undefined) => (v === null || v === undefined ? null : Number(v));
const unique = (xs: string[]) => [...new Set(xs)];

/** Ko‘p yoki uzun nomli a’zolar — yotiq ustunlar (top-N o‘qiladigan bo‘ladi). */
export function isHorizontal(labels: string[]): boolean {
  return labels.length > 8 || Math.max(0, ...labels.map((l) => l.length)) > 14;
}

/** Rang shkalasi chegaralari: 10–90 persentil — bitta keskin qiymat butun xaritani “oqartirmaydi”. */
export function colorRange(nums: number[]): { min: number; max: number } {
  if (nums.length === 0) return { min: 0, max: 1 };
  const sorted = [...nums].sort((a, b) => a - b);
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];
  const min = at(0.1), max = at(0.9);
  return max > min ? { min, max } : { min: sorted[0], max: sorted[sorted.length - 1] + 1 };
}

export function buildOption(result: QueryResult, kind: ChartKind, metricNames: Record<string, string>,
                            theme: Theme, format: Formatter, axis: (v: number) => string) {
  const dims = realDimensions(result);
  const values = valueColumns(result);
  const unit = (i: number) => result.columns[i]?.unit ?? null;
  const name = (i: number) => metricNames[result.columns[i].metric_id ?? ""] ?? result.columns[i].metric_id ?? result.columns[i].name;
  const base = {
    color: theme.colors,
    textStyle: { fontFamily: "inherit" },
    tooltip: { confine: true },
  };
  const axisStyle = { axisLabel: { color: theme.text }, axisLine: { lineStyle: { color: theme.border } } };
  const valueAxis = { type: "value", axisLabel: { color: theme.text, formatter: axis },
                      splitLine: { lineStyle: { color: theme.border } } };

  if (kind === "pie" || kind === "funnel") {
    const d = dims[0], v = values[0];
    const data = result.rows.map((r) => ({ name: memberLabel(result, r, d), value: num(r[v]) ?? 0 }));
    if (kind === "pie") {
      return {
        ...base,
        tooltip: { ...base.tooltip, trigger: "item",
                   formatter: (p: { name: string; value: number; percent: number }) =>
                     `${p.name}<br/><b>${format(p.value, unit(v))}</b> · ${p.percent}%` },
        legend: { type: "scroll", bottom: 0, left: "center", icon: "circle", itemWidth: 10, itemHeight: 10,
                  textStyle: { color: theme.text } },
        series: [{ type: "pie", radius: ["42%", "68%"], center: ["50%", "44%"], avoidLabelOverlap: true,
                   itemStyle: { borderColor: theme.surface, borderWidth: 2, borderRadius: 4 },
                   // Ulush foizi bo‘lak ichida; juda kichik bo‘laklarda yozilmaydi (tooltip’da bor).
                   label: { show: true, position: "inside", color: "#fff", fontWeight: 600,
                            formatter: (p: { percent: number }) => (p.percent >= 6 ? `${Math.round(p.percent)}%` : "") },
                   labelLine: { show: false },
                   data }],
      };
    }
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: "item",
                 formatter: (p: { name: string; value: number }) => `${p.name}<br/><b>${format(p.value, unit(v))}</b>` },
      // Yorliqlar o‘ngda: tor bosqichlarda ham o‘qiladi; minSize — kichik bosqich ham ko‘rinadi.
      series: [{ type: "funnel", left: 4, width: "56%", top: 8, bottom: 8, sort: "descending", gap: 3,
                 minSize: "14%",
                 label: { show: true, position: "right", color: theme.text,
                          formatter: (p: { name: string; value: number }) => `${p.name}  ${axis(p.value)}` },
                 labelLine: { show: true, length: 8, lineStyle: { color: theme.border } },
                 itemStyle: { borderColor: theme.surface, borderWidth: 1 }, data }],
    };
  }

  if (kind === "heatmap" || kind === "stacked_bar") {
    const [dx, dy] = dims, v = values[0];
    const xs = unique(result.rows.map((r) => memberLabel(result, r, dx)));
    const ys = unique(result.rows.map((r) => memberLabel(result, r, dy)));
    if (kind === "heatmap") {
      const cells = result.rows.map((r) => [xs.indexOf(memberLabel(result, r, dx)),
                                            ys.indexOf(memberLabel(result, r, dy)), num(r[v])]);
      const nums = cells.map((c) => c[2]).filter((x): x is number => x !== null);
      return {
        ...base,
        tooltip: { ...base.tooltip, position: "top",
                   formatter: (p: { data: [number, number, number] }) =>
                     `${xs[p.data[0]]} · ${ys[p.data[1]]}<br/><b>${format(p.data[2], unit(v))}</b>` },
        grid: { left: 8, right: 8, top: 8, bottom: 64, containLabel: true },
        xAxis: { type: "category", data: xs, splitArea: { show: true }, ...axisStyle },
        yAxis: { type: "category", data: ys, splitArea: { show: true }, ...axisStyle },
        visualMap: { ...colorRange(nums), calculable: true, orient: "horizontal",
                     left: "center", bottom: 0, itemHeight: 120, textStyle: { color: theme.text },
                     inRange: { color: ["#fde2e1", "#fff7d6", "#d8f3e3", "#1a7f4b"] } },
        series: [{ type: "heatmap", data: cells, label: { show: xs.length * ys.length <= 60, color: "#1c2430",
                   formatter: (p: { data: [number, number, number] }) => axis(p.data[2]) },
                   itemStyle: { borderColor: theme.surface, borderWidth: 2 } }],
      };
    }
    const series = ys.map((y) => ({
      name: y, type: "bar", stack: "total", emphasis: { focus: "series" }, barMaxWidth: 36,
      data: xs.map((x) => {
        const row = result.rows.find((r) => memberLabel(result, r, dx) === x && memberLabel(result, r, dy) === y);
        return row ? num(row[v]) : null;
      }),
    }));
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: "axis", axisPointer: { type: "shadow" },
                 valueFormatter: (x: number) => format(x, unit(v)) },
      legend: { type: "scroll", top: 0, left: 0, icon: "roundRect", itemWidth: 12, itemHeight: 8, textStyle: { color: theme.text } },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: xs, ...axisStyle },
      yAxis: valueAxis,
      series,
    };
  }

  // line / area / bar — birinchi kesim bo‘yicha, har ko‘rsatkich alohida seriya.
  const d = dims[0] ?? result.columns.findIndex((c) => c.kind === "dimension");
  const categories = result.rows.map((r) => String(r[d] ?? ""));
  const labels = result.rows.map((r) => (d >= 0 ? memberLabel(result, r, d) : ""));
  const horizontal = kind === "bar" && isHorizontal(labels);
  // Taqqoslash natijasi: joriy va oldingi davr yonma-yon (oldingisi xiraroq).
  const previous = result.columns.map((c, i) => ({ c, i })).filter(({ c }) => c.kind === "previous").map(({ i }) => i);
  const plotted = [...values, ...previous];
  const series = plotted.map((i) => ({
    name: result.columns[i].kind === "previous" ? `${name(i)} (oldingi davr)` : name(i),
    type: kind === "bar" ? "bar" : "line",
    data: result.rows.map((r) => num(r[i])),
    connectNulls: false,
    ...(kind === "area" ? { areaStyle: { opacity: 0.16 }, smooth: true, showSymbol: false } : {}),
    ...(kind === "line" ? { smooth: true, symbolSize: 6 } : {}),
    ...(kind === "bar" ? { barMaxWidth: 36, itemStyle: { borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
                                                         opacity: result.columns[i].kind === "previous" ? 0.45 : 1 } } : {}),
  }));
  const categoryAxis = { type: "category", data: labels, ...axisStyle,
                         ...(horizontal ? { inverse: true } : {}) };
  return {
    ...base,
    categories,
    tooltip: { ...base.tooltip, trigger: "axis", axisPointer: { type: kind === "bar" ? "shadow" : "line" },
               valueFormatter: (x: number) => format(x, unit(values[0])) },
    legend: { show: series.length > 1, top: 0, left: 0, icon: "roundRect", itemWidth: 12, itemHeight: 8,
              textStyle: { color: theme.text } },
    grid: { left: 8, right: 16, top: series.length > 1 ? 36 : 12, bottom: 8, containLabel: true },
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? categoryAxis : valueAxis,
    series,
  };
}
