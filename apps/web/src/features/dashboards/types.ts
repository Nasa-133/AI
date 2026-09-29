export type Unit = "money" | "percent" | "count" | "quantity";
export type Column = { name: string; kind: string; metric_id: string | null; unit: Unit | null };
export type QueryResult = {
  query_spec_id: string;
  dataset_snapshot_ids: string[];
  period?: { from: string; to: string };
  current_period?: { from: string; to: string };
  comparison_period?: { from: string; to: string };
  currency: string | null;
  columns: Column[];
  rows: (string | null)[][];
  notes: string[];
  as_of?: string;
  truncated?: boolean;
};
export type QuerySpec = {
  metric_ids: string[];
  date_range: { from: string; to: string };
  dimensions: string[];
  filters: { branch_codes?: string[] | null; product_codes?: string[] | null; customer_codes?: string[] | null };
  currency: string | null;
  limit?: number | null;
  order_by?: { metric_id: string; direction: "desc" | "asc" } | null;
};
export type Widget = {
  id: string;
  title: string;
  type: "kpi" | "line" | "area" | "bar" | "stacked_bar" | "pie" | "funnel" | "heatmap" | "table" | "text";
  query_spec_id: string | null;
  text: string | null;
  data: QueryResult | null;
  query: QuerySpec | null;
  status: "ready" | "missing" | "restricted";
};
export type DashboardDetail = {
  id: string; title: string; description: string | null; version: number; updated_at: string;
  widgets: Widget[];
  visibility: "private" | "tenant";
  shared_with: string[];
  can_edit: boolean;
};
export type DashboardVersion = { version: number; title: string; created_by: string; created_at: string };
export type WidgetEdit = { id: string; title?: string; type?: Widget["type"] };
export type DashboardCard = {
  id: string; title: string; version: number; updated_at: string;
  period: { from: string; to: string } | null;
  kpi: { metric_id: string; value: string | null; unit: Unit; currency: string | null } | null;
  /** Mini grafik: faqat toza vaqt qatoridan (bo‘lmasa null — bezak chizilmaydi). */
  spark?: { metric_id: string; unit: Unit; points: string[] } | null;
  status: "ready" | "missing" | "restricted" | "empty";
};
