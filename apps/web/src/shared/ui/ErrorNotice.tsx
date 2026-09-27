import { describeError } from "@/api/client";

/** Xato: nima bo‘ldi va keyingi qadam (TZ 6). */
export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const { title, action } = describeError(error);
  return (
    <div className="notice notice-danger" role="alert">
      <strong>{title}</strong>
      <span>{action}</span>
    </div>
  );
}
