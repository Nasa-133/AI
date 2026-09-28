"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "@/api/client";

export type Role = "owner" | "admin" | "analyst" | "viewer";
/** branch_scope: null — barcha filiallar (S02). */
export type Member = {
  user_id: string; email: string; role: Role; joined_at: string; branch_scope?: string[] | null;
};
export type Invitation = { id: string; email: string; role: Role; expires_at: string };

export const ROLE_LABEL: Record<Role, string> = {
  owner: "Egasi (Owner)", admin: "Administrator", analyst: "Analitik", viewer: "Kuzatuvchi (Viewer)",
};

/** Owner/Admin bo‘lmaganlar uchun 403 — ro‘yxat o‘rniga `null` (UI shunga moslashadi). */
export function useMembers(enabled = true) {
  return useQuery({
    queryKey: ["members"],
    enabled,
    queryFn: async (): Promise<Member[] | null> => {
      try {
        return (await unwrap(api.GET("/api/v1/members"))) as Member[];
      } catch (e) {
        if (e instanceof ApiError && e.status === 403) return null;
        throw e;
      }
    },
  });
}

export function useInvitations(enabled: boolean) {
  return useQuery({
    queryKey: ["invitations"],
    enabled,
    queryFn: async () => (await unwrap(api.GET("/api/v1/invitations"))) as Invitation[],
  });
}

function useMembersMutation<T>(fn: (input: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["members"] });
      void qc.invalidateQueries({ queryKey: ["invitations"] });
    },
  });
}

export const useInvite = () =>
  useMembersMutation((body: { email: string; role: Role }) => unwrap(api.POST("/api/v1/invitations", { body })));

export const useChangeRole = () =>
  useMembersMutation(({ userId, role }: { userId: string; role: Role }) =>
    unwrap(api.PATCH("/api/v1/members/{user_id}", { params: { path: { user_id: userId } }, body: { role } })));

export const useSetBranchScope = () =>
  useMembersMutation(({ userId, branches }: { userId: string; branches: string[] | null }) =>
    unwrap(api.PUT("/api/v1/members/{user_id}/branches", {
      params: { path: { user_id: userId } }, body: { branch_codes: branches },
    })));

export const useRemoveMember = () =>
  useMembersMutation((userId: string) =>
    unwrap(api.DELETE("/api/v1/members/{user_id}", { params: { path: { user_id: userId } } })));
