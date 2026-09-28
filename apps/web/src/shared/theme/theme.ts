export type Theme = "auto" | "light" | "dark";
export const THEME_KEY = "abo.theme";

/** Birinchi chizishdan oldin ishlaydigan inline skript (o‘zgarmas matn, foydalanuvchi ma’lumotisiz). */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "auto") delete root.dataset.theme;
  else root.dataset.theme = theme;
  try {
    if (theme === "auto") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch { /* saqlanmasa ham joriy sahifada ishlaydi */ }
}

export function currentTheme(): Theme {
  const t = typeof document !== "undefined" ? document.documentElement.dataset.theme : undefined;
  return t === "light" || t === "dark" ? t : "auto";
}
