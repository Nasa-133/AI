"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useLogout, useSwitchTenant, type Me } from "@/features/auth/api";
import { chatTarget } from "@/features/chat/chatTarget";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { ThemeSelect } from "@/shared/theme/ThemeSelect";

import styles from "./shell.module.css";

const NAV = [
  { href: "/", label: "Ofis", icon: "⌂" },
  { href: "/?dashboards=all", label: "Dashboardlar", icon: "▦" },
  { href: "/documents", label: "Hujjatlar", icon: "▤" },
  { href: "/tasks", label: "Vazifalar", icon: "☰" },
  { href: "/integrations", label: "Integratsiyalar", icon: "⇄" },
  { href: "/settings", label: "Sozlamalar", icon: "⚙" },
] as const;


export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useLogout();
  const switchTenant = useSwitchTenant();
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [mobileView, setMobileView] = useState<"main" | "chat">("main");
  const current = me.memberships.find((m) => m.tenant_id === me.current_tenant_id);
  // “Chatga yozish” — chat yig‘ilgan bo‘lsa ochiladi, mobil’da chat ko‘rinishiga o‘tiladi.
  useEffect(() => chatTarget.listen(() => {
    setChatCollapsed(false);
    setMobileView("chat");
  }), []);

  return (
    <div className={styles.shell} data-nav={navCollapsed ? "collapsed" : "open"}
         data-chat={chatCollapsed ? "collapsed" : "open"} data-mobile-view={mobileView}>
      <nav className={styles.nav} aria-label="Asosiy bo‘limlar">
        <div className={styles.brand}>{navCollapsed ? "AI" : "AI Business Office"}</div>
        {NAV.map((item) => (
          <Link key={item.href} href={item.href} className={styles.navLink}
                aria-current={pathname === item.href.split("?")[0] && item.href !== "/?dashboards=all"
                  ? "page" : undefined}
                title={item.label}>
            <span className={styles.navIcon} aria-hidden>{item.icon}</span>
            {!navCollapsed && item.label}
          </Link>
        ))}
        <div className={styles.navSpacer} />
        <button className="btn btn-ghost btn-sm" onClick={() => setNavCollapsed(!navCollapsed)}
                aria-label={navCollapsed ? "Menyuni kengaytirish" : "Menyuni yig‘ish"}>
          {navCollapsed ? "»" : "« Yig‘ish"}
        </button>
      </nav>

      <header className={styles.top}>
        {me.memberships.length > 1 ? (
          <select className="select" style={{ width: "auto" }} aria-label="Korxona"
                  value={me.current_tenant_id}
                  onChange={(e) => switchTenant.mutate(e.target.value)}>
            {me.memberships.map((m) => (
              <option key={m.tenant_id} value={m.tenant_id}>{m.tenant_name}</option>
            ))}
          </select>
        ) : (
          <strong>{current?.tenant_name}</strong>
        )}
        <span className="badge">{me.role}</span>
        <div className={styles.topSpacer} />
        <span className={styles.desktopOnly}><ThemeSelect /></span>
        <span className={`muted ${styles.desktopOnly}`}>{me.email}</span>
        <button className={`btn btn-ghost btn-sm ${styles.desktopOnly}`} onClick={() => setChatCollapsed(!chatCollapsed)}
                aria-pressed={!chatCollapsed}>
          {chatCollapsed ? "Chatni ochish" : "Chatni yig‘ish"}
        </button>
        <button className="btn btn-sm"
                onClick={() => logout.mutate(undefined, { onSettled: () => router.replace("/login") })}>
          Chiqish
        </button>
      </header>

      <main className={styles.main}>{children}</main>
      <aside className={styles.chat} aria-label="Chat">
        {!chatCollapsed && <ChatPanel />}
      </aside>

      <nav className={styles.mobileNav} aria-label="Mobil navigatsiya">
        <Link href="/" onClick={() => setMobileView("main")}>⌂<span>Ofis</span></Link>
        <Link href="/?dashboards=all" onClick={() => setMobileView("main")}>▦<span>Dashboard</span></Link>
        <button onClick={() => setMobileView("chat")}>✉<span>Chat</span></button>
        <Link href="/documents" onClick={() => setMobileView("main")}>▤<span>Hujjat</span></Link>
        <Link href="/integrations" onClick={() => setMobileView("main")}>⇄<span>Ma’lumot</span></Link>
        <Link href="/settings" onClick={() => setMobileView("main")}>⚙<span>Sozlamalar</span></Link>
      </nav>
    </div>
  );
}
