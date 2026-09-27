"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useRegister } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { Field } from "@/shared/ui/Field";

import styles from "../auth.module.css";

export default function RegisterPage() {
  const router = useRouter();
  const register = useRegister();
  const [form, setForm] = useState({ tenant_name: "", email: "", password: "" });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    const session = await register.mutateAsync(form).catch(() => null);
    if (session) router.replace("/mfa"); // Owner uchun MFA majburiy
  }

  return (
    <>
      <h1>Korxonani ro‘yxatdan o‘tkazish</h1>
      <form className={styles.form} onSubmit={submit}>
        <Field label="Korxona nomi" required minLength={2} value={form.tenant_name}
               onChange={set("tenant_name")} />
        <Field label="Email" type="email" autoComplete="email" required value={form.email}
               onChange={set("email")} />
        <Field label="Parol" type="password" autoComplete="new-password" required minLength={10}
               hint="Kamida 10 belgi." value={form.password} onChange={set("password")} />
        <ErrorNotice error={register.error} />
        <button className="btn btn-primary" disabled={register.isPending}>
          {register.isPending ? "Yaratilmoqda…" : "Yaratish"}
        </button>
      </form>
      <p className={`muted ${styles.footer}`}>
        Hisobingiz bormi? <Link href="/login">Kirish</Link>
      </p>
    </>
  );
}
