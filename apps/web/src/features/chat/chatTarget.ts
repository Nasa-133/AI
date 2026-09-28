"use client";

/**
 * Chatni boshqa joydan ochish (ofis kartasi, vazifalar ro‘yxati): agentni tanlash, suhbatga o‘tish
 * va yozish maydoniga fokus. Holat emas — hodisa: tinglovchilar callback’da reaksiya qiladi.
 */
export type ChatTarget = { agent: string | null; conversationId: string | null };

const listeners = new Set<(target: ChatTarget) => void>();

export const chatTarget = {
  open(next: { agent?: string | null; conversationId?: string | null }) {
    const target = { agent: next.agent ?? null, conversationId: next.conversationId ?? null };
    listeners.forEach((l) => l(target));
  },
  /** Obuna; qaytgan funksiya obunani bekor qiladi (useEffect cleanup’i uchun). */
  listen(listener: (target: ChatTarget) => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};
