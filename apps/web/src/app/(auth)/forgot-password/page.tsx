"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { api, unwrap } from "@/api/client";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { Field } from "@/shared/ui/Field";

import styles from "../auth.module.css";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await unwrap(api.POST("/api/v1/auth/password-reset", { body: { email } }));
      setDone(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <h1>Parolni tiklash</h1>
      {done ? (
        // Email mavjudligi oshkor qilinmaydi (backend ham bir xil javob beradi).
        <div className="notice" role="status">
          Agar bu email ro‘yxatdan o‘tgan bo‘lsa, 30 daqiqa amal qiladigan havola yuborildi.
        </div>
      ) : (
        <form className={styles.form} onSubmit={submit}>
          <Field label="Email" type="email" autoComplete="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
          <ErrorNotice error={error} />
          <button className="btn btn-primary">Havola yuborish</button>
        </form>
      )}
      <p className={`muted ${styles.footer}`}><Link href="/login">Kirishga qaytish</Link></p>
    </>
  );
}
