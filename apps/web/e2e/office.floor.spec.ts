import { expect, test, type Page } from "@playwright/test";

import { ask, registerOwner } from "./helpers";

const agent = (page: Page, role: string) => page.locator(`[data-agent="${role}"]`);
const viewBox = async (page: Page) =>
  (await page.getByRole("application", { name: /Ofis xaritasi/ }).getAttribute("viewBox"))!.split(" ").map(Number);
const position = async (page: Page, role: string) => {
  const t = (await agent(page, role).getAttribute("transform")) ?? "";
  const [, x, y] = /translate\(([\d.]+),([\d.]+)\)/.exec(t) ?? [];
  return { x: Number(x), y: Number(y) };
};

async function openOffice(page: Page, company: string) {
  await registerOwner(page, company);
  await page.getByRole("link", { name: "Ofis" }).first().click();
  await expect(page.getByRole("application", { name: /Ofis xaritasi/ })).toBeVisible();
}

test("xarita: vazifa → agent stoliga yuradi va ishlaydi; karta; zoom/surish; holat saqlanadi", async ({ page }) => {
  await openOffice(page, "Xarita MChJ");
  await expect(page.locator("[data-agent]")).toHaveCount(5);
  for (const role of ["coordinator", "sales_analyst", "finance_analyst", "inventory_analyst", "document_assistant"]) {
    await expect(agent(page, role)).toHaveAttribute("data-at", "rest");  // bo‘sh — dam olish zonasida
  }
  const before = await position(page, "finance_analyst");

  await ask(page, "Madina, 2026 yanvar yalpi foydasini ko‘rsat");
  // Holat backend’dan keladi → Madina moliya bo‘limidagi stoliga yuradi (yo‘lda “walking”).
  await expect(agent(page, "finance_analyst")).toHaveAttribute("data-at", "walking", { timeout: 15_000 });
  await expect(agent(page, "finance_analyst")).toHaveAttribute("data-at", "desk", { timeout: 30_000 });
  const desk = await position(page, "finance_analyst");
  expect(desk).not.toEqual(before);
  // Moliya bo‘limi: x 33..51, y 0..15 katak (16 px).
  expect(desk.x).toBeGreaterThan(33 * 16);
  expect(desk.x).toBeLessThan(51 * 16);
  expect(desk.y).toBeLessThan(15 * 16);
  await expect(agent(page, "finance_analyst")).toHaveAttribute("data-state", /completed|failed/);
  await expect(agent(page, "sales_analyst")).toHaveAttribute("data-at", "rest");  // boshqalar joyida

  // Agentni bosish → joriy vazifa va natija.
  await agent(page, "finance_analyst").click();
  const card = page.getByRole("complementary", { name: "Madina kartasi" });
  await expect(card.getByRole("region", { name: "Oxirgi natija" })).toContainText("2026 yanvar yalpi foydasini");
  await page.keyboard.press("Escape");
  await expect(card).toHaveCount(0);

  // Zoom (tugma, klaviatura, g‘ildirak) va surish.
  const fitBox = await viewBox(page);
  await page.getByRole("button", { name: "Yaqinlashtirish" }).click();
  const zoomed = await viewBox(page);
  expect(zoomed[2]).toBeLessThan(fitBox[2]);
  const map = page.getByRole("application", { name: /Ofis xaritasi/ });
  const box = (await map.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 120, box.y + box.height / 2 - 60, { steps: 5 });
  await page.mouse.up();
  const panned = await viewBox(page);
  expect(panned[0]).toBeGreaterThan(zoomed[0]);
  await page.mouse.wheel(0, -300);
  expect((await viewBox(page))[2]).toBeLessThan(panned[2]);
  await map.focus();
  await page.keyboard.press("-");
  await page.keyboard.press("0");
  expect(await viewBox(page)).toEqual(fitBox);
  await page.getByRole("button", { name: "Yaqinlashtirish" }).click();
  const kept = await viewBox(page);

  // Dashboard oynasi ochilib-yopilganda va boshqa sahifadan qaytganda ofis holati saqlanadi.
  await page.getByRole("link", { name: "Dashboardlar" }).first().click();
  await expect(page.getByRole("region", { name: "Barcha dashboardlar" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(agent(page, "finance_analyst")).toHaveAttribute("data-at", "desk");
  expect(await viewBox(page)).toEqual(kept);
  await page.getByRole("link", { name: "Hujjatlar" }).first().click();
  await page.getByRole("link", { name: "Ofis" }).first().click();
  await expect(agent(page, "finance_analyst")).toHaveAttribute("data-at", "desk");
  expect(await viewBox(page)).toEqual(kept);

  // Klaviatura: agentga Tab, Enter — karta, Escape — fokus agentga qaytadi.
  await agent(page, "coordinator").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("complementary", { name: "Bosh yordamchi kartasi" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(agent(page, "coordinator")).toBeFocused();

  // Ro‘yxat ko‘rinishi (U01) — xaritasiz muqobil yo‘l.
  const office = page.getByRole("region", { name: "Ofis" });
  await office.getByRole("button", { name: "Ro‘yxat" }).click();
  await expect(office.getByRole("table", { name: "Agentlar holati" }).getByRole("row")).toHaveCount(6);
  await office.getByRole("button", { name: "Xarita" }).click();

  // Mobil: xarita va boshqaruv sig‘adi.
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(map).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/office-map-mobile.png" });
});

test("bir nechta agent mustaqil ishlaydi; aniqlashtirish → javob kutmoqda", async ({ page }) => {
  await openOffice(page, "Parallel MChJ");
  await ask(page, "Ali, nimadir ko‘rsat");  // noaniq — aniqlashtiruvchi savol
  await ask(page, "Sardor, ombor qoldig‘i qancha?");
  await expect(agent(page, "sales_analyst")).toHaveAttribute("data-state", "awaiting_input", { timeout: 30_000 });
  await expect(agent(page, "sales_analyst")).toHaveAttribute("data-at", "desk", { timeout: 30_000 });
  await expect(agent(page, "inventory_analyst")).toHaveAttribute("data-at", "desk", { timeout: 30_000 });
  const ali = await position(page, "sales_analyst");
  const sardor = await position(page, "inventory_analyst");
  expect(ali.y).toBeLessThan(15 * 16);  // Savdo — yuqori qator
  expect(sardor.y).toBeGreaterThan(21 * 16);  // Ombor — pastki qator
  await expect(agent(page, "sales_analyst")).toContainText("Javobingizni kutmoqda");
  await page.screenshot({ path: "test-results/office-map-desktop.png" });
});

test("reduced-motion: yurish animatsiyasisiz darhol joyiga o‘tadi", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openOffice(page, "Harakatsiz MChJ");
  const seen: string[] = [];
  await page.exposeFunction("recordAt", (v: string) => { seen.push(v); });
  await page.evaluate(() => {
    const el = document.querySelector('[data-agent="finance_analyst"]')!;
    new MutationObserver(() => (window as unknown as { recordAt: (v: string) => void })
      .recordAt(el.getAttribute("data-at") ?? "")).observe(el, { attributes: true, attributeFilter: ["data-at"] });
  });
  await ask(page, "Madina, 2026 yanvar yalpi foydasini ko‘rsat");
  await expect(agent(page, "finance_analyst")).toHaveAttribute("data-at", "desk", { timeout: 30_000 });
  expect(seen).not.toContain("walking");
  const animation = await agent(page, "finance_analyst").locator("[data-hand]").first()
    .evaluate((el) => getComputedStyle(el).animationName);
  expect(animation).toBe("none");
});
