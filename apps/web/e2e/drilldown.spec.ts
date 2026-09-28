import { expect, test } from "@playwright/test";

import { ask, importCsv, registerOwner } from "./helpers";

test("drill-down: oy → filial → mahsulot, breadcrumb va sessiyada tiklanish (U06, U07)", async ({ page }) => {
  await registerOwner(page, "Drill UI MChJ");
  await importCsv(page, "sotuvlar.csv");
  await importCsv(page, "qaytarishlar.csv");
  await page.getByRole("link", { name: "Ofis" }).click();
  await ask(page, "Ali, 2026 yanvardan aprelgacha oylar bo‘yicha savdoni dashboard qil");
  await page.getByRole("link", { name: "Dashboardni ochish" }).click({ timeout: 30_000 });

  const win = page.getByRole("region", { name: "Dashboard oynasi" });
  // Grafik birinchi; drill-down — grafik ustunini yoki jadval qatorini bosish.
  await win.getByRole("button", { name: "Ma’lumot jadvali" }).first().click();
  await win.getByRole("button", { name: "2026-01 ›" }).click();
  const crumbs = win.getByRole("navigation", { name: "Drill-down yo‘li" });
  await expect(crumbs).toContainText("2026-01 → Filial");
  await expect(win.getByRole("cell", { name: "850,00 so‘m" })).toBeVisible(); // A01: TOS yanvar

  await win.getByRole("button", { name: "TOS ›" }).click();
  await expect(crumbs).toContainText("TOS → Mahsulot");
  await expect(win.getByRole("cell", { name: "470,00 so‘m" })).toBeVisible(); // P001

  // U07: qayta yuklashda sessiyadagi drill-down tiklanadi.
  await page.reload();
  await expect(page.getByRole("navigation", { name: "Drill-down yo‘li" })).toContainText("TOS → Mahsulot");
  await page.getByRole("button", { name: "Filtrlarni tiklash" }).click();
  await expect(page.getByRole("navigation", { name: "Drill-down yo‘li" })).toHaveCount(0);
});
