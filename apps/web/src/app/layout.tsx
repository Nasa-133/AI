import type { Metadata } from "next";

import { THEME_BOOT_SCRIPT } from "@/shared/theme/theme";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "AI Business Office",
  description: "ERP va hujjatlar asosida AI analitika",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Inline skript mavzuni birinchi chizishdan oldin qo‘yadi — hydration farqi kutilgan.
    <html lang="uz" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
