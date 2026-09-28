import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

/** Business API’ning standart xatosi (TZ 15): {code, message, retryable, trace_id}. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
    readonly traceId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCookie(name: string, source: string = globalThis.document?.cookie ?? ""): string {
  const prefix = `${name}=`;
  const found = source.split("; ").find((part) => part.startsWith(prefix));
  return found ? decodeURIComponent(found.slice(prefix.length)) : "";
}

/** O‘zgartiruvchi so‘rovlarga CSRF token qo‘shiladi (double-submit cookie). */
export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (UNSAFE.has(request.method)) {
      request.headers.set("X-CSRF-Token", readCookie("abo_csrf"));
    }
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });
api.use(csrfMiddleware);

type Result<T> = { data?: T; error?: unknown; response: Response };

/** openapi-fetch natijasini qiymat yoki `ApiError`ga aylantiradi. */
export async function unwrap<T>(promise: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (response.ok) return data as T;
  const body = (error ?? {}) as Partial<Record<"code" | "message" | "trace_id", string>> & {
    retryable?: boolean;
  };
  throw new ApiError(
    response.status,
    body.code ?? `HTTP_${response.status}`,
    body.message ?? "Kutilmagan javob. Keyinroq qayta urinib ko‘ring.",
    Boolean(body.retryable),
    body.trace_id ?? null,
  );
}

/** Foydalanuvchiga ko‘rsatiladigan matn: xato turi va keyingi qadam (TZ 6: “nimadir xato ketdi” emas). */
export function describeError(error: unknown): { title: string; action: string } {
  if (!(error instanceof ApiError)) {
    return { title: "Serverga ulanib bo‘lmadi.", action: "Internetni tekshirib, qayta urinib ko‘ring." };
  }
  const actions: Record<string, string> = {
    UNAUTHENTICATED: "Qayta kiring.",
    MFA_REQUIRED: "Ikki bosqichli tasdiqlashni yakunlang.",
    FORBIDDEN: "Kerakli ruxsatni korxona egasidan so‘rang.",
    RATE_LIMITED: "Bir necha daqiqadan so‘ng qayta urinib ko‘ring.",
    ACCOUNT_LOCKED: "15 daqiqadan so‘ng qayta urinib ko‘ring yoki parolni tiklang.",
    METRIC_SETTINGS_NOT_APPROVED: "Sozlamalar bo‘limida hisob qoidalarini tasdiqlang.",
    NO_DATA: "Integratsiyalar bo‘limida ma’lumot yuklang.",
    UNSUPPORTED_MEDIA_TYPE: "Faylni CSV (UTF-8) formatida saqlab qayta yuklang.",
    DOCUMENT_UNREADABLE: "Faylni DOCX, matnli PDF yoki TXT sifatida qayta saqlab yuklang.",
    PAYLOAD_TOO_LARGE: "Faylni kichikroq qismlarga bo‘lib yuklang.",
    BUDGET_EXCEEDED: "Korxona egasi Sozlamalar → AI budjeti bo‘limida limitni oshirishi mumkin.",
    VERSION_CONFLICT: "Hujjat boshqa foydalanuvchi tomonidan yangilandi — sahifani yangilab, farqni qayta ko‘ring.",
  };
  const ref = error.traceId ? ` (kod: ${error.traceId.slice(0, 8)})` : "";
  return {
    title: error.message + ref,
    action: actions[error.code] ?? (error.retryable ? "Qayta urinib ko‘ring." : "Ma’lumotlarni tekshirib qayta yuboring."),
  };
}
