import { describe, expect, it } from "vitest";

import type { Version } from "./api";
import { formatBytes, versionStatus } from "./status";

const base: Version = {
  id: "v", version_no: 1, kind: "original", base_version_id: null, filename: "a.docx",
  parse_status: "ready", parse_error: null, quality: {}, embedding_status: "ready", comment: null,
  sha256: "x", size_bytes: 10, is_current: true, created_at: null,
};

describe("versionStatus", () => {
  it("holatlarni tushunarli matnga aylantiradi", () => {
    expect(versionStatus(base).label).toBe("Tayyor");
    expect(versionStatus({ ...base, parse_status: "parsing" }).label).toBe("O‘qilmoqda");
    expect(versionStatus({ ...base, parse_status: "needs_ocr" }).hint).toMatch(/matn topilmadi/);
    expect(versionStatus({ ...base, parse_status: "failed", parse_error: "Parol bilan himoyalangan" }).hint)
      .toBe("Parol bilan himoyalangan");
    expect(versionStatus({ ...base, embedding_status: "failed" }).label).toMatch(/matnli qidiruv/);
  });

  it("hajmni formatlaydi", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3.5 * 1024 * 1024)).toBe("3,5 MB");
  });
});
