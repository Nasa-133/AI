"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import styles from "./ui.module.css";

/** Markazdagi natija oynasi (native <dialog>): Esc va fon bosilganda yopiladi, fokus ichida. */
export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog ref={ref} className={styles.dialog} aria-label={title} onClose={onClose}
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.dialogHead}>
        <h2>{title}</h2>
        <button className="btn btn-sm btn-ghost btn-icon" aria-label="Yopish" title="Yopish (Esc)" onClick={onClose}>
          <X aria-hidden />
        </button>
      </div>
      <div className={styles.dialogBody}>{children}</div>
    </dialog>
  );
}
