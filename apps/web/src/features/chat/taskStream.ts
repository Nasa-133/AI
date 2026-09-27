"use client";

import { useEffect, useReducer } from "react";

/** SSE hodisalaridan task holati (TZ 6: soxta foiz yo‘q — faqat bosqich va o‘tgan vaqt). */
export type StreamState = {
  status: string;
  phase: string | null;
  toolCalls: number;
  limitations: string[];
  connection: "connecting" | "open" | "reconnecting" | "closed";
};

export type StreamEvent =
  | { type: "task.created"; data: { status: string } }
  | { type: "task.progress"; data: { phase: string; tool_calls_used: number } }
  | { type: "task.cancel_requested"; data: Record<string, unknown> }
  | { type: "task.completed"; data: { status: string; limitations: string[] } }
  | { type: "connection"; data: { state: StreamState["connection"] } };

export const initialStream: StreamState = {
  status: "queued", phase: null, toolCalls: 0, limitations: [], connection: "connecting",
};

export function reduceStream(state: StreamState, e: StreamEvent): StreamState {
  switch (e.type) {
    case "task.created":
      return { ...state, status: e.data.status };
    case "task.progress":
      return { ...state, status: "running", phase: e.data.phase, toolCalls: e.data.tool_calls_used };
    case "task.cancel_requested":
      return { ...state, status: "cancelling" };
    case "task.completed":
      return { ...state, status: e.data.status, limitations: e.data.limitations, connection: "closed" };
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

const EVENTS = ["task.created", "task.progress", "task.cancel_requested", "task.completed"] as const;

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
