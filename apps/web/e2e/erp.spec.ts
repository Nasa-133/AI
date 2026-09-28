import { expect, test } from "@playwright/test";

import { ask, registerOwner } from "./helpers";

// Soxta ERP (make stack :8070) orqali: ERP ulash → mapping → sinxron → agent ERP ma’lumotidan javob beradi.
test("ERP ulash (API): mapping, sinxron va chatda javob", async ({ page }) => {
  test.setTimeout(180_000);
  await registerOwner(page, "UI ERP MChJ");
  await page.getByRole("link", { name: "Integratsiyalar" }).click();
  await page.getByRole("button", { name: "ERP ulash (API)" }).click();

  const nav = page.getByRole("navigation", { name: "Manbalar" });
  for (const name of ["ERP: Sotuvlar", "ERP: Qaytarishlar"]) {
    await nav.getByRole("button", { name: new RegExp(name) }).click();
    const detail = page.locator("section", { has: page.getByRole("heading", { name }) });
    await expect(detail.getByText("ERP API")).toBeVisible();
    // Obyekt oldindan tanlangan, ERP holatlari (posted → confirmed) taklif qilingan.
    await expect(detail.locator("p", { hasText: "Manba:" })).toContainText("moslik 100%", { timeout: 30_000 });
    await expect(detail.getByLabel("posted holati")).toHaveValue("confirmed");
    await detail.getByRole("button", { name: "Mapping’ni tasdiqlash" }).click();
    await detail.getByRole("button", { name: "Sinxronlash" }).click({ timeout: 30_000 });
    await expect(detail.getByText("Yuklandi")).toBeVisible({ timeout: 90_000 });
  }

  await page.getByRole("link", { name: "Ofis" }).click();
  await ask(page, "Ali, 2026 sentabr oyidagi savdoni filiallar bo‘yicha ko‘rsat");
  await expect(page.getByText(/Sof savdo tushumi/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Toshkent").first()).toBeVisible();
});
