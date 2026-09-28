"use client";

import {
  Building2, FileText, LayoutDashboard, ListChecks, LogOut, MessageSquare, PanelLeftClose,
  PanelLeftOpen, PanelRightClose, PanelRightOpen, Plug, Settings, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useLogout, useSwitchTenant, type Me } from "@/features/auth/api";
import { useBudget } from "@/features/budget/api";
import { chatTarget } from "@/features/chat/chatTarget";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { ThemeSelect } from "@/shared/theme/ThemeSelect";

import styles from "./shell.module.css";

const NAV: { href: string; label: string; short: string; icon: LucideIcon }[] = [
  { href: "/", label: "Ofis", short: "Ofis", icon: Building2 },
  { href: "/?dashboards=all", label: "Dashboardlar", short: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Hujjatlar", short: "Hujjat", icon: FileText },
  { href: "/tasks", label: "Vazifalar", short: "Vazifa", icon: ListChecks },
  { href: "/integrations", label: "Integratsiyalar", short: "Ma’lumot", icon: Plug },
  { href: "/settings", label: "Sozlamalar", short: "Sozlama", icon: Settings },
];


export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useLogout();
  const switchTenant = useSwitchTenant();
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [mobileView, setMobileView] = useState<"main" | "chat">("main");
  const current = me.memberships.find((m) => m.tenant_id === me.current_tenant_id);
  const budget = useBudget();
  // “Chatga yozish” — chat yig‘ilgan bo‘lsa ochiladi, mobil’da chat ko‘rinishiga o‘tiladi.
  useEffect(() => chatTarget.listen(() => {
    setChatCollapsed(false);
    setMobileView("chat");
  }), []);

  return (
    <div className={styles.shell} data-nav={navCollapsed ? "collapsed" : "open"}
         data-chat={chatCollapsed ? "collapsed" : "open"} data-mobile-view={mobileView}>
      <nav className={styles.nav} aria-label="Asosiy bo‘limlar">
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden>AI</span>
          {!navCollapsed && <span className={styles.brandText}>Business Office</span>}
        </div>
        {NAV.map((item) => (
          <Link key={item.href} href={item.href} className={styles.navLink}
                aria-current={pathname === item.href.split("?")[0] && item.href !== "/?dashboards=all"
                  ? "page" : undefined}
                title={item.label}>
            <item.icon className={styles.navIcon} aria-hidden strokeWidth={1.8} />
            {!navCollapsed && <span>{item.label}</span>}
          </Link>
        ))}
        <div className={styles.navSpacer} />
        <button className={`btn btn-ghost btn-sm ${styles.collapse}`} onClick={() => setNavCollapsed(!navCollapsed)}
                aria-label={navCollapsed ? "Menyuni kengaytirish" : "Menyuni yig‘ish"}
                title={navCollapsed ? "Menyuni kengaytirish" : "Menyuni yig‘ish"}>
          {navCollapsed ? <PanelLeftOpen aria-hidden /> : <><PanelLeftClose aria-hidden /> Yig‘ish</>}
        </button>
      </nav>

      <header className={styles.top}>
        {me.memberships.length > 1 ? (
          <select className="select select-sm select-auto" aria-label="Korxona"
                  value={me.current_tenant_id}
                  onChange={(e) => switchTenant.mutate(e.target.value)}>
            {me.memberships.map((m) => (
              <option key={m.tenant_id} value={m.tenant_id}>{m.tenant_name}</option>
            ))}
          </select>
        ) : (
          <strong className={styles.tenant}>{current?.tenant_name}</strong>
        )}
        <span className="badge badge-outline">{me.role}</span>
        {budget.data && budget.data.state !== "ok" && (
          <Link href="/settings" className={budget.data.state === "exceeded" ? "badge badge-danger" : "badge badge-warning"}
                title="AI budjeti — Sozlamalar">
            AI budjeti {budget.data.percent}%
          </Link>
        )}
        <div className={styles.topSpacer} />
        <span className={styles.desktopOnly}><ThemeSelect /></span>
        <span className={`${styles.email} ${styles.desktopOnly}`} title={me.email}>{me.email}</span>
        <button className={`btn btn-sm ${styles.desktopOnly}`} onClick={() => setChatCollapsed(!chatCollapsed)}
                aria-pressed={!chatCollapsed} title={chatCollapsed ? "Chatni ochish" : "Chatni yig‘ish"}>
          {chatCollapsed ? <PanelRightOpen aria-hidden /> : <PanelRightClose aria-hidden />}
          {chatCollapsed ? "Chatni ochish" : "Chatni yig‘ish"}
        </button>
        <button className="btn btn-sm" title="Tizimdan chiqish"
                onClick={() => logout.mutate(undefined, { onSettled: () => router.replace("/login") })}>
          <LogOut aria-hidden /> Chiqish
        </button>
      </header>

      <main className={styles.main}>{children}</main>
      <aside className={styles.chat} aria-label="Chat">
        {!chatCollapsed && <ChatPanel />}
      </aside>

      <nav className={styles.mobileNav} aria-label="Mobil navigatsiya">
        {NAV.filter((n) => n.href !== "/tasks").slice(0, 2).map((n) => (
          <Link key={n.href} href={n.href} aria-label={n.label} onClick={() => setMobileView("main")}
                aria-current={mobileView === "main" && pathname === n.href.split("?")[0] && n.href === "/" ? "page" : undefined}>
            <n.icon aria-hidden strokeWidth={1.8} /><span>{n.short}</span>
          </Link>
        ))}
        <button onClick={() => setMobileView("chat")} aria-current={mobileView === "chat" ? "page" : undefined}>
          <MessageSquare aria-hidden strokeWidth={1.8} /><span>Chat</span>
        </button>
        {NAV.filter((n) => ["/documents", "/integrations", "/settings"].includes(n.href)).map((n) => (
          <Link key={n.href} href={n.href} aria-label={n.label} onClick={() => setMobileView("main")}
                aria-current={mobileView === "main" && pathname === n.href ? "page" : undefined}>
            <n.icon aria-hidden strokeWidth={1.8} /><span>{n.short}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
