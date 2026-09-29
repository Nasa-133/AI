"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { PHASES } from "@/features/chat/taskStream";
import { useCancelTask } from "@/features/chat/api";
import { chatTarget } from "@/features/chat/chatTarget";
import { AgentAnswer } from "@/features/chat/AgentAnswer";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { stateLabel, TASK_STATUS, type AgentResult, type OfficeAgent, type OfficeTask } from "./api";
import styles from "./office.module.css";

function TaskRow({ task }: { task: OfficeTask }) {
  const cancel = useCancelTask();
  const [label, cls] = TASK_STATUS[task.status] ?? [task.status, "badge"];
  return (
    <li className={styles.taskRow}>
      <div className={styles.taskHead}>
        <span className={styles.taskTitle}>{task.mine ? task.title : "Boshqa foydalanuvchi vazifasi"}</span>
        <span className={cls}>{label}</span>
      </div>
      <span className="muted">
        {task.queue_position ? `Navbatda ${task.queue_position}-o‘rin`
          : task.phase ? PHASES[task.phase] ?? task.phase : "Boshlanishini kutmoqda"}
      </span>
      {task.mine && (
        <div className={styles.taskActions}>
          {task.conversation_id && (
            <button className="btn btn-sm" onClick={() => chatTarget.open({ conversationId: task.conversation_id })}>
              Suhbatni ochish
            </button>
          )}
          <button className="btn btn-sm" disabled={cancel.isPending} onClick={() => cancel.mutate(task.id)}>
            To‘xtatish
          </button>
        </div>
      )}
      <ErrorNotice error={cancel.error} />
    </li>
  );
}

function LastResult({ result }: { result: AgentResult }) {
  const [label, cls] = TASK_STATUS[result.status] ?? [result.status, "badge"];
  return (
    <section className={styles.result} aria-label="Oxirgi natija">
      <div className={styles.taskHead}>
        <strong>Oxirgi natija</strong>
        <span className={cls}>{label}</span>
      </div>
      <span className="muted">{result.title}</span>
      {result.answer ? (
        <div className={styles.answer}><AgentAnswer content={result.answer} refs={[]} /></div>
      ) : (
        <span className="muted">Javob matni yo‘q.</span>
      )}
      <div className={styles.taskActions}>
        {result.source_count > 0 && <span className="badge">Manbalar: {result.source_count}</span>}
        {result.dashboard_ids.map((id) => (
          <Link key={id} className="btn btn-sm" href={`/?dashboard=${id}`}>Dashboardni ochish</Link>
        ))}
        {result.document_drafts.map((d) => (
          <Link key={d.version_id} className="btn btn-sm" href={`/documents?doc=${d.document_id}&compare=${d.version_id}`}>
            Draftni ko‘rish
          </Link>
        ))}
        {result.conversation_id && (
          <button className="btn btn-sm" onClick={() => chatTarget.open({ conversationId: result.conversation_id })}>
            {result.truncated ? "To‘liq javob chatda" : "Suhbatni ochish"}
          </button>
        )}
      </div>
    </section>
  );
}

/** Agent yon kartasi (TZ 6): holat, joriy ishlar, navbat, to‘xtatish va chatga yozish.
 * Non-modal: ofis va chat ishlashda davom etadi; Escape yopadi, fokus stolga qaytadi. */
export function AgentPanel({ agent, onClose, onShowOnMap }: {
  agent: OfficeAgent; onClose: () => void; onShowOnMap?: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { ref.current?.focus(); }, [agent.role_key]);
  return (
    <aside ref={ref} tabIndex={-1} className={`panel ${styles.side}`} aria-label={`${agent.name} kartasi`}
           onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}>
      <div className={styles.sideHead}>
        <div>
          <h3>{agent.name}</h3>
          <span className="muted">{agent.title}</span>
        </div>
        <button className="btn btn-sm btn-ghost btn-icon" aria-label="Kartani yopish" title="Yopish" onClick={onClose}><X aria-hidden /></button>
      </div>
      <dl className={styles.facts}>
        <dt>Holat</dt><dd data-state={agent.state}>{stateLabel(agent)}</dd>
        <dt>Joriy ishlar</dt><dd>{agent.active_count} / {agent.limit}</dd>
        <dt>Navbatda</dt><dd>{agent.queue_length}</dd>
      </dl>
      {agent.state === "awaiting_input" && (
        <div className="notice notice-warning">Agent aniqlashtiruvchi savol berdi — chatda javob yozing.</div>
      )}
      {agent.tasks.length > 0 ? (
        <ul className={styles.taskList} aria-label="Faol vazifalar">
          {agent.tasks.map((t) => <TaskRow key={t.id} task={t} />)}
        </ul>
      ) : (
        <p className="muted">Faol vazifa yo‘q.</p>
      )}
      {agent.last_result && <LastResult result={agent.last_result} />}
      <div className={styles.taskActions}>
        <button className="btn btn-primary btn-sm" onClick={() => chatTarget.open({ agent: agent.role_key })}>
          Chatga yozish
        </button>
        {onShowOnMap && (
          <button className="btn btn-sm" onClick={onShowOnMap}>Xaritada ko‘rsatish</button>
        )}
        <Link className="btn btn-sm" href="/tasks">Barcha vazifalar</Link>
      </div>
    </aside>
  );
}
