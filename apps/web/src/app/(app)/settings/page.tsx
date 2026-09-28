"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { AuditSection } from "@/features/audit/AuditSection";
import { BudgetSection } from "@/features/budget/BudgetSection";
import { PrivacySection } from "@/features/budget/PrivacySection";
import { MembersSection } from "@/features/members/MembersSection";
import { TenantsSection } from "@/features/tenants/TenantsSection";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

type Settings = { settings: { version: number; settings: Record<string, unknown>; approved_at: string } | null };

export default function SettingsPage() {
  const qc = useQueryClient();
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => unwrap(api.GET("/api/v1/metrics")) });
  const approve = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/metric-settings/approve", { body: {} })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["metrics"] }),
  });
  const current = (metrics.data as Settings | undefined)?.settings;

  return (
    <div className="page" style={{ maxWidth: 860 }}>
      <div className="page-head">
        <div>
          <h1>Sozlamalar</h1>
          <p>Hisob qoidalari, AI budjeti, maxfiylik, a’zolar va audit jurnali.</p>
        </div>
      </div>
      <section className="panel panel-pad stack">
        <h2>Hisob qoidalari (metrika sozlamalari)</h2>
        <p className="muted">
          Tasdiqlanmaguncha moliyaviy xulosa chiqarilmaydi (TZ 7.1). Joriy standart:
        </p>
        <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 2 }}>
          <li>Summalar QQSsiz hisoblanadi.</li>
          <li>Qaytarishlar sof savdodan ayriladi.</li>
          <li>Manbada ayrilgan chegirma qayta ayrilmaydi.</li>
          <li>Faqat tasdiqlangan hujjatlar hisobga olinadi.</li>
        </ul>
        {current ? (
          <div className="notice notice-success">Tasdiqlangan: {current.version}-versiya, {new Date(current.approved_at).toLocaleString("uz")}</div>
        ) : (
          <div className="notice notice-warning">Hali tasdiqlanmagan.</div>
        )}
        <ErrorNotice error={metrics.error ?? approve.error} />
        <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={approve.isPending}
                onClick={() => approve.mutate()}>
          {current ? "Qayta tasdiqlash (yangi versiya)" : "Tasdiqlash"}
        </button>
      </section>
      <BudgetSection />
      <PrivacySection />
      <MembersSection />
      <TenantsSection />
      <AuditSection />
    </div>
  );
}
