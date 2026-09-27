"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Me = components["schemas"]["MeResponse"];

export const meKey = ["me"] as const;

/** `null` — tizimga kirilmagan (401); boshqa xatolar yuqoriga uzatiladi. */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await unwrap(api.GET("/api/v1/me"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string; tenant_name: string }) =>
      unwrap(api.POST("/api/v1/tenants", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/login", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
    onSettled: () => qc.clear(),
  });
}

export function useMfaEnroll() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/auth/mfa/enroll")) });
}

export function useMfaVerify() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => unwrap(api.POST("/api/v1/auth/mfa/verify", { body: { code } })),
    onSuccess: (me) => qc.setQueryData(meKey, me),
  });
}

export function useSwitchTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tenantId: string) =>
      unwrap(api.POST("/api/v1/session/tenant", { body: { tenant_id: tenantId } })),
    onSuccess: () => qc.resetQueries(),
  });
}
