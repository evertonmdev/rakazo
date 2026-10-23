/** Keep bounded runner JSON intact: a tail slice destroys URLs and extracted content. */
export function ultrafastToolResult(stdout: string, code: number): Record<string, unknown> {
  if (stdout.length <= 65_536) {
    try {
      const result: unknown = JSON.parse(stdout);
      if (result && typeof result === "object" && !Array.isArray(result)) {
        const output = result as Record<string, unknown>;
        return { ...output, ok: code === 0 && output.ok === true, code };
      }
    } catch {
      // Do not return raw process output: it may contain provider/CDP internals.
    }
  }
  return { ok: false, code, error: "Ultrafast returned invalid or oversized JSON evidence." };
}
