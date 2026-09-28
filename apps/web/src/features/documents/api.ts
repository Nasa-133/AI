"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, readCookie, unwrap, ApiError } from "@/api/client";

export type ParseStatus = "pending" | "parsing" | "ready" | "needs_ocr" | "failed";
export type Version = {
  id: string; version_no: number; kind: string; base_version_id: string | null; filename: string;
  parse_status: ParseStatus; parse_error: string | null; quality: Record<string, unknown>;
  embedding_status: string; comment: string | null; sha256: string; size_bytes: number;
  is_current: boolean; created_at: string | null;
};
export type DocumentItem = {
  id: string; title: string; visibility: "private" | "tenant"; updated_at: string;
  current: Version | null;
};
export type DocumentDetail = {
  id: string; title: string; visibility: "private" | "tenant"; shared_with: string[];
  current_version_id: string | null; can_draft: boolean; can_promote: boolean; versions: Version[];
};
export type Section = { section_id: string; kind: string; locator: string; text: string };
export type Change = {
  section_id: string; locator: string; change: "added" | "removed" | "changed";
  before: string | null; after: string | null;
};
export type Diff = {
  document_id: string; left_version_id: string; right_version_id: string;
  unchanged_count: number; changes: Change[];
};
export type SearchHit = {
  document_id: string; document_title: string; version_id: string; version_no: number;
  chunk_id: string; section_ids: string[]; locator: string; text: string; score: number;
};

const BUSY = new Set<string>(["pending", "parsing"]);
const busy = (v: Version | null | undefined) =>
  Boolean(v && (BUSY.has(v.parse_status) || v.embedding_status === "pending"));

export const docKeys = {
  list: (q: string) => ["documents", q] as const,
  detail: (id: string) => ["document", id] as const,
};

export function useDocuments(query = "") {
  return useQuery({
    queryKey: docKeys.list(query),
    queryFn: async () => (await unwrap(api.GET("/api/v1/documents", {
      params: { query: { q: query || null } },
    }))) as unknown as DocumentItem[],
    refetchInterval: (q) => ((q.state.data ?? []).some((d) => busy(d.current)) ? 1500 : false),
  });
}

export function useDocument(id: string | null) {
  return useQuery({
    queryKey: docKeys.detail(id ?? "none"),
    enabled: Boolean(id),
    queryFn: async () => (await unwrap(api.GET("/api/v1/documents/{document_id}", {
      params: { path: { document_id: id! } },
    }))) as unknown as DocumentDetail,
    refetchInterval: (q) => (q.state.data?.versions.some(busy) ? 1500 : false),
  });
}

export function useSections(documentId: string, versionId: string | null) {
  return useQuery({
    queryKey: ["sections", versionId],
    enabled: Boolean(versionId),
    queryFn: async () => (await unwrap(api.GET(
      "/api/v1/documents/{document_id}/versions/{version_id}/sections",
      { params: { path: { document_id: documentId, version_id: versionId! } } },
    ))) as unknown as Section[],
  });
}

export function useDiff(documentId: string, left: string | null, right: string | null) {
  return useQuery({
    queryKey: ["diff", left, right],
    enabled: Boolean(left && right && left !== right),
    queryFn: async () => (await unwrap(api.GET("/api/v1/documents/{document_id}/diff", {
      params: { path: { document_id: documentId }, query: { left: left!, right: right! } },
    }))) as unknown as Diff,
  });
}

export function downloadUrl(documentId: string, versionId: string): string {
  return `/api/v1/documents/${documentId}/versions/${versionId}/download`;
}

/** Multipart yuklash: openapi-fetch o‘rniga fetch (CSRF qo‘lda). */
async function uploadDocument(file: File): Promise<{ id: string; version_id: string }> {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch("/api/v1/documents", {
    method: "POST", body: form, credentials: "same-origin",
    headers: { "X-CSRF-Token": readCookie("abo_csrf") },
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new ApiError(r.status, body.code ?? `HTTP_${r.status}`, body.message ?? "Yuklab bo‘lmadi.",
                       false, body.trace_id ?? null);
  }
  return body;
}

function useInvalidate() {
  const qc = useQueryClient();
  return (id?: string) => {
    void qc.invalidateQueries({ queryKey: ["documents"] });
    if (id) void qc.invalidateQueries({ queryKey: docKeys.detail(id) });
  };
}

export function useUploadDocument() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: uploadDocument, onSuccess: () => invalidate() });
}

export function usePromote(documentId: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { version_id: string; expected_current_version_id: string }) =>
      unwrap(api.POST("/api/v1/documents/{document_id}/promote", {
        params: { path: { document_id: documentId } }, body,
      })),
    // Konflikt (409) bo‘lsa ham ro‘yxat yangilanadi: foydalanuvchi yangi joriy versiyani ko‘radi.
    onSettled: () => invalidate(documentId),
  });
}

export function useDeleteDocument() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (documentId: string) => unwrap(api.DELETE("/api/v1/documents/{document_id}", {
      params: { path: { document_id: documentId } },
    })),
    onSuccess: () => invalidate(),
  });
}

export function useShare(documentId: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { visibility: "private" | "tenant"; user_ids: string[] }) =>
      unwrap(api.PUT("/api/v1/documents/{document_id}/access", {
        params: { path: { document_id: documentId } }, body,
      })),
    onSuccess: () => invalidate(documentId),
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: async (query: string) => (await unwrap(api.POST("/api/v1/documents/search", {
      body: { query, document_ids: null },
    }))) as unknown as { mode: string; notes: string[]; results: SearchHit[] },
  });
}
