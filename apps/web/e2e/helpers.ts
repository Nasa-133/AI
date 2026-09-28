import { expect, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";
import path from "node:path";

export const GOLDEN = path.resolve(__dirname, "../../../fixtures/synthetic/golden");

export async function registerOwner(page: Page, company: string) {
  await page.goto("/register");
  await page.getByLabel("Korxona nomi").fill(company);
  await page.getByLabel("Email").fill(`ui-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@demo.uz`);
  await page.getByLabel("Parol").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Yaratish" }).click();
  await page.getByRole("button", { name: "Sozlashni boshlash" }).click();
  const secret = (await page.getByRole("main").locator("code").textContent())!.trim();
  await page.getByLabel("6 xonali kod").fill(new OTPAuth.TOTP({ secret }).generate());
  await page.getByRole("button", { name: "Tasdiqlash" }).click();
  await expect(page.getByRole("region", { name: "Dashboardlar doskasi" })).toBeVisible();
  await page.getByRole("link", { name: "Sozlamalar" }).click();
  await page.getByRole("button", { name: "Tasdiqlash" }).click();
  await expect(page.getByText("Tasdiqlangan: 1-versiya")).toBeVisible();
}

export async function importCsv(page: Page, file: string) {
  await page.getByRole("link", { name: "Integratsiyalar" }).click();
  await page.getByLabel("CSV fayl (UTF-8, sarlavhali)").setInputFiles(path.join(GOLDEN, file));
  await page.getByRole("button", { name: "Yuklash" }).click();
  // Aynan shu fayl paneli (oldingi manbaning holati bilan adashtirmaslik uchun).
  const detail = page.locator("section", { has: page.getByRole("heading", { name: file }) });
  await detail.getByRole("button", { name: "Mapping’ni tasdiqlash" }).click({ timeout: 30_000 });
  await detail.getByRole("button", { name: "Sinxronlash" }).click({ timeout: 30_000 });
  await expect(detail.getByText("Yuklandi")).toBeVisible({ timeout: 30_000 });
}

export async function ask(page: Page, text: string) {
  await page.getByLabel("Xabar").fill(text);
  await page.getByRole("button", { name: "Yuborish", exact: true }).click();
}
