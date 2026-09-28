"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

import type {
  DashboardCard, DashboardDetail, DashboardVersion, QueryResult, QuerySpec, WidgetEdit,
} from "./types";

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

function useDashboardMutation<TInput, TOutput>(id: string, fn: (input: TInput) => Promise<TOutput>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard", id] });
      void qc.invalidateQueries({ queryKey: ["dashboards"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-versions", id] });
    },
  });
}

export function useEditDashboard(id: string) {
  return useDashboardMutation(id, (body: { title?: string; widgets?: WidgetEdit[] }) =>
    unwrap(api.PATCH("/api/v1/dashboards/{dashboard_id}", {
      params: { path: { dashboard_id: id } }, body: body as never,
    })));
}

export function useShareDashboard(id: string) {
  return useDashboardMutation(id, (body: { visibility: "private" | "tenant"; user_ids: string[] }) =>
    unwrap(api.PUT("/api/v1/dashboards/{dashboard_id}/access", {
      params: { path: { dashboard_id: id } }, body,
    })));
}

export function useRefreshDashboard(id: string) {
  return useDashboardMutation<void, { version: number; not_refreshed: string[] }>(id, () =>
    unwrap(api.POST("/api/v1/dashboards/{dashboard_id}/refresh", {
      params: { path: { dashboard_id: id } },
    })) as Promise<{ version: number; not_refreshed: string[] }>);
}

export function useDashboardVersions(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["dashboard-versions", id],
    enabled,
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/{dashboard_id}/versions", {
      params: { path: { dashboard_id: id } },
    }))) as unknown as DashboardVersion[],
  });
}

export const exportUrl = (id: string, widgetId: string) =>
  `/api/v1/dashboards/${id}/widgets/${widgetId}/export.csv`;
