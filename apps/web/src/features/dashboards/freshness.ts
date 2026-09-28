"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

export type Freshness = {
  state: "fresh" | "pending" | "stale";
  message: string | null;
  waiting: { id: string; name: string; status: string; waiting_seconds: number; stale: boolean }[];
};

/** I03: Integration ishlamasa import “kutilmoqda”, dashboardlar “eskirgan” belgisi bilan. */
export function useFreshness() {
  return useQuery({
    queryKey: ["data-freshness"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/data-freshness"))) as unknown as Freshness,
    refetchInterval: (q) => (q.state.data?.state === "fresh" ? 60_000 : 10_000),
  });
}
