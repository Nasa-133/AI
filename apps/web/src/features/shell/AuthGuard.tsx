"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useMe, type Me } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

/** Sessiya va MFA talabini tekshiradi; haqiqiy ruxsat har doim backend’da (TZ 3). */
export function AuthGuard({ children }: { children: (me: Me) => ReactNode }) {
  const router = useRouter();
  const me = useMe();

  useEffect(() => {
    if (me.data === null) router.replace("/login");
    else if (me.data && !me.data.mfa_satisfied) router.replace("/mfa");
  }, [me.data, router]);

  if (me.error) {
    return (
      <main style={{ padding: 32, maxWidth: 520 }}>
        <ErrorNotice error={me.error} />
      </main>
    );
  }
  if (!me.data || !me.data.mfa_satisfied) {
    return <main aria-busy="true" style={{ padding: 32 }} className="muted">Yuklanmoqda…</main>;
  }
  return <>{children(me.data)}</>;
}
