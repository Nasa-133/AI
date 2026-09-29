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

/** Matndagi xom o‘nli sonlar (`1936621058.00`) → o‘qiladigan (`1 936 621 058,00`). Sana, versiya
 * va butun sonlarga (yil) tegmaydi — faqat nuqtali o‘nli qismi borlar. */
export function formatNumbersInText(text: string): string {
  return text.replace(/(^|[^\d.,\w-])(-?)(\d+)\.(\d{1,2})(?![\d.])/g,
    (_, pre: string, sign: string, int: string, frac: string) =>
      `${pre}${sign ? "−" : ""}${group(int)},${frac.padEnd(2, "0")}`);
}
