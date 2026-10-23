import { describe, expect, it } from "vitest";
import { ultrafastToolResult } from "./ultrafast-result.js";

describe("ultrafastToolResult", () => {
  it("preserves structured collected evidence beyond the old 4k tail", () => {
    const evidence = [
      { kind: "extract_text", text: "public ".repeat(1200) },
      { kind: "copy_link", url: "https://example.org/pin/123" },
    ];
    const result = ultrafastToolResult(JSON.stringify({ ok: true, status: "done", evidence }), 0);
    expect(result).toMatchObject({ ok: true, code: 0, evidence });
  });
  it("fails closed on malformed, oversized, or non-object output", () => {
    for (const value of ["not JSON", "[]", "null", "x".repeat(65537)]) {
      expect(ultrafastToolResult(value, 0)).toMatchObject({ ok: false, code: 0 });
    }
  });
  it("preserves partial evidence when runner did not finish", () => {
    expect(
      ultrafastToolResult(
        '{"ok":false,"status":"blocked","evidence":[{"kind":"read_url","url":"https://example.org/"}]}',
        1,
      ),
    ).toMatchObject({ ok: false, code: 1, evidence: [{ kind: "read_url" }] });
  });
});
