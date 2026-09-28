import { expect, test } from "@playwright/test";

import { ask, registerOwner } from "./helpers";

test("ofis: backend holati, klaviatura, agent kartasi, ro‘yxat ko‘rinishi, vazifalar (U01)", async ({ page }) => {
  await registerOwner(page, "Ofis UI MChJ");
  await page.getByRole("link", { name: "Ofis" }).first().click();
  const office = page.getByRole("region", { name: "Ofis" });
  const desks = office.getByRole("group", { name: "Agentlar stollari" });
  await expect(desks.getByRole("button")).toHaveCount(5);
  await expect(desks.getByRole("button", { name: /^Ali, Savdo analitigi: Bo‘sh/ })).toBeVisible();

  // Klaviatura: Tab bilan stollarga kirish, strelkalar, Enter — karta; Escape — fokus qaytadi.
  const ali = desks.getByRole("button", { name: /^Ali,/ });
  await ali.focus();
  await page.keyboard.press("ArrowRight");
  const madina = desks.getByRole("button", { name: /^Madina,/ });
  await expect(madina).toBeFocused();
  await page.keyboard.press("Enter");
  const card = page.getByRole("complementary", { name: "Madina kartasi" });
  await expect(card).toBeVisible();
  await expect(card.getByText("0 / 3")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(card).toHaveCount(0);
  await expect(madina).toBeFocused();

  // Vazifa → agent holati backend’dan: yakuniy holat 30 s ko‘rinadi.
  await ask(page, "Ali, 2026 yanvar oyidagi savdoni ko‘rsat");
  await expect(desks.getByRole("button", { name: /^Ali, Savdo analitigi: (Bajardi|Qisman bajardi|Xato)/ }))
    .toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "test-results/office-desktop.png" });

  // “Chatga yozish”: agent tanlanadi, yozish maydoniga fokus.
  await ali.click();
  await page.getByRole("complementary", { name: "Ali kartasi" }).getByRole("button", { name: "Chatga yozish" }).click();
  await expect(page.getByLabel("Agent", { exact: true })).toHaveValue("sales_analyst");
  await expect(page.getByLabel("Xabar")).toBeFocused();

  // U01: sahnasiz ro‘yxat ko‘rinishi — xuddi shu amallar.
  await office.getByRole("button", { name: "Ro‘yxat" }).click();
  const rows = office.getByRole("table", { name: "Agentlar holati" }).getByRole("row");
  await expect(rows).toHaveCount(6);
  await rows.filter({ hasText: "Dilnoza" }).getByRole("button", { name: "Ochish" }).click();
  await expect(page.getByRole("complementary", { name: "Dilnoza kartasi" })).toBeVisible();
  await page.reload();
  await expect(office.getByRole("table", { name: "Agentlar holati" })).toBeVisible();  // tanlov saqlanadi
  await office.getByRole("button", { name: "Sahna" }).click();

  // Vazifalar sahifasi.
  await page.getByRole("link", { name: "Vazifalar" }).click();
  await expect(page.getByRole("cell", { name: "Ali, 2026 yanvar oyidagi savdoni ko‘rsat" })).toBeVisible();

  // Mobil: gorizontal toshish yo‘q, ofis kartochkalari ishlaydi.
  await page.getByRole("link", { name: "Ofis" }).first().click();
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(desks.getByRole("button", { name: /^Dilnoza,/ })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("aniqlashtirish → “javob kutmoqda”; reduced-motion’da animatsiya yo‘q", async ({ page }) => {
  await registerOwner(page, "Harakat MChJ");
  await page.getByRole("link", { name: "Ofis" }).first().click();
  await ask(page, "Ali, nimadir ko‘rsat");  // metrika noaniq — agent aniqlashtiruvchi savol beradi
  const desks = page.getByRole("group", { name: "Agentlar stollari" });
  await expect(desks.getByRole("button", { name: /^Ali, Savdo analitigi: Javobingizni kutmoqda/ }))
    .toBeVisible({ timeout: 30_000 });

  const animation = () => page.evaluate(() => {
    const mark = document.querySelector('svg[data-state="awaiting_input"] g');
    return mark ? getComputedStyle(mark).animationName : "yo‘q";
  });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  expect(await animation()).not.toBe("none");  // test bo‘sh emas: odatda animatsiya bor
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await animation()).toBe("none");

  // Javob berilgach holat o‘zgaradi (backend: suhbatda yangi vazifa).
  await ask(page, "Ali, 2026 yanvar savdosi");
  await expect(desks.getByRole("button", { name: /^Ali, Savdo analitigi: Javobingizni kutmoqda/ }))
    .toHaveCount(0, { timeout: 30_000 });
});
