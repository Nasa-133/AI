"use client";

import { Paperclip } from "lucide-react";
import { useId } from "react";

import styles from "./ui.module.css";

/**
 * Fayl tanlash: brauzerning (tilga bog‘liq) “Choose File” tugmasi o‘rniga tizim tugmasi.
 * Haqiqiy input yashirin, lekin label orqali klaviatura va testlar (setInputFiles) uchun ochiq.
 */
export function FilePicker({ id, accept, file, onChange, label = "Fayl tanlash" }: {
  id?: string; accept?: string; file: File | null; onChange: (file: File | null) => void; label?: string;
}) {
  const auto = useId();
  const inputId = id ?? auto;
  return (
    <div className={styles.filePicker}>
      <input id={inputId} className={styles.fileInput} type="file" accept={accept}
             onChange={(e) => onChange(e.target.files?.[0] ?? null)} />
      <label htmlFor={inputId} className="btn btn-sm" aria-hidden><Paperclip aria-hidden /> {label}</label>
      <span className={styles.fileName} title={file?.name}>{file ? file.name : "Fayl tanlanmagan"}</span>
    </div>
  );
}
