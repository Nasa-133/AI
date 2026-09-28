"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { useMe } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

type AuditEvent = {
  id: number; actor_id: string | null; actor_kind: "user" | "agent" | "system"; action: string;
  target_type: string | null; target_id: string | null; ip: string | null; created_at: string;
};

const ACTIONS: Record<string, string> = {
  "tenant.created": "Korxona yaratildi",
  "auth.login": "Tizimga kirish",
  "auth.logout": "Tizimdan chiqish",
  "auth.mfa_verified": "Ikki bosqichli tasdiq",
  "auth.tenant_switched": "Korxona almashtirildi",
  "member.invited": "A’zo taklif qilindi",
  "member.joined": "A’zo qo‘shildi",
  "member.role_changed": "Rol o‘zgartirildi",
  "member.removed": "A’zo chiqarildi",
  "metrics.settings_approved": "Hisob qoidalari tasdiqlandi",
  "budget.updated": "AI budjeti o‘zgartirildi",
  "document.uploaded": "Hujjat yuklandi",
  "document.draft_created": "Hujjat drafti yaratildi",
  "document.promoted": "Hujjat versiyasi joriy qilindi",
  "document.deleted": "Hujjat o‘chirildi",
  "document.shared": "Hujjat ulashildi",
  "dashboard.edited": "Dashboard tahrirlandi",
  "dashboard.shared": "Dashboard ulashildi",
  "integration.created": "Ma’lumot manbasi qo‘shildi",
  "integration.mapping_approved": "Mapping tasdiqlandi",
  "integration.sync_started": "Sinxronlash boshlandi",
  "task.cancelled": "Vazifa bekor qilindi",
  "agent.dashboard_created": "Agent dashboard yaratdi",
  "agent.document_draft_created": "Agent hujjat drafti yaratdi",
};
const ACTOR = { user: "Foydalanuvchi", agent: "AI agent", system: "Tizim" } as const;

/** Audit jurnali (TZ 17–18): faqat egasi va administrator; o‘zgartirib bo‘lmaydi, 365 kun. */
export function AuditSection() {
  const me = useMe();
  const allowed = me.data?.role === "owner" || me.data?.role === "admin";
  const audit = useInfiniteQuery({
    queryKey: ["audit"],
    enabled: allowed,
    initialPageParam: null as number | null,
    queryFn: async ({ pageParam }) => (await unwrap(api.GET("/api/v1/audit", {
      params: { query: { limit: 30, before: pageParam } },
    }))) as unknown as AuditEvent[],
    getNextPageParam: (last) => (last.length === 30 ? last[last.length - 1].id : undefined),
  });
  if (!allowed) return null;
  const events = audit.data?.pages.flat() ?? [];

  return (
    <section className="panel panel-pad" aria-labelledby="audit-h" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h2 id="audit-h">Audit jurnali</h2>
      <p className="muted" style={{ margin: 0 }}>
        Muhim amallar: kim, qachon, nima qildi. Yozuvlarni o‘zgartirib bo‘lmaydi; 365 kun saqlanadi.
      </p>
      <ErrorNotice error={audit.error} />
      <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
        <table className="table">
          <caption className="sr-only">Audit yozuvlari</caption>
          <thead><tr><th>Vaqt</th><th>Amal</th><th>Kim</th><th>Obyekt</th><th>IP</th></tr></thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleString("uz-UZ", { dateStyle: "short", timeStyle: "medium" })}</td>
                <td>{ACTIONS[e.action] ?? e.action}</td>
                <td>{ACTOR[e.actor_kind]}{e.actor_id ? ` · ${e.actor_id.slice(0, 8)}` : ""}</td>
                <td className="mono muted">{e.target_type ? `${e.target_type} ${e.target_id?.slice(0, 8) ?? ""}` : "—"}</td>
                <td className="mono muted">{e.ip ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {audit.hasNextPage && (
        <button className="btn btn-sm" style={{ alignSelf: "flex-start" }} disabled={audit.isFetchingNextPage}
                onClick={() => audit.fetchNextPage()}>
          Oldingilarini ko‘rsatish
        </button>
      )}
    </section>
  );
}
