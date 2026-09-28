"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

export type AgentStateKey =
  | "idle" | "queued" | "reading" | "analyzing" | "drafting" | "awaiting_input"
  | "awaiting_approval" | "completed" | "failed" | "cancelled";

export type OfficeTask = {
  id: string; mine: boolean; title: string | null; conversation_id: string | null;
  agent_role_key: string; status: string; phase: string | null; kind: string;
  error_code: string | null; queue_position: number | null; created_at: string; updated_at: string;
  agent_name?: string; agent_title?: string;
};
export type OfficeAgent = {
  role_key: string; name: string; title: string; state: AgentStateKey; partial: boolean;
  active_count: number; limit: number; queue_length: number;
  current_task: OfficeTask | null; tasks: OfficeTask[];
  last_result: AgentResult | null;
};
export type AgentResult = OfficeTask & {
  answer: string; truncated: boolean; dashboard_ids: string[];
  document_drafts: { document_id: string; version_id: string }[]; source_count: number;
};
export type Office = { agents: OfficeAgent[]; idle_after_seconds: number; generated_at: string };

/** Holat backend’dan (task/step’dan hosil qilingan) — UI o‘zidan holat o‘ylab topmaydi (TZ 6). */
export function useOffice() {
  return useQuery({
    queryKey: ["office"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/office"))) as unknown as Office,
    refetchInterval: (q) => {
      const agents = q.state.data?.agents ?? [];
      // Faol ish bo‘lsa tez-tez; yakuniy holat 30 s dan so‘ng “bo‘sh”ga qaytishi uchun ham.
      return agents.some((a) => a.state !== "idle") ? 2000 : 10_000;
    },
  });
}

export function useMyTasks() {
  return useQuery({
    queryKey: ["tasks"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/tasks"))) as unknown as OfficeTask[],
    refetchInterval: (q) => ((q.state.data ?? []).some((t) => ["queued", "running"].includes(t.status)) ? 2000 : false),
  });
}

export const STATE_LABEL: Record<AgentStateKey, string> = {
  idle: "Bo‘sh",
  queued: "Navbatda",
  reading: "O‘qimoqda",
  analyzing: "Tahlil qilmoqda",
  drafting: "Tayyorlamoqda",
  awaiting_input: "Javobingizni kutmoqda",
  awaiting_approval: "Tasdiq kutmoqda",
  completed: "Bajardi",
  failed: "Xato",
  cancelled: "Bekor qilindi",
};

export function stateLabel(a: Pick<OfficeAgent, "state" | "partial">): string {
  return a.state === "completed" && a.partial ? "Qisman bajardi" : STATE_LABEL[a.state];
}

export const TASK_STATUS: Record<string, [string, string]> = {
  queued: ["Navbatda", "badge"],
  running: ["Ishlamoqda", "badge badge-accent"],
  awaiting_input: ["Javob kutmoqda", "badge badge-warning"],
  succeeded: ["Tayyor", "badge badge-success"],
  partial: ["Qisman", "badge badge-warning"],
  failed: ["Xato", "badge badge-danger"],
  cancelled: ["Bekor qilindi", "badge"],
};
