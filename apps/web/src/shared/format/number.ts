/** Lokal son formati (TZ 7.1): `1 234 567,50 so‘m`. Qiymatlar API’dan Decimal string keladi. */

function group(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

export function formatDecimal(value: string, fractionDigits = 2): string {
  const negative = value.startsWith("-");
  const [intPart, frac = ""] = value.replace("-", "").split(".");
  const fixed = fractionDigits > 0 ? `,${(frac + "0".repeat(fractionDigits)).slice(0, fractionDigits)}` : "";
  return `${negative ? "−" : ""}${group(intPart)}${fixed}`;
}

export function currencyLabel(currency: string | null | undefined): string {
  if (!currency) return "";
  return currency === "UZS" ? "so‘m" : currency;
}

export function formatValue(value: string | null | undefined, unit: string | null,
                            currency?: string | null): string {
  if (value === null || value === undefined) return "—";
  switch (unit) {
    case "money": return `${formatDecimal(value)} ${currencyLabel(currency)}`.trim();
    case "percent": return `${formatDecimal(value)} %`;
    case "count": return formatDecimal(value.split(".")[0], 0);
    case "quantity": return formatDecimal(value, value.includes(".") ? 2 : 0);
    default: return value;
  }
}
