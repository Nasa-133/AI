"use client";

import { CircleHelp } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import styles from "./ui.module.css";

/** Yordam tooltip’i: ko‘rsatma ekranni egallamaydi — “?” ustiga olib borilganda yoki bosilganda. */
export function HelpTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className={styles.help} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className="btn btn-sm btn-ghost btn-icon" aria-label={label} aria-expanded={open}
              aria-describedby={open ? id : undefined} onClick={() => setOpen(!open)}
              onBlur={() => setOpen(false)} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
        <CircleHelp aria-hidden />
      </button>
      {open && <span role="tooltip" id={id} className={styles.helpPop}>{children}</span>}
    </span>
  );
}
