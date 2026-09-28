"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Database, MessageSquare, Scale } from "lucide-react";
import Link from "next/link";

import { api, unwrap } from "@/api/client";
import { useMe } from "@/features/auth/api";
import { useSources } from "@/features/integrations/api";

import styles from "./onboarding.module.css";

type Metrics = { settings: { version: number } | null };

/**
 * Ishni boshlash: hisob qoidalari tasdiqlanmaguncha va ma’lumot ulanmaguncha agentlar raqam
 * bermaydi (taxmin qilinmaydi). Qadamlar bajarilgach ro‘yxat o‘zi yo‘qoladi.
 */
export function SetupChecklist() {
  const me = useMe();
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: () => unwrap(api.GET("/api/v1/metrics")) });
  const sources = useSources();
  if (metrics.isLoading || sources.isLoading || !me.data) return null;
  const approved = Boolean((metrics.data as Metrics | undefined)?.settings);
  const hasData = (sources.data ?? []).some((s) => s.status === "synced");
  if (approved && hasData) return null;
  const manager = me.data.role === "owner" || me.data.role === "admin";

  const steps = [
    {
      done: approved, icon: Scale, title: "Hisob qoidalarini tasdiqlang",
      text: "QQS, qaytarish va chegirma qanday hisoblanishini bir marta tasdiqlaysiz — shundan keyin moliyaviy raqamlar chiqadi.",
      action: manager ? <Link className="btn btn-sm btn-primary" href="/settings">Qoidalarni ko‘rish</Link> : null,
    },
    {
      done: hasData, icon: Database, title: "Ma’lumot ulang",
      text: "ERP tizimini ulang yoki CSV fayl yuklang, mapping’ni tasdiqlab sinxronlang.",
      action: manager ? <Link className="btn btn-sm btn-primary" href="/integrations">Ma’lumot ulash</Link> : null,
    },
    {
      done: false, icon: MessageSquare, title: "Agentlarga savol bering",
      text: "Masalan: “Ali, o‘tgan oy filiallar savdosini solishtir” yoki “oylik savdo bo‘yicha dashboard qur”.",
      action: null,
    },
  ];
  return (
    <section className={`panel ${styles.card}`} aria-label="Ishni boshlash">
      <div className={styles.head}>
        <h2>Ishni boshlash</h2>
        <span className="muted">Agentlar faqat tasdiqlangan qoidalar va yuklangan ma’lumotdan hisoblaydi — raqam taxmin qilinmaydi.</span>
      </div>
      {!manager && (
        <div className="notice notice-warning">Bu qadamlarni korxona egasi yoki administrator bajaradi.</div>
      )}
      <ol className={styles.steps}>
        {steps.map((s, i) => (
          <li key={s.title} className={styles.step} data-done={s.done}>
            <span className={styles.mark} aria-hidden>{s.done ? <Check /> : <s.icon />}</span>
            <div className={styles.body}>
              <strong>{i + 1}. {s.title}{s.done && <span className="badge badge-success" style={{ marginLeft: 8 }}>Bajarildi</span>}</strong>
              <span className="muted">{s.text}</span>
            </div>
            {!s.done && s.action}
          </li>
        ))}
      </ol>
    </section>
  );
}
