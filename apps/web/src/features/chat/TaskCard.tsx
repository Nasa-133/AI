"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { AGENTS, keys, TERMINAL, useCancelTask, useTask } from "./api";
import styles from "./chat.module.css";
import { PHASES, useTaskStream } from "./taskStream";

const STATUS: Record<string, [string, string]> = {
  queued: ["Navbatda", "badge"],
  running: ["Ishlamoqda", "badge badge-accent"],
  cancelling: ["Bekor qilinmoqda", "badge badge-warning"],
  succeeded: ["Tayyor", "badge badge-success"],
  partial: ["Qisman natija", "badge badge-warning"],
  failed: ["Xato", "badge badge-danger"],
  cancelled: ["Bekor qilindi", "badge"],
};

function useElapsed(since: number, active: boolean): number {
  const [now, setNow] = useState(since);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return Math.max(0, Math.round((now - since) / 1000));
}

/** Faol vazifa: agent, haqiqiy bosqich va o‘tgan vaqt; soxta progress foizi yo‘q (TZ 6). */
export function TaskCard({ taskId, conversationId, startedAt }: {
  taskId: string; conversationId: string; startedAt: number;
}) {
  const qc = useQueryClient();
  const role = useTask(taskId).data?.agent_role_key ?? "";
  const cancel = useCancelTask();
  const onDone = useCallback(() => {
    void qc.invalidateQueries({ queryKey: keys.messages(conversationId) });
    // Agent dashboard yaratgan bo‘lishi mumkin — doskadagi kartochkalar yangilanadi (TZ 6, U05).
    void qc.invalidateQueries({ queryKey: ["dashboards"] });
  }, [qc, conversationId]);
  const stream = useTaskStream(taskId, onDone);
  const live = !TERMINAL.has(stream.status);
  const elapsed = useElapsed(startedAt, live);
  const [label, badge] = STATUS[stream.status] ?? [stream.status, "badge"];
  const agent = AGENTS[role];

  return (
    <div className={styles.card} aria-live="polite">
      <div className={styles.cardRow}>
        <span className={styles.dot} data-live={live} aria-hidden />
        <strong>{agent?.name ?? "Agent"}</strong>
        <span className="muted">{agent?.title}</span>
        <span className={badge} style={{ marginLeft: "auto" }}>{label}</span>
      </div>
      {live && (
        <div className={styles.cardRow}>
          <span>{stream.phase ? PHASES[stream.phase] ?? stream.phase : "Boshlanishini kutmoqda"}</span>
          <span className="muted num">· {elapsed} s</span>
          {stream.toolCalls > 0 && <span className="muted">· {stream.toolCalls} ta hisob</span>}
          {stream.connection === "reconnecting" && <span className="badge badge-warning">Qayta ulanmoqda</span>}
          <button className="btn btn-sm" style={{ marginLeft: "auto" }}
                  disabled={stream.status === "cancelling" || cancel.isPending}
                  onClick={() => cancel.mutate(taskId)}>
            To‘xtatish
          </button>
        </div>
      )}
      {stream.limitations.length > 0 && (
        <ul className="muted" style={{ margin: 0, paddingLeft: 18 }}>
          {stream.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      )}
    </div>
  );
}
