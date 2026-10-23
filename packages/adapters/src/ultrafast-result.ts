/** Transport cap is separate from the compact model-facing evidence budget. */
export const ULTRAFAST_STDOUT_LIMIT = 1_048_576;
const RESULT_LIMIT = 60_000;

function compact(value: unknown, textLimit: number, arrayLimit: number, depth = 0): unknown {
  if (depth > 12) return "[depth limit]";
  if (typeof value === "string") {
    // Keep complete bounded URLs, even when excerpts need to shrink.
    return value.slice(0, /^https?:\/\//.test(value) ? 4000 : textLimit);
  }
  if (Array.isArray(value))
    return value.slice(0, arrayLimit).map((v) => compact(v, textLimit, arrayLimit, depth + 1));
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value)
        .slice(0, 100)
        .map(([k, v]) => [k.slice(0, 120), compact(v, textLimit, arrayLimit, depth + 1)]),
    );
  return value;
}

/** Never tail-slice JSON or expose unparsed stdout/provider internals. */
export function ultrafastToolResult(stdout: string, code: number): Record<string, unknown> {
  const failure = (errorCode: string, message: string) => ({
    ok: false,
    code,
    error: message,
    diagnostic: { code: errorCode, phase: "output" },
  });
  if (stdout.length > ULTRAFAST_STDOUT_LIMIT)
    return failure(
      "OUTPUT_LIMIT",
      "Ultrafast output exceeded the transport limit; reduce the task scope.",
    );
  if (!stdout.trim())
    return failure(
      "OUTPUT_EMPTY",
      "Ultrafast produced no JSON result; check runner startup or process timeout.",
    );
  let result: unknown;
  try {
    result = JSON.parse(stdout);
  } catch {
    return failure(
      "OUTPUT_INVALID_JSON",
      "Ultrafast produced invalid JSON; check the runner output contract.",
    );
  }
  if (!result || typeof result !== "object" || Array.isArray(result))
    return failure("OUTPUT_NOT_OBJECT", "Ultrafast JSON result must be an object.");
  let output = {
    ...(result as Record<string, unknown>),
    ok: code === 0 && (result as Record<string, unknown>).ok === true,
    code,
  };
  if (JSON.stringify(output).length <= RESULT_LIMIT) return output;
  const original = output;
  // Shrink text before reducing record counts, preserving sibling URLs and excerpts.
  for (const [text, records] of [
    [6000, 60],
    [3000, 60],
    [1000, 60],
    [500, 30],
    [250, 20],
    [120, 10],
    [80, 3],
  ]) {
    output = {
      ...(compact(original, text!, records!) as typeof output),
      output_truncated: true,
    } as typeof output;
    if (JSON.stringify(output).length <= RESULT_LIMIT) return output;
  }
  return failure(
    "OUTPUT_LIMIT",
    "Ultrafast evidence could not fit the structured result budget; reduce the task scope.",
  );
}
