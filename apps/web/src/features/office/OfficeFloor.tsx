import { AGENTS } from "@/features/chat/api";

/**
 * Ofis sahnasi. Jonli holatlar (backend eventlariga bog‘langan animatsiya) — Bosqich 4.
 * Hozir soxta “ishlayapti” holati ko‘rsatilmaydi (TZ 6): faqat jamoa tarkibi.
 */
export function OfficeFloor() {
  return (
    <section aria-label="Ofis" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <h2>Ofis</h2>
        <span className="muted">Agentlarning jonli holati Bosqich 4 da ulanadi; hozir vazifa holati chatda ko‘rinadi.</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 150px), 1fr))", gap: 12 }}>
        {Object.entries(AGENTS).map(([key, a]) => (
          <article key={key} className="panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 4 }}>
            <div aria-hidden style={{ fontSize: 28 }}>🧑‍💼</div>
            <strong>{a.name}</strong>
            <span className="muted">{a.title}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
