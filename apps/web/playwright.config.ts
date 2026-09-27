import { defineConfig } from "@playwright/test";

// Stek oldindan ishga tushgan bo‘lishi kerak: `make stack` (web :3010).
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  use: { baseURL: process.env.WEB_URL ?? "http://localhost:3010", trace: "retain-on-failure" },
  reporter: [["list"]],
});
