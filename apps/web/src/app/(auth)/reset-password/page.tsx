"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { api, unwrap } from "@/api/client";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { Field } from "@/shared/ui/Field";

import styles from "../auth.module.css";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await unwrap(api.POST("/api/v1/auth/password-reset/confirm", { body: { token, new_password: password } }));
      setDone(true);
    } catch (err) {
      setError(err);
    }
  }

  if (done) {
    return (
      <>
        <h1>Parol yangilandi</h1>
        <p className="muted">Xavfsizlik uchun barcha ochiq sessiyalar yopildi.</p>
        <Link className="btn btn-primary" href="/login">Kirish</Link>
      </>
    );
  }
  return (
    <>
      <h1>Yangi parol</h1>
      <form className={styles.form} onSubmit={submit}>
        <Field label="Yangi parol" type="password" autoComplete="new-password" required minLength={10}
               hint="Kamida 10 belgi." value={password} onChange={(e) => setPassword(e.target.value)} />
        <ErrorNotice error={error} />
        <button className="btn btn-primary" disabled={!token}>Saqlash</button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><ResetForm /></Suspense>;
}
