"use client";

import { useState, type FormEvent } from "react";

import { useMe } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import {
  ROLE_LABEL, useChangeRole, useInvitations, useInvite, useMembers, useRemoveMember, useSetBranchScope,
  type Member, type Role,
} from "./api";

/** Owner istalgan rolni beradi, Admin faqat Analitik/Kuzatuvchi (backend ham tekshiradi). */
function assignable(myRole: string): Role[] {
  return myRole === "owner" ? ["owner", "admin", "analyst", "viewer"] : ["analyst", "viewer"];
}

/** S02: filial doirasi (vergul bilan kodlar; bo‘sh — barcha filiallar). Owner/Admin doim hammasini ko‘radi. */
function BranchScopeCell({ member, editable }: { member: Member; editable: boolean }) {
  const setScope = useSetBranchScope();
  const saved = (member.branch_scope ?? []).join(", ");
  const [draft, setDraft] = useState(saved);
  if (member.role === "owner" || member.role === "admin") return <span className="muted">Barchasi</span>;
  if (!editable) return <span>{saved || "Barchasi"}</span>;
  const codes = draft.split(",").map((c) => c.trim()).filter(Boolean);
  return (
    <form style={{ display: "flex", gap: 6, alignItems: "center" }}
          onSubmit={(e) => { e.preventDefault(); setScope.mutate({ userId: member.user_id, branches: codes.length ? codes : null }); }}>
      <input className="input" style={{ width: 140 }} value={draft} placeholder="Barchasi"
             aria-label={`${member.email} filiallari`} onChange={(e) => setDraft(e.target.value)} />
      {draft !== saved && <button className="btn btn-sm" disabled={setScope.isPending}>Saqlash</button>}
      {setScope.error && <span className="badge badge-danger" role="alert">Xato</span>}
    </form>
  );
}

export function MembersSection() {
  const me = useMe();
  const myRole = me.data?.role ?? "viewer";
  const manager = myRole === "owner" || myRole === "admin";
  const members = useMembers(manager);
  const invitations = useInvitations(manager);
  const invite = useInvite();
  const changeRole = useChangeRole();
  const remove = useRemoveMember();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [sent, setSent] = useState<string | null>(null);

  if (!manager) return null;
  const roles = assignable(myRole);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await invite.mutateAsync({ email, role }).then(() => true).catch(() => false);
    if (ok) { setSent(email); setEmail(""); }
  }

  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h2>A’zolar</h2>
      <ErrorNotice error={members.error ?? changeRole.error ?? remove.error} />
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th>Email</th><th>Rol</th><th title="Bo‘sh — barcha filiallar">Filiallar</th><th>Qo‘shilgan</th><th /></tr></thead>
          <tbody>
            {members.data?.map((m) => {
              const self = m.user_id === me.data?.user_id;
              const editable = !self && (myRole === "owner" || !["owner", "admin"].includes(m.role));
              return (
                <tr key={m.user_id}>
                  <td>{m.email}{self && <span className="badge" style={{ marginLeft: 6 }}>siz</span>}</td>
                  <td>
                    {editable ? (
                      <select className="select" style={{ width: "auto" }} value={m.role}
                              aria-label={`${m.email} roli`}
                              onChange={(e) => changeRole.mutate({ userId: m.user_id, role: e.target.value as Role })}>
                        {[...new Set([m.role, ...roles])].map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                      </select>
                    ) : ROLE_LABEL[m.role]}
                  </td>
                  <td><BranchScopeCell key={(m.branch_scope ?? []).join(",")} member={m} editable={editable} /></td>
                  <td className="muted">{new Date(m.joined_at).toLocaleDateString("uz")}</td>
                  <td>
                    {editable && (
                      <button className="btn btn-sm"
                              onClick={() => window.confirm(`${m.email} korxonadan chiqarilsinmi?`) && remove.mutate(m.user_id)}>
                        Chiqarish
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h3>Taklif qilish</h3>
      <form onSubmit={submit} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="field" style={{ flex: "1 1 240px" }}>
          <span>Email</span>
          <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          <span>Rol</span>
          <select className="select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {roles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </label>
        <button className="btn btn-primary" disabled={invite.isPending}>Taklif yuborish</button>
      </form>
      <ErrorNotice error={invite.error} />
      {sent && <div className="notice" role="status">{sent} manziliga taklif havolasi yuborildi (7 kun amal qiladi).</div>}

      {!!invitations.data?.length && (
        <>
          <h3>Kutilayotgan takliflar</h3>
          <ul style={{ margin: 0 }}>
            {invitations.data.map((i) => (
              <li key={i.id}>{i.email} — {ROLE_LABEL[i.role]} <span className="muted">
                (muddati: {new Date(i.expires_at).toLocaleDateString("uz")})</span></li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
