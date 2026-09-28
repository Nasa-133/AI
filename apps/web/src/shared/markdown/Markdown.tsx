import { Fragment } from "react";

import { parseMarkdown, type Inline } from "./parse";

function Inlines({ items }: { items: Inline[] }) {
  return (
    <>
      {items.map((it, i) => {
        if (it.kind === "strong") return <strong key={i}>{it.text}</strong>;
        if (it.kind === "em") return <em key={i}>{it.text}</em>;
        if (it.kind === "code") return <code key={i} className="mono">{it.text}</code>;
        return <Fragment key={i}>{it.text}</Fragment>;
      })}
    </>
  );
}

const NUMERIC = /^-?[\d\s.,]+%?$/;

export function Markdown({ source }: { source: string }) {
  return (
    <div className="md">
      {parseMarkdown(source).map((b, i) => {
        switch (b.kind) {
          case "heading": {
            const Tag = `h${b.level}` as "h2" | "h3" | "h4";
            return <Tag key={i}><Inlines items={b.content} /></Tag>;
          }
          case "paragraph":
            return <p key={i}><Inlines items={b.content} /></p>;
          case "quote":
            return <blockquote key={i} className="md-quote">{b.text}</blockquote>;
          case "list":
            return <ul key={i}>{b.items.map((it, j) => <li key={j}><Inlines items={it} /></li>)}</ul>;
          case "table": {
            // Ustundagi barcha qiymatlar son bo‘lsa — sarlavha ham o‘ngga (raqamlar ustma-ust tekis).
            const numeric = b.header.map((_, k) => b.rows.length > 0 && b.rows.every(
              (r) => NUMERIC.test((r[k] ?? []).map((x) => x.text).join(""))));
            return (
              <div key={i} className="table-wrap">
                <table className="table">
                  <thead><tr>{b.header.map((h, j) => <th key={j} className={numeric[j] ? "num" : undefined}><Inlines items={h} /></th>)}</tr></thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, k) => {
                          const text = c.map((x) => x.text).join("");
                          return <td key={k} className={NUMERIC.test(text) ? "num" : undefined}><Inlines items={c} /></td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }
        }
      })}
    </div>
  );
}
