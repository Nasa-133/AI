"use client";

import { useState } from "react";

import { applyTheme, currentTheme, type Theme } from "./theme";

export function ThemeSelect() {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  return (
    <select className="select select-sm select-auto" aria-label="Mavzu" value={theme}
            suppressHydrationWarning
            onChange={(e) => { const t = e.target.value as Theme; setTheme(t); applyTheme(t); }}>
      <option value="auto">Mavzu: avtomatik</option>
      <option value="light">Yorug‘</option>
      <option value="dark">Qorong‘i</option>
    </select>
  );
}
