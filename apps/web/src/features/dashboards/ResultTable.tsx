import { formatValue } from "@/shared/format/number";

import { DIMENSION_LABEL } from "./drill";
import type { QueryResult } from "./types";

export function ResultTable({ result, metricNames, onSelect, canSelect }: {
  result: QueryResult;
  metricNames: Record<string, string>;
  onSelect?: (member: string) => void;
  canSelect?: boolean;
}) {
  const header = (c: QueryResult["columns"][number]) => {
    if (c.kind === "dimension") {
      return c.name.endsWith("_name") ? "Nomi" : DIMENSION_LABEL[c.name] ?? c.name;
    }
    const base = metricNames[c.metric_id ?? ""] ?? c.metric_id ?? c.name;
    const suffix: Record<string, string> = { current: "joriy", previous: "oldingi", abs_change: "farq", pct_change: "o‘zgarish %" };
    return suffix[c.kind] ? `${base} (${suffix[c.kind]})` : base;
  };
  if (!result.rows.length) return <p className="muted">Bu kesimda ma’lumot yo‘q.</p>;
  return (
    <div style={{ overflowX: "auto", maxHeight: 360 }}>
      <table className="table">
        <thead>
          <tr>{result.columns.map((c) => <th key={c.name} className={c.kind === "dimension" ? undefined : "num"}>{header(c)}</th>)}</tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => {
                const c = result.columns[j];
                if (c.kind === "dimension") {
                  const clickable = j === 0 && canSelect && onSelect && cell;
                  return (
                    <td key={j}>
                      {clickable ? (
                        <button className="btn btn-ghost btn-sm" style={{ padding: 0, minHeight: 0 }}
                                onClick={() => onSelect(cell)}>{cell} ›</button>
                      ) : cell ?? "—"}
                    </td>
                  );
                }
                return <td key={j} className="num">{formatValue(cell, c.unit, result.currency)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
