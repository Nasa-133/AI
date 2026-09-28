"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

export type Budget = {
  currency: string; daily_limit: string | null; monthly_limit: string | null;
  spent_today: string; spent_month: string; state: "ok" | "warning" | "exceeded";
  percent: number; reservation_per_task: string;
};

export function useBudget() {
  return useQuery({
    queryKey: ["budget"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/budget"))) as unknown as Budget,
    refetchInterval: 60_000,
  });
}

export function useUpdateBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { daily_limit: string | null; monthly_limit: string | null }) =>
      unwrap(api.PUT("/api/v1/budget", { body: body as never })) as Promise<Budget>,
    onSuccess: (data) => qc.setQueryData(["budget"], data),
  });
}
