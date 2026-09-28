"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useLogin } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { Field } from "@/shared/ui/Field";

import styles from "../auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const session = await login.mutateAsync({ email, password }).catch(() => null);
    if (session) router.replace(session.mfa_satisfied ? "/" : "/mfa");
  }

  return (
    <>
      <h1>Kirish</h1>
      <form className={styles.form} onSubmit={submit}>
        <Field label="Email" type="email" autoComplete="email" required value={email}
               onChange={(e) => setEmail(e.target.value)} />
        <Field label="Parol" type="password" autoComplete="current-password" required
               value={password} onChange={(e) => setPassword(e.target.value)} />
        <ErrorNotice error={login.error} />
        <button className="btn btn-primary" disabled={login.isPending}>
          {login.isPending ? "Tekshirilmoqda…" : "Kirish"}
        </button>
      </form>
      <p className={`muted ${styles.footer}`}>
        <Link href="/forgot-password">Parolni unutdingizmi?</Link>
      </p>
      <p className={`muted ${styles.footer}`}>
        Korxonangiz hali yo‘qmi? <Link href="/register">Ro‘yxatdan o‘tish</Link>
      </p>
    </>
  );
}
