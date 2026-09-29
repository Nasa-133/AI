import { expect, test } from "@playwright/test";

import { ask, importCsv } from "./helpers";
import * as OTPAuth from "otpauth";

test("ro‘yxatdan o‘tish → CSV → chat javobi → dashboard oynasi", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Korxona nomi").fill("UI E2E MChJ");
  await page.getByLabel("Email").fill(`ui-${Date.now()}@demo.uz`);
  await page.getByLabel("Parol").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Yaratish" }).click();

  await page.getByRole("button", { name: "Sozlashni boshlash" }).click();
  const secret = (await page.locator("code").textContent())!.trim();
  await page.getByLabel("6 xonali kod").fill(new OTPAuth.TOTP({ secret }).generate());
  await page.getByRole("button", { name: "Tasdiqlash" }).click();
  await expect(page.getByRole("region", { name: "Dashboardlar doskasi" })).toBeVisible();

  await page.getByRole("link", { name: "Sozlamalar" }).click();
  await page.getByRole("button", { name: "Tasdiqlash" }).click();
  await expect(page.getByText("Tasdiqlangan: 1-versiya")).toBeVisible();

  await importCsv(page, "sotuvlar.csv");
  await importCsv(page, "qaytarishlar.csv");

  // Chat sahifa almashganda ham saqlanadi (o‘ng panel doimiy).
  await page.getByRole("link", { name: "Ofis" }).click();
  await ask(page, "Ali, 2026 yanvar oyidagi savdoni ko‘rsat");
  await expect(page.getByText(/Sof savdo tushumi — 850,00/)).toBeVisible({ timeout: 30_000 });

  await ask(page, "Ali, 2026 yanvar savdosini dashboard qil");
  const openLink = page.getByRole("link", { name: "Dashboardni ochish" });
  await expect(openLink).toBeVisible({ timeout: 30_000 });
  // Yangi dashboard majburan ochilmaydi (U05): oyna yo‘q, doskada kartochka bor.
  await expect(page.getByRole("region", { name: "Dashboard oynasi" })).toHaveCount(0);
  const card = page.locator("[data-dashboard-card]").first();
  await expect(card).toBeVisible({ timeout: 15_000 });

  // U02: kartochka → ilova ichidagi oyna (yangi tab emas).
  const pagesBefore = page.context().pages().length;
  await card.click();
  const window = page.getByRole("region", { name: "Dashboard oynasi" });
  await expect(window).toBeVisible();
  await expect(window.getByText(/850,00/).first()).toBeVisible();
  expect(page.context().pages().length).toBe(pagesBefore);

  // U03: Escape yopadi, chat va doska joyida, fokus kartochkaga qaytadi.
  await page.keyboard.press("Escape");
  await expect(window).toHaveCount(0);
  await expect(page.getByLabel("Xabar")).toBeVisible();
  await expect(card).toBeFocused();

  // Barchasi → tanlash oynasi → dashboard.
  await page.getByRole("button", { name: /Barchasi \(1\)/ }).click();
  const picker = page.getByRole("region", { name: "Barcha dashboardlar" });
  await expect(picker).toBeVisible();
  await picker.locator("[data-dashboard-card]").first().click();
  await expect(page.getByRole("region", { name: "Dashboard oynasi" })).toBeVisible();
});
