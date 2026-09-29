import { AlertTriangle } from "lucide-react";

import { Blocks, Markdown } from "@/shared/markdown/Markdown";

import type { SourceRef } from "./api";
import { structureAnswer, type Answer } from "./answer";
import styles from "./chat.module.css";

/** Tuzilgan javob: xulosa → asosiy raqamlar → keyingi qadam; qolgani yig‘iladi. */
function StructuredAnswer({ answer }: { answer: Answer }) {
  return (
    <div className={styles.answer}>
      {answer.lead.length > 0 && <div className={styles.lead}><Blocks blocks={answer.lead} formatNumbers /></div>}
      {answer.notices.length > 0 && (
        // Ma’lumot yetishmasligi / cheklov — yashirilmaydi.
        <div className={`notice notice-warning ${styles.notices}`} role="note">
          <AlertTriangle aria-hidden />
          <ul>{answer.notices.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
      {answer.numbers && answer.numbers.blocks.length > 0 && (
        <section className={styles.part} aria-label="Asosiy raqamlar">
          <h4 className={styles.partTitle}>Asosiy raqamlar</h4>
          <Blocks blocks={answer.numbers.blocks} formatNumbers expandTables tableTitle="Asosiy raqamlar" />
        </section>
      )}
      {answer.next && answer.next.blocks.length > 0 && (
        <section className={styles.part} aria-label="Keyingi qadam">
          <h4 className={styles.partTitle}>Keyingi qadam</h4>
          <Blocks blocks={answer.next.blocks} />
        </section>
      )}
      {answer.extra.map((s) => (
        <details key={s.title} className={styles.fold}>
          <summary>{s.title}{s.note && <span className="muted"> · {s.note}</span>}</summary>
          <Blocks blocks={s.blocks} formatNumbers expandTables
                  tableTitle={s.note ? `${s.title} (${s.note})` : s.title} />
        </details>
      ))}
      {answer.sources.length > 0 && (
        <details className={styles.fold}>
          <summary>Manbalar <span className="muted">· {answer.sources.length}</span></summary>
          <ul className={styles.sources}>{answer.sources.map((s, i) => <li key={i}>{s.label}</li>)}</ul>
          <details className={styles.tech}>
            <summary>Texnik tafsilot</summary>
            <ul>{answer.sources.map((s, i) => <li key={i} className="mono">{s.raw.replace(/`/g, "")}</li>)}</ul>
          </details>
        </details>
      )}
    </div>
  );
}

/** Agent javobi: tuzilgan bo‘lsa — bo‘limlarga ajratilgan; aks holda oddiy markdown (sonlar formatlangan). */
export function AgentAnswer({ content, refs }: { content: string; refs: SourceRef[] }) {
  const answer = structureAnswer(content, refs);
  return answer ? <StructuredAnswer answer={answer} /> : <Markdown source={content} formatNumbers expandTables />;
}
