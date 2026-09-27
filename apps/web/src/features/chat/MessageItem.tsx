import Link from "next/link";

import { Markdown } from "@/shared/markdown/Markdown";

import { AGENTS, type ChatMessage } from "./api";
import styles from "./chat.module.css";

export function MessageItem({ message }: { message: ChatMessage }) {
  if (message.author_kind === "user") {
    return (
      <div className={`${styles.msg} ${styles.msgUser}`}>
        <div className={styles.bubbleUser}>{message.content}</div>
      </div>
    );
  }
  const agent = AGENTS[message.agent_role_key ?? ""];
  const dashboards = (message.structured?.dashboard_ids as string[] | undefined) ?? [];
  const snapshots = message.source_refs.filter((r) => r.kind === "dataset_snapshot").length;
  return (
    <div className={styles.msg}>
      <span className={styles.author}>{agent ? `${agent.name} · ${agent.title}` : "Agent"}</span>
      <div className={styles.bubbleAgent}>
        <Markdown source={message.content} />
      </div>
      <div className={styles.meta}>
        {snapshots > 0 && <span className="badge">Manba: {snapshots} ta snapshot</span>}
        {dashboards.map((id) => (
          // Dashboard majburan ochilmaydi — foydalanuvchi o‘zi tanlaydi (TZ 8, U05).
          <Link key={id} className="btn btn-sm" href={`/?dashboard=${id}`}>Dashboardni ochish</Link>
        ))}
      </div>
    </div>
  );
}
