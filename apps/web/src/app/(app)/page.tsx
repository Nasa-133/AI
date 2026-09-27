"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useRef } from "react";

import { useMe } from "@/features/auth/api";
import { Board } from "@/features/dashboards/Board";
import { DashboardWindow } from "@/features/dashboards/DashboardWindow";
import { Picker } from "@/features/dashboards/Picker";
import { OfficeFloor } from "@/features/office/OfficeFloor";

function Workspace() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const me = useMe();
  const opener = useRef<string | null>(null);
  const dashboardId = params.get("dashboard");
  const showAll = params.get("dashboards") === "all";

  const open = useCallback((id: string) => {
    opener.current = id;
    router.push(`${pathname}?dashboard=${id}`, { scroll: false });
  }, [router, pathname]);

  const close = useCallback(() => {
    router.push(pathname, { scroll: false });
    // Yopilganda fokus uni ochgan kartochkaga qaytadi (TZ 6).
    const id = opener.current;
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>(`[data-dashboard-card="${id}"]`)?.focus();
    });
  }, [router, pathname]);

  return (
    <>
      <Board onOpen={(id) => open(id)} onShowAll={() => router.push(`${pathname}?dashboards=all`, { scroll: false })} />
      <OfficeFloor />
      {dashboardId && (
        <DashboardWindow id={dashboardId} allowDrill={me.data?.role !== "viewer"}
                         onShowAll={() => router.push(`${pathname}?dashboards=all`, { scroll: false })}
                         onClose={close} />
      )}
      {showAll && !dashboardId && <Picker onOpen={open} onClose={close} />}
    </>
  );
}

export default function Page() {
  return <Suspense><Workspace /></Suspense>;
}
