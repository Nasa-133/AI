"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { useDocuments } from "@/features/documents/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { AGENTS, useConversations, useCreateConversation, useMessages, useSendMessage } from "./api";
import styles from "./chat.module.css";
import { contextDocs, useContextDocs } from "./contextDocs";
import { MessageItem } from "./MessageItem";
import { TaskCard } from "./TaskCard";

const STORAGE_KEY = "abo.conversation";
const SUGGESTIONS = [
  "Ali, o‘tgan oy filiallar savdosini solishtir",
  "Madina, bu oy yalpi foyda nega kamaydi?",
  "Oylar bo‘yicha sof savdoni dashboard qil",
  "Shartnomada to‘lov muddati necha kun?",
];

function remembered(): string | null {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
}
function remember(id: string): void {
  try { localStorage.setItem(STORAGE_KEY, id); } catch { /* shaxsiy rejim — muhim emas */ }
}

export function ChatPanel() {
  const conversations = useConversations();
  const create = useCreateConversation();
  const [selected, setSelected] = useState<string | null>(null);
  const conversationId = useMemo(() => {
    const list = conversations.data ?? [];
    const wanted = selected ?? remembered();
    return list.find((c) => c.id === wanted)?.id ?? list[0]?.id ?? null;
  }, [conversations.data, selected]);
  const messages = useMessages(conversationId);
  const send = useSendMessage();
  const [text, setText] = useState("");
  const [agent, setAgent] = useState<string>("");
  const listRef = useRef<HTMLDivElement>(null);
  const attached = useContextDocs();
  const [picking, setPicking] = useState(false);
  const documents = useDocuments();
  const attachable = (documents.data ?? []).filter(
    (d) => d.current?.parse_status === "ready" && !attached.some((a) => a.id === d.id));

  const items = messages.data ?? [];
  const answered = new Set(items.filter((m) => m.author_kind === "agent").map((m) => m.task_id));
  const pending = items.filter((m) => m.author_kind === "user" && m.task_id && !answered.has(m.task_id));

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [items.length]);

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await create.mutateAsync("Yangi suhbat");
    setSelected(id);
    remember(id);
    return id;
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const content = text.trim();
    if (!content || send.isPending) return;
    const id = await ensureConversation().catch(() => null);
    if (!id) return;
    await send.mutateAsync({ conversationId: id, content, agent: agent || null,
                             documentIds: attached.map((d) => d.id) })
      .then(() => { setText(""); contextDocs.clear(); }).catch(() => {});
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <select className="select" aria-label="Suhbat" value={conversationId ?? ""}
                onChange={(e) => { setSelected(e.target.value); remember(e.target.value); }}
                disabled={!conversations.data?.length}>
          {!conversations.data?.length && <option value="">Suhbat yo‘q</option>}
          {conversations.data?.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
        <button className="btn btn-sm" disabled={create.isPending}
                onClick={() => create.mutate("Yangi suhbat", {
                  onSuccess: ({ id }) => { setSelected(id); remember(id); },
                })}>
          + Yangi
        </button>
      </div>

      <div className={styles.list} ref={listRef}>
        <ErrorNotice error={conversations.error ?? messages.error} />
        {messages.isLoading && <div className="skeleton" style={{ height: 60 }} />}
        {!items.length && !messages.isLoading && (
          <div className={styles.empty}>
            <strong>Savolingizni yozing</strong>
            <span className="muted">Agent hisobni tekshiriladigan vositalar bilan bajaradi va manbani ko‘rsatadi.</span>
            {SUGGESTIONS.map((s) => (
              <button key={s} className={`btn btn-sm ${styles.suggestion}`} onClick={() => setText(s)}>{s}</button>
            ))}
          </div>
        )}
        {items.map((m) => <MessageItem key={m.id} message={m} />)}
        {conversationId && pending.map((m) => (
          <TaskCard key={m.task_id} taskId={m.task_id!} conversationId={conversationId}
                    startedAt={Date.parse(m.created_at)} />
        ))}
      </div>

      <form className={styles.composer} onSubmit={submit}>
        <ErrorNotice error={send.error ?? create.error} />
        <div className={styles.composerRow}>
          <label className="sr-only" htmlFor="chat-agent">Agent</label>
          <select id="chat-agent" className="select" style={{ width: "auto" }} value={agent}
                  onChange={(e) => setAgent(e.target.value)}>
            <option value="">@ avtomatik</option>
            {Object.entries(AGENTS).map(([key, a]) => (
              <option key={key} value={key}>@{a.name} — {a.title}</option>
            ))}
          </select>
          <button type="button" className="btn btn-sm" aria-expanded={picking}
                  onClick={() => setPicking(!picking)}>
            + Hujjat
          </button>
        </div>
        {picking && (
          <div className={styles.picker} role="listbox" aria-label="Hujjat biriktirish">
            {!attachable.length && <span className="muted">Biriktirish uchun tayyor hujjat yo‘q.</span>}
            {attachable.slice(0, 20).map((d) => (
              <button key={d.id} type="button" role="option" aria-selected="false" className="btn btn-sm"
                      onClick={() => { contextDocs.add({ id: d.id, title: d.title }); setPicking(false); }}>
                ▤ {d.title}
              </button>
            ))}
          </div>
        )}
        {attached.length > 0 && (
          <div className={styles.chips} aria-label="Biriktirilgan hujjatlar">
            {attached.map((d) => (
              <span key={d.id} className={styles.chip}>
                ▤ {d.title}
                <button type="button" aria-label={`${d.title} — olib tashlash`}
                        onClick={() => contextDocs.remove(d.id)}>×</button>
              </span>
            ))}
          </div>
        )}
        <div className={styles.composerRow}>
          <label className="sr-only" htmlFor="chat-input">Xabar</label>
          <textarea id="chat-input" className="textarea" rows={2} value={text} maxLength={20000}
                    placeholder="Masalan: Ali, o‘tgan oy filiallar savdosini solishtir"
                    onChange={(e) => setText(e.target.value)} onKeyDown={onKey} />
          <button className="btn btn-primary" disabled={!text.trim() || send.isPending}>Yuborish</button>
        </div>
      </form>
    </section>
  );
}
