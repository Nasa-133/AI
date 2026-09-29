"use client";

import { ChevronDown, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useLogout, type Me } from "@/features/auth/api";
import { ThemeSelect } from "@/shared/theme/ThemeSelect";

import styles from "./shell.module.css";

const ROLE: Record<string, string> = {
  owner: "Egasi (owner)", admin: "Administrator", analyst: "Analitik", viewer: "Kuzatuvchi",
};

/** Ixcham account menyusi: profil, email, mavzu va chiqish bitta joyda. */
export function AccountMenu({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const logout = useLogout();
  const initials = me.email.slice(0, 2).toUpperCase();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  return (
    <div className={styles.account} ref={root}>
      <button className={`btn btn-sm btn-ghost ${styles.accountButton}`} aria-haspopup="true" aria-expanded={open}
              aria-label="Akkaunt menyusi" title={me.email} onClick={() => setOpen(!open)}>
        <span className={styles.avatar} aria-hidden>{initials}</span>
        <ChevronDown aria-hidden />
      </button>
      {open && (
        <div className={styles.menu} role="group" aria-label="Akkaunt">
          <div className={styles.menuHead}>
            <span className={styles.avatar} aria-hidden>{initials}</span>
            <span className={styles.menuWho}>
              <strong title={me.email}>{me.email}</strong>
              <span className="muted">{ROLE[me.role] ?? me.role}</span>
            </span>
          </div>
          <label className={styles.menuRow} htmlFor="account-theme">
            <span>Mavzu</span>
            <ThemeSelect id="account-theme" />
          </label>
          <Link href="/settings" className={styles.menuItem} onClick={() => setOpen(false)}>
            <Settings aria-hidden /> Profil va sozlamalar
          </Link>
          <button className={styles.menuItem} title="Tizimdan chiqish"
                  onClick={() => logout.mutate(undefined, { onSettled: () => router.replace("/login") })}>
            <LogOut aria-hidden /> Chiqish
          </button>
        </div>
      )}
    </div>
  );
}
