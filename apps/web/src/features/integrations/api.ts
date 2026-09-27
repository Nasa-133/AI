"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, readCookie, unwrap, ApiError } from "@/api/client";

export type MappingItem = {
  canonical_field: string; source_column: string | null;
  transform: "text" | "decimal" | "decimal_or_null" | "datetime_tz" | "date" | "status_map" | "const";
  constant: string | null;
};
export type DiscoveredEntity = {
  entity: string; source_name: string; match_score: number; columns: string[];
  sample_rows: (string | null)[][]; suggested_mapping: MappingItem[]; unmapped_required_fields: string[];
};
export type Source = {
  id: string; name: string; connector_id: string; status: string; entity: string | null;
  mapping_version: number | null; error_message: string | null; updated_at: string;
  discovery?: { entities: DiscoveredEntity[] } | null;
};

const BUSY = new Set(["discovering", "configuring", "syncing"]);

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/integrations"))) as unknown as Source[],
    refetchInterval: (q) => ((q.state.data ?? []).some((s) => BUSY.has(s.status)) ? 1500 : false),
  });
}

export function useSource(id: string | null) {
  return useQuery({
    queryKey: ["source", id],
    enabled: Boolean(id),
    queryFn: async () => (await unwrap(api.GET("/api/v1/integrations/{source_id}", {
      params: { path: { source_id: id! } },
    }))) as unknown as Source,
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? 1500 : false),
  });
}

/** Multipart yuklash: openapi-fetch o‘rniga to‘g‘ridan-to‘g‘ri fetch (CSRF qo‘lda). */
async function uploadFile(file: File): Promise<{ id: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("purpose", "dataset_import");
  const r = await fetch("/api/v1/uploads", {
    method: "POST", body: form, credentials: "same-origin",
    headers: { "X-CSRF-Token": readCookie("abo_csrf") },
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, body.code ?? `HTTP_${r.status}`, body.message ?? "Yuklab bo‘lmadi.", false, body.trace_id ?? null);
  return body;
}

export function useCreateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { connector: "file_import" | "demo_erp"; file?: File }) => {
      const upload = input.file ? await uploadFile(input.file) : null;
      return unwrap(api.POST("/api/v1/integrations", {
        body: { connector_id: input.connector, name: input.file?.name ?? "Demo ERP (sintetik)", upload_id: upload?.id ?? null },
      })) as Promise<{ id: string }>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useApproveMapping(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { entity: string; mapping: MappingItem[]; status_map: { source_value: string; canonical_value: string }[] }) =>
      unwrap(api.POST("/api/v1/integrations/{source_id}/mapping", { params: { path: { source_id: id } }, body: body as never })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["source", id] }),
  });
}

export function useSync(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/integrations/{source_id}/sync", { params: { path: { source_id: id } } })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["source", id] }); void qc.invalidateQueries({ queryKey: ["sources"] }); },
  });
}
