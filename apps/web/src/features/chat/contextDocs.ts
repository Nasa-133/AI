"use client";

import { useSyncExternalStore } from "react";

/** Chatga kontekst sifatida biriktirilgan hujjatlar (chip). Sahifalar orasida umumiy holat. */
export type ContextDoc = { id: string; title: string };

const MAX = 10;
let docs: ContextDoc[] = [];
const listeners = new Set<() => void>();

function emit(next: ContextDoc[]) {
  docs = next;
  listeners.forEach((l) => l());
}

export const contextDocs = {
  add(doc: ContextDoc) {
    if (!docs.some((d) => d.id === doc.id)) emit([...docs, doc].slice(-MAX));
  },
  remove(id: string) { emit(docs.filter((d) => d.id !== id)); },
  clear() { if (docs.length) emit([]); },
  get: () => docs,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};

const EMPTY: ContextDoc[] = [];

export function useContextDocs(): ContextDoc[] {
  return useSyncExternalStore(contextDocs.subscribe, contextDocs.get, () => EMPTY);
}
