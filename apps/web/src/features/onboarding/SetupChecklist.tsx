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
  // Ixcham: bitta qator qadamlar (tavsif — sichqoncha ostida); ofis ekrandan surilib ketmaydi.
  const next = steps.findIndex((st) => !st.done);
  return (
    <section className={styles.card} aria-label="Ishni boshlash">
      <h2 className={styles.title} title="Agentlar faqat tasdiqlangan qoidalar va yuklangan ma’lumotdan hisoblaydi — raqam taxmin qilinmaydi.">
        Ishni boshlash
      </h2>
      <ol className={styles.steps}>
        {steps.map((s, i) => (
          <li key={s.title} className={styles.step} data-done={s.done} data-next={i === next} title={s.text}>
            <span className={styles.mark} aria-hidden>{s.done ? <Check /> : <s.icon />}</span>
            <span className={styles.body}>
              {i + 1}. {s.title}{s.done && <span className="sr-only"> — bajarildi</span>}
            </span>
            {!s.done && s.action}
          </li>
        ))}
      </ol>
      {!manager && <span className={styles.note}>Bu qadamlarni korxona egasi yoki administrator bajaradi.</span>}
    </section>
  );
}
