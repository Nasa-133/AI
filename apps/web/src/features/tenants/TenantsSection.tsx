"use client";

import { useMutation } from "@tanstack/react-query";
import { Building2, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, unwrap } from "@/api/client";
import { useMe, useSwitchTenant } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

/** Foydalanuvchining korxonalari: har biri alohida ma’lumot (masalan, asosiy va test korxona). */
export function TenantsSection() {
  const me = useMe();
  const switchTenant = useSwitchTenant();
  const [name, setName] = useState("");
  const add = useMutation({
    mutationFn: (tenantName: string) => unwrap(api.POST("/api/v1/tenants/additional", {
      body: { tenant_name: tenantName },
    })) as Promise<{ tenant_id: string }>,
    onSuccess: ({ tenant_id }) => { setName(""); switchTenant.mutate(tenant_id); },
  });
  if (!me.data) return null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (name.trim()) add.mutate(name.trim());
  }

  return (
    <section className="panel panel-pad stack" aria-labelledby="tenants-h">
      <h2 id="tenants-h">Korxonalar</h2>
      <p className="muted">Har korxonaning ma’lumoti, integratsiyalari va dashboardlari alohida. Tepadagi menyudan almashtiriladi.</p>
      <ul className="stack-sm" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {me.data.memberships.map((m) => {
          const current = m.tenant_id === me.data?.current_tenant_id;
          return (
            <li key={m.tenant_id} className="row" style={{ justifyContent: "space-between" }}>
              <span className="icon-text"><Building2 aria-hidden /> {m.tenant_name}
                <span className="badge badge-outline">{m.role}</span>
                {current && <span className="badge badge-success">joriy</span>}
              </span>
              {!current && (
                <button className="btn btn-sm" disabled={switchTenant.isPending}
                        onClick={() => switchTenant.mutate(m.tenant_id)}>O‘tish</button>
              )}
            </li>
          );
        })}
      </ul>
      <form className="row-end" onSubmit={submit}>
        <label className="field grow" style={{ maxWidth: 360 }}>
          <span>Yangi korxona nomi</span>
          <input className="input" value={name} maxLength={200} placeholder="Masalan: Test korxona"
                 onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="btn" disabled={!name.trim() || add.isPending}><Plus aria-hidden /> Korxona qo‘shish</button>
      </form>
      <ErrorNotice error={add.error ?? switchTenant.error} />
    </section>
  );
}
