import Link from "next/link";

import { Markdown } from "@/shared/markdown/Markdown";

import { AGENTS, type ChatMessage } from "./api";
import { FileText, LayoutDashboard } from "lucide-react";

import styles from "./chat.module.css";

export function MessageItem({ message }: { message: ChatMessage }) {
  if (message.author_kind === "user") {
    const docs = (message.structured?.context_documents as { id: string; title: string }[] | undefined) ?? [];
    return (
      <div className={`${styles.msg} ${styles.msgUser}`}>
        {docs.length > 0 && (
          <div className={styles.chipsUser}>
            {docs.map((d) => (
              <Link key={d.id} className={styles.chip} href={`/documents?doc=${d.id}`}><FileText aria-hidden /> {d.title}</Link>
            ))}
          </div>
        )}
        <div className={styles.bubbleUser}>{message.content}</div>
      </div>
    );
  }
  const agent = AGENTS[message.agent_role_key ?? ""];
  const dashboards = (message.structured?.dashboard_ids as string[] | undefined) ?? [];
  const drafts = (message.structured?.document_drafts as { document_id: string; version_id: string }[] | undefined) ?? [];
  const snapshots = message.source_refs.filter((r) => r.kind === "dataset_snapshot").length;
  const docRefs = message.source_refs.filter((r) => r.kind === "document_version").length;
  return (
    <div className={styles.msg}>
      <span className={styles.author}>{agent ? `${agent.name} · ${agent.title}` : "Agent"}</span>
      <div className={styles.bubbleAgent}>
        <Markdown source={message.content} />
      </div>
      <div className={styles.meta}>
        {snapshots > 0 && <span className="badge">Manba: {snapshots} ta snapshot</span>}
        {docRefs > 0 && <span className="badge">Manba: {docRefs} ta hujjat versiyasi</span>}
        {drafts.map((d) => (
          // Draft avtomatik joriy bo‘lmaydi: foydalanuvchi diff’ni ko‘rib o‘zi tasdiqlaydi (TZ 9.3).
          <Link key={d.version_id} className="btn btn-sm"
                href={`/documents?doc=${d.document_id}&compare=${d.version_id}`}>
            Draftni ko‘rib chiqish
          </Link>
        ))}
        {dashboards.map((id) => (
          // Dashboard majburan ochilmaydi — foydalanuvchi o‘zi tanlaydi (TZ 8, U05).
          <Link key={id} className="btn btn-sm" href={`/?dashboard=${id}`}><LayoutDashboard aria-hidden /> Dashboardni ochish</Link>
        ))}
      </div>
    </div>
  );
}
