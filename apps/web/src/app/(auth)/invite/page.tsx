"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { api, unwrap } from "@/api/client";
import { meKey } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { Field } from "@/shared/ui/Field";

import styles from "../auth.module.css";

function AcceptInvitation() {
  const router = useRouter();
  const qc = useQueryClient();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      const session = await unwrap(api.POST("/api/v1/invitations/accept", { body: { token, password } }));
      await qc.invalidateQueries({ queryKey: meKey });
      router.replace(session.mfa_satisfied ? "/" : "/mfa");
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }

  if (!token) return <div className="notice notice-danger">Taklif havolasi to‘liq emas. Xatdagi havolani qayta oching.</div>;
  return (
    <>
      <h1>Taklifni qabul qilish</h1>
      <p className="muted">Yangi hisob uchun parol o‘rnating. Hisobingiz bo‘lsa — joriy parolingizni kiriting.</p>
      <form className={styles.form} onSubmit={submit}>
        <Field label="Parol" type="password" autoComplete="new-password" required minLength={10}
               value={password} onChange={(e) => setPassword(e.target.value)} />
        <ErrorNotice error={error} />
        <button className="btn btn-primary" disabled={pending}>Qo‘shilish</button>
      </form>
    </>
  );
}

export default function InvitePage() {
  return <Suspense><AcceptInvitation /></Suspense>;
}
