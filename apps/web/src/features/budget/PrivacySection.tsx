"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { useMe } from "@/features/auth/api";
import { ErrorNotice } from "@/shared/ui/ErrorNotice";

type Privacy = { pseudonymize: boolean; mask_customer_names: boolean };

/** TZ 13.12: AI’ga (OpenAI) ketadigan kontekstdan shaxsiy ma’lumot psevdonimlanadi. */
export function PrivacySection() {
  const me = useMe();
  const qc = useQueryClient();
  const privacy = useQuery({
    queryKey: ["privacy"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/privacy"))) as unknown as Privacy,
  });
  const update = useMutation({
    mutationFn: (body: Privacy) => unwrap(api.PUT("/api/v1/privacy", { body })) as Promise<Privacy>,
    onSuccess: (data) => qc.setQueryData(["privacy"], data),
  });
  const p = privacy.data;
  if (!p) return <ErrorNotice error={privacy.error} />;
  const owner = me.data?.role === "owner";
  const change = (patch: Partial<Privacy>) => update.mutate({ ...p, ...patch });

  return (
    <section className="panel panel-pad" aria-labelledby="privacy-h" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h2 id="privacy-h">Maxfiylik (AI’ga yuboriladigan ma’lumot)</h2>
      <p className="muted" style={{ margin: 0 }}>
        Telefon, email, PINFL, pasport va karta raqamlari AI modeliga yuborilishdan oldin tokenga
        almashtiriladi (masalan, <code className="mono">[TEL-3f9a1c20]</code>). Javobda asl qiymat
        faqat shu tizim ichida tiklanadi. Sozlama o‘zgarishi audit jurnaliga yoziladi.
      </p>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={p.pseudonymize} disabled={!owner || update.isPending}
               onChange={(e) => change({ pseudonymize: e.target.checked })} />
        Shaxsiy ma’lumotlarni psevdonimlash
      </label>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={p.mask_customer_names} disabled={!owner || !p.pseudonymize || update.isPending}
               onChange={(e) => change({ mask_customer_names: e.target.checked })} />
        Mijoz nomlarini ham yashirish (tahlil jadvallarida)
      </label>
      {!p.pseudonymize && (
        <div className="notice notice-warning">
          Psevdonimlash o‘chiq: shaxsiy ma’lumotlar AI provayderiga asl holida yuboriladi.
        </div>
      )}
      {!owner && <span className="hint">Sozlamani korxona egasi o‘zgartiradi.</span>}
      <ErrorNotice error={update.error} />
    </section>
  );
}
