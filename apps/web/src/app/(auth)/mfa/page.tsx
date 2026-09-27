"use client";

import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { useEffect, useState, type FormEvent } from "react";

import { useMe, useMfaEnroll, useMfaVerify } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";
import { Field } from "@/shared/ui/Field";

import styles from "../auth.module.css";

export default function MfaPage() {
  const router = useRouter();
  const me = useMe();
  const enroll = useMfaEnroll();
  const verify = useMfaVerify();
  const [code, setCode] = useState("");
  const [qr, setQr] = useState<string | null>(null);

  useEffect(() => {
    if (me.data === null) router.replace("/login");
    if (me.data?.mfa_satisfied) router.replace("/");
  }, [me.data, router]);

  useEffect(() => {
    if (enroll.data) void QRCode.toDataURL(enroll.data.provisioning_uri, { margin: 1 }).then(setQr);
  }, [enroll.data]);

  const needsEnrollment = me.data && !me.data.mfa_enabled;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const result = await verify.mutateAsync(code.trim()).catch(() => null);
    if (result?.mfa_satisfied) router.replace("/");
  }

  return (
    <>
      <h1>Ikki bosqichli tasdiqlash</h1>
      {needsEnrollment && !enroll.data && (
        <>
          <p className="muted">
            Korxona egasi va administratorlari uchun majburiy. Authenticator ilovasini (Google
            Authenticator, Aegis va h.k.) tayyorlang.
          </p>
          <ErrorNotice error={enroll.error} />
          <button className="btn btn-primary" onClick={() => enroll.mutate()} disabled={enroll.isPending}>
            Sozlashni boshlash
          </button>
        </>
      )}
      {enroll.data && (
        <>
          <p className="muted">QR kodni ilovada skanerlang yoki kalitni qo‘lda kiriting.</p>
          {/* QR — data-URL; next/image optimizatsiyasi kerak emas */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {qr && <img className={styles.qr} src={qr} width={180} height={180} alt="MFA QR kod" />}
          <code className={`mono ${styles.secret}`}>{enroll.data.secret}</code>
        </>
      )}
      {(enroll.data || me.data?.mfa_enabled) && (
        <form className={styles.form} onSubmit={submit}>
          <Field label="6 xonali kod" inputMode="numeric" autoComplete="one-time-code"
                 pattern="[0-9]{6}" required value={code} onChange={(e) => setCode(e.target.value)} />
          <ErrorNotice error={verify.error} />
          <button className="btn btn-primary" disabled={verify.isPending}>Tasdiqlash</button>
        </form>
      )}
    </>
  );
}
