import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { ask, importCsv, registerOwner } from "./helpers";

const API_LOG = path.resolve(__dirname, "../../../.dev-logs/api.log");

/** Lokal stekda (notifier=log) havola API logiga yoziladi — shu yerdan token olinadi. */
async function linkFromLog(email: string, route: "invite" | "reset-password"): Promise<string> {
  for (let i = 0; i < 40; i++) {
    const lines = fs.readFileSync(API_LOG, "utf8").split("\n").filter((l) => l.includes(email));
    const match = lines.reverse().map((l) => new RegExp(`/${route}\\?token=([\\w-]+)`).exec(l)).find(Boolean);
    if (match) return `/${route}?token=${match[1]}`;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`${email} uchun havola logda topilmadi`);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "Chiqish" }).click();
  await expect(page).toHaveURL(/\/login/);
}

test("a’zo taklifi → qabul → rol cheklovlari; parol tiklash", async ({ page, browser }) => {
  await registerOwner(page, "A’zolar MChJ");
  const email = `analyst-${Date.now()}@demo.uz`;
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Rol").selectOption("analyst");
  await page.getByRole("button", { name: "Taklif yuborish" }).click();
  await expect(page.getByText(`${email} manziliga taklif havolasi yuborildi`)).toBeVisible();
  await expect(page.getByText("Kutilayotgan takliflar")).toBeVisible();

  const invited = await browser.newPage();
  await invited.goto(await linkFromLog(email, "invite"));
  await invited.getByLabel("Parol").fill("analyst-password-1");
  await invited.getByRole("button", { name: "Qo‘shilish" }).click();
  // Analitik uchun MFA majburiy emas — to‘g‘ri ofisga.
  await expect(invited.getByRole("region", { name: "Dashboardlar doskasi" })).toBeVisible();
  await invited.getByRole("link", { name: "Sozlamalar" }).click();
  await expect(invited.getByRole("heading", { name: "A’zolar" })).toHaveCount(0);

  // Owner ro‘yxatda ko‘radi va rolini o‘zgartiradi.
  await page.reload();
  await expect(page.getByRole("cell", { name: email })).toBeVisible();
  await page.getByLabel(`${email} roli`).selectOption("viewer");
  await expect(page.getByLabel(`${email} roli`)).toHaveValue("viewer");

  // Parolni tiklash: eski sessiyalar yopiladi, yangi parol bilan kirish.
  await logout(invited);
  await invited.getByRole("link", { name: "Parolni unutdingizmi?" }).click();
  await expect(invited.getByRole("heading", { name: "Parolni tiklash" })).toBeVisible();
  await invited.getByLabel("Email").fill(email);
  await invited.getByRole("button", { name: "Havola yuborish" }).click();
  await expect(invited.getByText(/havola yuborildi/)).toBeVisible();
  await invited.goto(await linkFromLog(email, "reset-password"));
  await invited.getByLabel("Yangi parol").fill("brand-new-password-2");
  await invited.getByRole("button", { name: "Saqlash" }).click();
  await expect(invited.getByRole("heading", { name: "Parol yangilandi" })).toBeVisible();
  await invited.getByRole("link", { name: "Kirish" }).click();
  await expect(invited.getByRole("heading", { name: "Kirish" })).toBeVisible();
  await invited.getByLabel("Email").fill(email);
  await invited.getByLabel("Parol").fill("brand-new-password-2");
  await invited.getByRole("button", { name: "Kirish" }).click();
  await expect(invited.getByRole("region", { name: "Dashboardlar doskasi" })).toBeVisible();
});

test("dashboard: tahrir, versiya, ulashish, yangilash, CSV, mavzu", async ({ page }) => {
  await registerOwner(page, "Dash UI MChJ");
  await importCsv(page, "sotuvlar.csv");
  await page.getByRole("link", { name: "Ofis" }).click();
  await ask(page, "Ali, 2026 yanvardan aprelgacha oylar bo‘yicha savdoni dashboard qil");
  await page.getByRole("link", { name: "Dashboardni ochish" }).click({ timeout: 30_000 });
  const win = page.getByRole("region", { name: "Dashboard oynasi" });

  await win.getByRole("button", { name: "Tahrirlash" }).click();
  await win.getByLabel("Nomi", { exact: true }).fill("Oylik savdo");
  await win.getByLabel("Widget 1 turi").selectOption("bar");
  await win.getByRole("button", { name: "Saqlash (yangi versiya)" }).click();
  await expect(win.getByRole("heading", { name: "Oylik savdo" })).toBeVisible();
  await expect(win.getByRole("button", { name: "v2" })).toBeVisible();

  await win.getByRole("button", { name: "v2" }).click();
  await expect(win.getByRole("region", { name: "Versiyalar" }).getByRole("row")).toHaveCount(3);
  await win.getByRole("button", { name: "Yopish" }).click();

  await win.getByRole("button", { name: "Ulashish" }).click();
  await win.getByLabel(/Faqat men/).check();
  await win.getByRole("button", { name: "Saqlash" }).click();
  await expect(win.getByRole("button", { name: "Ulashish (yopiq)" })).toBeVisible();

  await win.getByRole("button", { name: "Yangilash" }).click();
  await expect(win.getByText(/3-versiya yaratildi/)).toBeVisible();

  const download = page.waitForEvent("download");
  await win.getByRole("link", { name: "CSV" }).first().click();
  const csv = fs.readFileSync(await (await download).path(), "utf8").replace(/^﻿/, "");
  expect(csv.split(/\r?\n/)[0]).toBe("month,net_sales");

  await page.keyboard.press("Escape");
  await page.getByLabel("Mavzu").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("boshqaruv: AI budjeti, maxfiylik va audit jurnali", async ({ page }) => {
  await registerOwner(page, "Boshqaruv MChJ");
  const budget = page.getByRole("region", { name: "AI budjeti" });
  await expect(budget.getByText("Me’yorda")).toBeVisible();
  await budget.getByLabel("Oylik limit (USD)").fill("0");
  await budget.getByRole("button", { name: "Saqlash" }).click();
  await expect(budget.getByText("0.00 / 0.00 USD")).toBeVisible();
  await expect(budget.getByText(/Limit tugagan/)).toBeVisible();

  // Limit 0: yangi AI vazifasi yuborilmaydi, sababi va keyingi qadam chatda ko‘rinadi.
  await ask(page, "Ali, savdo qancha?");
  await expect(page.getByText(/AI budjeti limiti tugagan/).first()).toBeVisible({ timeout: 30_000 });
  await page.reload();
  await expect(page.getByRole("link", { name: /AI budjeti \d+%/ })).toBeVisible();  // sarlavhada

  const privacy = page.getByRole("region", { name: /Maxfiylik/ });
  const toggle = privacy.getByLabel("Shaxsiy ma’lumotlarni psevdonimlash");
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await expect(privacy.getByText(/asl holida yuboriladi/)).toBeVisible();
  await toggle.check();

  const audit = page.getByRole("region", { name: "Audit jurnali" });
  await page.reload();
  for (const action of ["AI budjeti o‘zgartirildi", "Korxona yaratildi", "Hisob qoidalari tasdiqlandi"]) {
    await expect(audit.getByRole("cell", { name: action }).first()).toBeVisible();
  }
});
