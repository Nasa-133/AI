import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Picker } from "./Picker";
import type { DashboardCard } from "./types";

// U04: 50 ta ruxsatli dashboard — qidiruv, saralash, tanlash. Kartochkalar faqat saqlangan
// preview’dan (useDashboardCards → GET /dashboards), LLM chaqiruvi yo‘q.
const CARDS: DashboardCard[] = Array.from({ length: 50 }, (_, i) => ({
  id: `d${i}`, title: `Hisobot ${String(49 - i).padStart(2, "0")}${i === 12 ? " — Buxoro" : ""}`,
  version: 1, updated_at: "2026-09-28T10:00:00Z",
  period: { from: "2026-01-01", to: "2026-04-30" },
  kpi: i % 2 ? { metric_id: "net_sales", value: "1800.00", unit: "money", currency: "UZS" } : null,
  status: "ready",
}));

vi.mock("./api", () => ({
  useDashboardCards: (q: string) => ({
    data: CARDS.filter((c) => c.title.toLowerCase().includes(q.toLowerCase())),
    isLoading: false, error: null,
  }),
  useMetricNames: () => ({ net_sales: "Sof savdo" }),
}));

const cardTitles = () =>
  Array.from(document.querySelectorAll("[data-dashboard-card]")).map(
    (el) => within(el as HTMLElement).getByTitle(/Hisobot/).textContent);

describe("Picker (U04)", () => {
  it("50 ta kartochkani ko‘rsatadi, qidiradi, saralaydi va tanlaydi", async () => {
    const onOpen = vi.fn();
    const onClose = vi.fn();
    render(<Picker onOpen={onOpen} onClose={onClose} />);

    expect(screen.getByRole("heading", { name: "Barcha dashboardlar (50)" })).toBeInTheDocument();
    expect(document.querySelectorAll("[data-dashboard-card]")).toHaveLength(50);
    expect(screen.getAllByText("Sof savdo")).toHaveLength(25);
    expect(screen.getByLabelText("Qidirish")).toHaveFocus();

    await userEvent.selectOptions(screen.getByLabelText("Saralash"), "title");
    const titles = cardTitles();
    expect(titles[0]).toBe("Hisobot 00");
    expect(titles[49]).toBe("Hisobot 49");

    await userEvent.type(screen.getByLabelText("Qidirish"), "buxoro");
    expect(cardTitles()).toEqual(["Hisobot 37 — Buxoro"]);
    await userEvent.click(screen.getByRole("button", { name: /Hisobot 37/ }));
    expect(onOpen).toHaveBeenCalledWith("d12");

    await userEvent.clear(screen.getByLabelText("Qidirish"));
    await userEvent.type(screen.getByLabelText("Qidirish"), "yo‘q narsa");
    expect(screen.getByText("Dashboard topilmadi.")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
