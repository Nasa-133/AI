"use client";

import { useCancelTask } from "@/features/chat/api";
import { chatTarget } from "@/features/chat/chatTarget";
import { PHASES } from "@/features/chat/taskStream";
import { TASK_STATUS, useMyTasks } from "@/features/office/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

const ACTIVE = new Set(["queued", "running", "awaiting_input"]);

function when(iso: string): string {
  return new Date(iso).toLocaleString("uz-UZ", { dateStyle: "short", timeStyle: "short" });
}

/** Mening vazifalarim (TZ 6 “Vazifalar”): holat, agent, navbatdagi o‘rin, to‘xtatish. */
export default function TasksPage() {
  const tasks = useMyTasks();
  const cancel = useCancelTask();
  const items = tasks.data ?? [];

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100 }}>
      <h1>Vazifalar</h1>
      <ErrorNotice error={tasks.error ?? cancel.error} />
      {tasks.isLoading && <div className="skeleton" style={{ height: 120 }} />}
      {!items.length && !tasks.isLoading && (
        <p className="muted">Hali vazifa yo‘q. Chatda savol bering — u shu yerda kuzatiladi.</p>
      )}
      {items.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <caption className="sr-only">Mening vazifalarim</caption>
            <thead>
              <tr><th>Vazifa</th><th>Agent</th><th>Holat</th><th>Bosqich</th><th>Vaqt</th><th /></tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const [label, cls] = TASK_STATUS[t.status] ?? [t.status, "badge"];
                return (
                  <tr key={t.id}>
                    <td style={{ maxWidth: 360, overflowWrap: "anywhere" }}>{t.title}</td>
                    <td>{t.agent_name} <span className="muted">{t.agent_title}</span></td>
                    <td><span className={cls}>{label}</span></td>
                    <td className="muted">
                      {t.queue_position ? `Navbatda ${t.queue_position}-o‘rin`
                        : ACTIVE.has(t.status) && t.phase ? PHASES[t.phase] ?? t.phase : "—"}
                    </td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{when(t.created_at)}</td>
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      {t.conversation_id && (
                        <button className="btn btn-sm btn-ghost"
                                onClick={() => chatTarget.open({ conversationId: t.conversation_id })}>
                          Suhbat
                        </button>
                      )}
                      {(t.status === "queued" || t.status === "running") && (
                        <button className="btn btn-sm" disabled={cancel.isPending}
                                onClick={() => cancel.mutate(t.id)}>
                          To‘xtatish
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
