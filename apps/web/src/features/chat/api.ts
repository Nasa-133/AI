"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

export type SourceRef = { kind: string; id: string; version_id: string | null; locator: string | null };
export type ChatMessage = {
  id: string;
  author_kind: "user" | "agent";
  agent_role_key: string | null;
  content: string;
  task_id: string | null;
  structured: Record<string, unknown> | null;
  source_refs: SourceRef[];
  created_at: string;
};
export type Conversation = { id: string; title: string; updated_at: string };
export type TaskDetail = {
  id: string; status: string; agent_role_key: string; cancel_requested: boolean;
  error_code: string | null; limitations: string[]; created_at: string;
  steps: { id: string; status: string; phase: string | null }[];
};

export const AGENTS: Record<string, { name: string; title: string }> = {
  coordinator: { name: "Bosh yordamchi", title: "Koordinator" },
  sales_analyst: { name: "Ali", title: "Savdo analitigi" },
  finance_analyst: { name: "Madina", title: "Moliya analitigi" },
  inventory_analyst: { name: "Sardor", title: "Ombor analitigi" },
  document_assistant: { name: "Dilnoza", title: "Hujjat yordamchisi" },
};

export const TERMINAL = new Set(["succeeded", "partial", "failed", "cancelled"]);

export const keys = {
  conversations: ["conversations"] as const,
  messages: (id: string) => ["messages", id] as const,
  task: (id: string) => ["task", id] as const,
};

export function useConversations() {
  return useQuery({
    queryKey: keys.conversations,
    queryFn: async () => (await unwrap(api.GET("/api/v1/conversations"))) as unknown as Conversation[],
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title: string) => unwrap(api.POST("/api/v1/conversations", { body: { title } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.conversations }),
  });
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: keys.messages(conversationId ?? "none"),
    enabled: Boolean(conversationId),
    queryFn: async () => (await unwrap(api.GET("/api/v1/conversations/{conversation_id}/messages", {
      params: { path: { conversation_id: conversationId! } },
    }))) as unknown as ChatMessage[],
  });
}

/** Suhbat ID’si argument sifatida: birinchi xabarda suhbat shu yerning o‘zida yaratiladi. */
export function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { conversationId: string; content: string; agent: string | null;
                          documentIds?: string[] }) =>
      unwrap(api.POST("/api/v1/conversations/{conversation_id}/messages", {
        params: {
          path: { conversation_id: input.conversationId },
          // Tarmoq qayta yuborsa ham bitta task yaratiladi (TZ T04).
          header: { "idempotency-key": crypto.randomUUID() },
        },
        body: { content: input.content, agent: input.agent, document_ids: input.documentIds ?? [] },
      })) as Promise<{ task_id: string; agent_role_key: string; agent_name: string }>,
    onSuccess: (_d, input) => {
      void qc.invalidateQueries({ queryKey: keys.messages(input.conversationId) });
      // Agent darhol o‘z stoliga yo‘l oladi (holat backend’dan: yangi vazifa navbatda).
      void qc.invalidateQueries({ queryKey: ["office"] });
    },
  });
}

export function useTask(taskId: string) {
  return useQuery({
    queryKey: keys.task(taskId),
    queryFn: async () => (await unwrap(api.GET("/api/v1/tasks/{task_id}", {
      params: { path: { task_id: taskId } },
    }))) as unknown as TaskDetail,
  });
}

export function useCancelTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      unwrap(api.POST("/api/v1/tasks/{task_id}/cancel", { params: { path: { task_id: taskId } } })),
    onSuccess: (_d, taskId) => {
      void qc.invalidateQueries({ queryKey: keys.task(taskId) });
      void qc.invalidateQueries({ queryKey: ["tasks"] });
      void qc.invalidateQueries({ queryKey: ["office"] });
    },
  });
}
