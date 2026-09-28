"use client";

import { useState, type FormEvent } from "react";

import { useMe } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useBudget, useUpdateBudget, type Budget } from "./api";

const STATE: Record<Budget["state"], [string, string]> = {
  ok: ["Me’yorda", "badge badge-success"],
  warning: ["80% dan oshdi", "badge badge-warning"],
  exceeded: ["Limit tugagan — yangi AI vazifalar to‘xtatilgan", "badge badge-danger"],
};

function Meter({ label, spent, limit, currency }: { label: string; spent: string; limit: string | null; currency: string }) {
  const ratio = limit && Number(limit) > 0 ? Math.min(Number(spent) / Number(limit), 1) : 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span>{label}</span>
        <span className="num">{spent} / {limit ?? "cheklanmagan"} {currency}</span>
      </div>
      {limit && (
        <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ratio * 100)}
             style={{ height: 8, borderRadius: 4, background: "var(--surface-2)", overflow: "hidden" }}>
          <div style={{ width: `${ratio * 100}%`, height: "100%",
                        background: ratio >= 1 ? "var(--danger)" : ratio >= 0.8 ? "var(--warning)" : "var(--success)" }} />
        </div>
      )}
    </div>
  );
}

/** AI budjeti (TZ 19): sarf, rezerv, 80% ogohlantirish; limitni faqat egasi o‘zgartiradi. */
export function BudgetSection() {
  const me = useMe();
  const budget = useBudget();
  const update = useUpdateBudget();
  const [daily, setDaily] = useState<string | null>(null);
  const [monthly, setMonthly] = useState<string | null>(null);
  const b = budget.data;
  if (!b) return <ErrorNotice error={budget.error} />;
  const owner = me.data?.role === "owner";
  const [label, cls] = STATE[b.state];

  function submit(e: FormEvent) {
    e.preventDefault();
    const norm = (v: string | null, current: string | null) => {
      const value = (v ?? current ?? "").trim().replace(",", ".");
      return value === "" ? null : value;
    };
    update.mutate({ daily_limit: norm(daily, b!.daily_limit), monthly_limit: norm(monthly, b!.monthly_limit) },
                  { onSuccess: () => { setDaily(null); setMonthly(null); } });
  }

  return (
    <section className="panel panel-pad" aria-labelledby="budget-h" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <h2 id="budget-h" style={{ marginRight: "auto" }}>AI budjeti</h2>
        <span className={cls}>{label}</span>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Har AI vazifasi boshlanishida {b.reservation_per_task} {b.currency} rezerv qilinadi, yakunda haqiqiy sarf
        yoziladi. Limitga yetganda yangi pulli ish boshlanmaydi; boshlangan ishlar tugaydi.
      </p>
      <Meter label="Bugun" spent={b.spent_today} limit={b.daily_limit} currency={b.currency} />
      <Meter label="Shu oy" spent={b.spent_month} limit={b.monthly_limit} currency={b.currency} />
      {owner ? (
        <form onSubmit={submit} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="field" style={{ width: 170 }}>
            <span>Kunlik limit ({b.currency})</span>
            <input className="input" inputMode="decimal" placeholder="cheklanmagan"
                   value={daily ?? b.daily_limit ?? ""} onChange={(e) => setDaily(e.target.value)} />
          </label>
          <label className="field" style={{ width: 170 }}>
            <span>Oylik limit ({b.currency})</span>
            <input className="input" inputMode="decimal" placeholder="cheklanmagan"
                   value={monthly ?? b.monthly_limit ?? ""} onChange={(e) => setMonthly(e.target.value)} />
          </label>
          <button className="btn btn-primary" disabled={update.isPending}>Saqlash</button>
        </form>
      ) : (
        <span className="hint">Limitni korxona egasi o‘zgartiradi.</span>
      )}
      <ErrorNotice error={update.error} />
    </section>
  );
}
