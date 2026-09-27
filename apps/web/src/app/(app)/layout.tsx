"use client";

import { AppShell } from "@/features/shell/AppShell";
import { AuthGuard } from "@/features/shell/AuthGuard";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AuthGuard>{(me) => <AppShell me={me}>{children}</AppShell>}</AuthGuard>;
}
