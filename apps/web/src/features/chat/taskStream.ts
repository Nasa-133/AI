"use client";

import { useEffect, useReducer } from "react";

/** SSE hodisalaridan task holati (TZ 6: soxta foiz yo‘q — faqat bosqich va o‘tgan vaqt). */
export type StreamState = {
  status: string;
  phase: string | null;
  toolCalls: number;
  limitations: string[];
  queuePosition: number | null;
  needsInput: boolean;
  connection: "connecting" | "open" | "reconnecting" | "closed";
};

export type StreamEvent =
  | { type: "task.created"; data: { status: string; queue_position?: number | null } }
  | { type: "task.queued"; data: { queue_position: number | null } }
  | { type: "task.progress"; data: { phase: string; tool_calls_used: number } }
  | { type: "task.cancel_requested"; data: Record<string, unknown> }
  | { type: "task.completed"; data: { status: string; limitations: string[]; needs_input?: boolean } }
  | { type: "connection"; data: { state: StreamState["connection"] } };

export const initialStream: StreamState = {
  status: "queued", phase: null, toolCalls: 0, limitations: [], queuePosition: null,
  needsInput: false, connection: "connecting",
};

export function reduceStream(state: StreamState, e: StreamEvent): StreamState {
  switch (e.type) {
    case "task.created":
      return { ...state, status: e.data.status, queuePosition: e.data.queue_position ?? null };
    case "task.queued":
      return { ...state, queuePosition: e.data.queue_position };
    case "task.progress":
      return { ...state, status: "running", phase: e.data.phase, toolCalls: e.data.tool_calls_used,
               queuePosition: null };
    case "task.cancel_requested":
      return { ...state, status: "cancelling" };
    case "task.completed":
      return { ...state, status: e.data.status, limitations: e.data.limitations, queuePosition: null,
               needsInput: Boolean(e.data.needs_input), connection: "closed" };
    case "connection":
      return state.connection === "closed" ? state : { ...state, connection: e.data.state };
  }
}

export const PHASES: Record<string, string> = {
  planning: "Rejalashtirmoqda",
  reading: "O‘qimoqda",
  retrieving: "Manba qidirmoqda",
  computing: "Hisoblamoqda",
  analyzing: "Tahlil qilmoqda",
  drafting: "Javob tayyorlamoqda",
  waiting_tool: "Hisob natijasini kutmoqda",
};

const EVENTS = ["task.created", "task.queued", "task.progress", "task.cancel_requested", "task.completed"] as const;

export function useTaskStream(taskId: string, onDone: () => void): StreamState {
  const [state, dispatch] = useReducer(reduceStream, initialStream);
  useEffect(() => {
    // EventSource qayta ulanishda Last-Event-ID’ni o‘zi yuboradi — eventlar yo‘qolmaydi (TZ T02).
    const source = new EventSource(`/api/v1/tasks/${taskId}/events`);
    source.onopen = () => dispatch({ type: "connection", data: { state: "open" } });
    source.onerror = () => dispatch({ type: "connection", data: { state: "reconnecting" } });
    for (const name of EVENTS) {
      source.addEventListener(name, (msg) => {
        dispatch({ type: name, data: JSON.parse((msg as MessageEvent).data) } as StreamEvent);
        if (name === "task.completed") {
          source.close();
          onDone();
        }
      });
    }
    return () => source.close();
  }, [taskId, onDone]);
  return state;
}
