"use client";

import { Maximize2 } from "lucide-react";
import { Fragment, useState } from "react";

import { formatNumbersInText } from "@/shared/format/number";
import { Dialog } from "@/shared/ui/Dialog";

import { parseMarkdown, type Block, type Inline } from "./parse";

type Options = { formatNumbers?: boolean; expandTables?: boolean };

function Inlines({ items, formatNumbers }: { items: Inline[]; formatNumbers?: boolean }) {
  const t = (s: string) => (formatNumbers ? formatNumbersInText(s) : s);
  return (
    <>
      {items.map((it, i) => {
        if (it.kind === "strong") return <strong key={i}>{t(it.text)}</strong>;
        if (it.kind === "em") return <em key={i}>{t(it.text)}</em>;
        if (it.kind === "code") return <code key={i} className="mono">{it.text}</code>;
        return <Fragment key={i}>{t(it.text)}</Fragment>;
      })}
    </>
  );
}

const NUMERIC = /^[-−]?[\d\s.,]+%?$/;

function Table({ block, formatNumbers }: { block: Extract<Block, { kind: "table" }>; formatNumbers?: boolean }) {
  // Ustundagi barcha qiymatlar son bo‘lsa — sarlavha ham o‘ngga (raqamlar ustma-ust tekis).
  const numeric = block.header.map((_, k) => block.rows.length > 0 && block.rows.every(
    (r) => NUMERIC.test((r[k] ?? []).map((x) => x.text).join(""))));
  return (
    <div className="table-wrap md-table">
      <table className="table">
        <thead><tr>{block.header.map((h, j) => <th key={j} className={numeric[j] ? "num" : undefined}><Inlines items={h} /></th>)}</tr></thead>
        <tbody>
          {block.rows.map((r, j) => (
            <tr key={j}>
              {r.map((c, k) => (
                <td key={k} className={numeric[k] ? "num" : undefined}><Inlines items={c} formatNumbers={formatNumbers} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Katta jadval (ko‘p ustun yoki qator): tor chatda gorizontal scroll + markaziy oynada ochish. */
function ExpandableTable({ block, formatNumbers, title }: {
  block: Extract<Block, { kind: "table" }>; formatNumbers?: boolean; title: string;
}) {
  const [open, setOpen] = useState(false);
  const big = block.header.length > 3 || block.rows.length > 6;
  return (
    <div className="md-table-box">
      {big && (
        <button type="button" className="btn btn-sm btn-ghost md-expand" onClick={() => setOpen(true)}
                title="Jadvalni katta oynada ochish">
          <Maximize2 aria-hidden /> Kattalashtirish
        </button>
      )}
      <Table block={block} formatNumbers={formatNumbers} />
      {open && (
        <Dialog title={title} onClose={() => setOpen(false)}>
          <Table block={block} formatNumbers={formatNumbers} />
        </Dialog>
      )}
    </div>
  );
}

export function Blocks({ blocks, formatNumbers, expandTables, tableTitle = "Jadval" }: Options & {
  blocks: Block[]; tableTitle?: string;
}) {
  return (
    <div className="md">
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "heading": {
            const Tag = `h${b.level}` as "h2" | "h3" | "h4";
            return <Tag key={i}><Inlines items={b.content} /></Tag>;
          }
          case "paragraph":
            return <p key={i}><Inlines items={b.content} formatNumbers={formatNumbers} /></p>;
          case "quote":
            return <blockquote key={i} className="md-quote">{b.text}</blockquote>;
          case "list":
            return <ul key={i}>{b.items.map((it, j) => <li key={j}><Inlines items={it} formatNumbers={formatNumbers} /></li>)}</ul>;
          case "table":
            return expandTables
              ? <ExpandableTable key={i} block={b} formatNumbers={formatNumbers} title={tableTitle} />
              : <Table key={i} block={b} formatNumbers={formatNumbers} />;
        }
      })}
    </div>
  );
}

export function Markdown({ source, ...options }: Options & { source: string }) {
  return <Blocks blocks={parseMarkdown(source)} {...options} />;
}
