import type { AgentStateKey } from "./api";
import styles from "./office.module.css";

/** Stol, monitor va personaj (SVG). Holat belgisi faqat backend holatidan; animatsiya CSS’da
 * `prefers-reduced-motion`da o‘chadi. Dekorativ: ma’no matnda beriladi (aria-hidden). */
export function AgentAvatar({ state, color }: { state: AgentStateKey; color: string }) {
  return (
    <svg className={styles.avatar} viewBox="0 0 120 96" aria-hidden focusable="false"
         data-state={state} style={{ ["--agent" as string]: color }}>
      {/* stol */}
      <rect x="8" y="62" width="104" height="8" rx="2" className={styles.desk} />
      <rect x="16" y="70" width="6" height="22" className={styles.desk} />
      <rect x="98" y="70" width="6" height="22" className={styles.desk} />
      {/* personaj */}
      <circle cx="42" cy="26" r="11" className={styles.head} />
      <path d="M24 62 C24 44 60 44 60 62 Z" className={styles.body} />
      {/* monitor */}
      <rect x="66" y="30" width="38" height="26" rx="3" className={styles.monitor} />
      <rect x="82" y="56" width="6" height="6" className={styles.desk} />
      {state === "reading" && <rect x="44" y="50" width="16" height="12" rx="1" className={styles.paper} />}
      {state === "drafting" && <path d="M70 52 l24 -16 l3 3 l-24 16 z" className={styles.pen} />}
      {state === "analyzing" && (
        <polyline points="70,50 78,42 86,46 96,36" className={styles.chart} />
      )}
      {/* holat belgisi (pufakcha) */}
      {state !== "idle" && (
        <g className={styles.badgeMark}>
          <circle cx="60" cy="10" r="9" />
          <text x="60" y="14" textAnchor="middle">
            {{ queued: "…", reading: "≡", analyzing: "∑", drafting: "✎", awaiting_input: "?",
               awaiting_approval: "!", completed: "✓", failed: "×", cancelled: "–" }[state]}
          </text>
        </g>
      )}
    </svg>
  );
}
