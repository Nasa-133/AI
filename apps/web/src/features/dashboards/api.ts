"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

import type { DashboardCard, DashboardDetail, QueryResult, QuerySpec } from "./types";

export function useDashboardCards(q: string) {
  return useQuery({
    queryKey: ["dashboards", q],
    // Doskani ko‘rsatish faqat saqlangan preview’ni o‘qiydi — LLM chaqirilmaydi (TZ 8.1, U04).
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards", {
      params: { query: { q: q || undefined, limit: 200 } },
    }))) as unknown as DashboardCard[],
    placeholderData: keepPreviousData,
  });
}

export function useDashboard(id: string | null) {
  return useQuery({
    queryKey: ["dashboard", id],
    enabled: Boolean(id),
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/{dashboard_id}", {
      params: { path: { dashboard_id: id! } },
    }))) as unknown as DashboardDetail,
  });
}

export function useMetricNames(): Record<string, string> {
  const q = useQuery({
    queryKey: ["metrics"],
    queryFn: () => unwrap(api.GET("/api/v1/metrics")),
    staleTime: 10 * 60_000,
  });
  const metrics = ((q.data as { metrics?: { id: string; name: string }[] } | undefined)?.metrics) ?? [];
  return Object.fromEntries(metrics.map((m) => [m.id, m.name]));
}

export function useRunQuery() {
  return useMutation({
    mutationFn: async (spec: QuerySpec) =>
      ((await unwrap(api.POST("/api/v1/analytics/queries", {
        body: spec as never,
      }))) as unknown as { data: QueryResult }).data,
  });
}
