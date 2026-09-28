import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { THEME_BOOT_SCRIPT } from "@/shared/theme/theme";

import "./globals.css";
import { Providers } from "./providers";

// O‘zbek lotin (‘ ʼ), kirill va raqamlar uchun to‘liq qamrov; shrift build paytida lokal saqlanadi.
const inter = Inter({ subsets: ["latin", "latin-ext", "cyrillic"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin", "cyrillic"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "AI Business Office",
  description: "ERP va hujjatlar asosida AI analitika",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Inline skript mavzuni birinchi chizishdan oldin qo‘yadi — hydration farqi kutilgan.
    <html lang="uz" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
