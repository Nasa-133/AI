"use client";

import { useState } from "react";

import { ErrorNotice } from "@/shared/ui/ErrorNotice";

import { useApproveMapping, type DiscoveredEntity, type MappingItem } from "./api";
import { canonicalOptions, statusValues } from "./statusMap";

const TRANSFORMS: MappingItem["transform"][] = ["text", "decimal", "decimal_or_null", "datetime_tz", "date", "status_map", "const"];

/**
 * Manba → canonical mapping (TZ 7.1): taklif ko‘rsatiladi, foydalanuvchi tekshiradi va tasdiqlaydi.
 * Noma’lum ustun taxmin qilinmaydi — bo‘sh qoldiriladi va majburiy maydon belgilanadi.
 */
export function MappingEditor({ sourceId, entity }: { sourceId: string; entity: DiscoveredEntity }) {
  const approve = useApproveMapping(sourceId);
  const [items, setItems] = useState<MappingItem[]>(entity.suggested_mapping);
  const [statuses, setStatuses] = useState(() => statusValues(entity));
  const update = (i: number, patch: Partial<MappingItem>) =>
    setItems(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const missing = items.filter((it) => entity.unmapped_required_fields.includes(it.canonical_field)
                                       && !it.source_column && it.transform !== "const");
  const statusIncomplete = statuses.some((s) => !s.canonical_value);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <p className="muted">
        Manba: <strong>{entity.source_name}</strong> → <span className="mono">{entity.entity}</span>
        {" "}· moslik {Math.round(entity.match_score * 100)}%
      </p>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th>Canonical maydon</th><th>Manba ustuni</th><th>O‘girish</th><th>Doimiy qiymat</th></tr></thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={it.canonical_field}>
                <td className="mono">{it.canonical_field}
                  {entity.unmapped_required_fields.includes(it.canonical_field) && !it.source_column &&
                    <span className="badge badge-danger" style={{ marginLeft: 6 }}>majburiy</span>}
                </td>
                <td>
                  <select className="select" style={{ minWidth: 180 }} value={it.source_column ?? ""}
                          aria-label={`${it.canonical_field} ustuni`}
                          onChange={(e) => update(i, { source_column: e.target.value || null })}>
                    <option value="">— yo‘q —</option>
                    {entity.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </td>
                <td>
                  <select className="select" style={{ minWidth: 150 }} value={it.transform}
                          aria-label={`${it.canonical_field} o‘girish`}
                          onChange={(e) => update(i, { transform: e.target.value as MappingItem["transform"] })}>
                    {TRANSFORMS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td>
                  {it.transform === "const" ? (
                    <input className="input" style={{ minWidth: 100 }} value={it.constant ?? ""} aria-label={`${it.canonical_field} qiymati`}
                           onChange={(e) => update(i, { constant: e.target.value })} />
                  ) : <span className="muted">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {statuses.length > 0 && (
        <div>
          <h3>{entity.entity === "inventory.movement" ? "Harakat turlari" : "Holat qiymatlari"}</h3>
          {entity.entity !== "inventory.movement" && <p className="muted">Faqat “confirmed” holatidagi satrlar hisobga olinadi.</p>}
          {statuses.map((s, i) => (
            <div key={s.source_value} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
              <span style={{ minWidth: 160 }}>{s.source_value}</span>→
              <select className="select" style={{ width: "auto" }} value={s.canonical_value}
                      aria-label={`${s.source_value} holati`}
                      onChange={(e) => setStatuses(statuses.map((x, j) => j === i ? { ...x, canonical_value: e.target.value } : x))}>
                <option value="">— tanlang —</option>
                {canonicalOptions(entity.entity).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
      {missing.length > 0 && (
        <div className="notice notice-warning">Majburiy maydonlar ulanmagan: {missing.map((m) => m.canonical_field).join(", ")}</div>
      )}
      <ErrorNotice error={approve.error} />
      <button className="btn btn-primary" style={{ alignSelf: "flex-start" }}
              disabled={missing.length > 0 || statusIncomplete || approve.isPending}
              onClick={() => approve.mutate({ entity: entity.entity, mapping: items, status_map: statuses })}>
        Mapping’ni tasdiqlash
      </button>
    </div>
  );
}
