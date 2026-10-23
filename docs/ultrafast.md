# Ultrafast browser

Default page tools (`browser_navigate`, `browser_snapshot`, `browser_act`) stay as they are.

In bot settings, **Ativar ultrafast** replaces those tools with `browser_ultrafast`. That runner attaches to the Chromium already on the computer screen, brings the tab forward, and runs [Jev Ultrafast](https://github.com/browser-use/jev-ultrafast). Text fields use `inception/mercury-3` on OpenRouter. TypeSafe still chooses the operation and the target.

Set these in the bot's Browser settings. They are encrypted and are not returned by the API. Environment variables still work as a fallback:

- `TYPESAFE_API_KEY`
- `TEXT_MODEL_API_KEY`
- `TEXT_MODEL` defaults to `inception/mercury-3`
- `TEXT_MODEL_BASE_URL` defaults to `https://openrouter.ai/api/v1`
- `TEXT_MODEL_REASONING` defaults to `none`

The computer image must include `/usr/local/bin/rakazo-ultrafast`. Rebuild `infra/sandboxes/computer` after this fork. The running published image does not have the runner until that rebuild.

## Typed read capabilities

TypeSafe continues to choose one operation and an observed target (never a generated selector,
JavaScript snippet, shell command, or a replacement browser):

| Operation | Evidence returned |
| --- | --- |
| `READ_URL` | Current visible tab URL |
| `COPY_LINK` | HTTP(S) URL of a currently observed anchor, without opening it |
| `EXTRACT_TEXT` | Rendered page text, up to 12,000 characters; truncation is explicit |
| `INSPECT_NETWORK` | Up to 30 recent request records: URL, method, resource type, status, MIME, completion/failure and encoded size |
| `READ_RESPONSE` | Small public JSON response or an explicit omission reason |

“Copy” means collect the URL into the tool result, **not** change the operating-system clipboard.
Link node identity and href guards are checked immediately before reading. A changed/stale link
must be observed again. Read-only progress does not trigger the three-nonmutating-click guard.
The model sees collected evidence on subsequent choices and is instructed to collect requested
URLs/content/traffic before DONE. Page text and traffic remain untrusted data, not instructions.

The runner returns structured `evidence`, `evidence_dropped`, `status`, and `stop_reason`, including
partial evidence if a later operation/provider fails or a budget is exhausted. The executor preserves
the bounded JSON object rather than cutting off its first URLs/content with a 4,000-character tail.
The evidence ledger keeps at most 20 entries / 48,000 serialized characters, dropping oldest entries
with an explicit counter. The runner additionally bounds the **serialized** UTF-8 result to 60,000 bytes,
shortening text structurally before dropping whole evidence entries (and incrementing the counter).
Complete bounded URLs and sibling records survive excerpt compaction. `output_truncated` marks compaction.
The executor accepts up to 1 MiB of JSON transport, compacts valid large objects to a 60,000-character
model-facing budget, and never prefix/tail-slices parsed evidence.

### Safe failure diagnostics

The runner emits exactly one JSON object, including initialization failures. Third-party stdout/stderr
are suppressed, not returned as evidence. Diagnostics expose only code-owned codes, the failing phase,
exception class where useful, and HTTP status; never raw provider bodies, headers, keys or tracebacks.

- `OUTPUT_EMPTY`, `OUTPUT_INVALID_JSON`, `OUTPUT_NOT_OBJECT`, `OUTPUT_LIMIT` distinguish transport failures.
- `PROVIDER_HTTP` includes `http_status` and `choose` (TypeSafe) or `text` (Mercury) phase.
  HTTP 401/403 names the credential store to configure in `recovery`; 429/5xx requests retry later.
- `PROVIDER_TIMEOUT`, `PROVIDER_CONNECTION`, `PROVIDER_INVALID_JSON`, `PROVIDER_INVALID_CHOICE`
  distinguish provider problems without executing an unvalidated action.
- `BROWSER_CDP_UNAVAILABLE`, `BROWSER_TIMEOUT`, `DEPENDENCY_MISSING` identify startup problems.
  A cold computer uses the existing `rakazo-browser` visible launcher; a live Chrome is reused.
- `model_blocked`, `no_progress_after_three_mutations`, `runner_time_budget`, `runner_step_budget`
  distinguish normal typed-policy stops from `operation_failed` exceptions.

`steps` counts executed actions, **not** model calls. `decisions` and `last_operation` explain zero-action
stops. A bounded sanitized `observation` preserves the last visible page excerpt even when there were
no explicit evidence reads. Successful read evidence is retained on later failures. Provider timeouts
share the runner's deadline so it can return partial results before the sandbox's process timeout.

The default Mercury endpoint is **OpenRouter**, so its field needs an OpenRouter key, not a direct
Inception API key. An authentication rejection cannot be fixed by retrying or bypassing typed actions;
update the saved key in the bot's Browser settings (never in chat/logs). Custom endpoint deployments
must explicitly configure `TEXT_MODEL_BASE_URL` and `TEXT_MODEL` together.

### Network privacy and limits

Capture starts **before** the runner's initial navigation and consumes actual CDP events in that
same visible Chrome session. It cannot recover traffic from before the run. At most 60 records
(and 60 extra-info sensitivity flags) are kept; metadata URLs are bounded to 1,000 characters.
Chrome response buffers are limited to 1 MiB total / 32 KiB per resource. No request headers,
cookies, POST payloads or raw body events are retained or returned.

Bodies are opt-in through `READ_RESPONSE`: only completed GET JSON responses up to 16 KiB,
with at most 6,000 serialized characters after sanitizing. Binary/base64, HTML, non-JSON,
oversized, failed, expired, authenticated/cookie-bearing, login/account/payment and other
sensitive requests are omitted. Extra-info events are checked for credentials/cookies even
when Chrome omits them from the main request event. Authentication, cookie, token, secret,
password, session and financial credential fields are redacted recursively; URL userinfo,
secret query parameters, credential paths and fragments are removed/redacted. This is a
conservative diagnostic reader, not a HAR export, request replayer, or credential extractor.

### Regression checks

Use Python with `browser-harness==0.1.13` and `httpx[http2]==0.28.1` installed:

```sh
python3 -m unittest discover -s infra/sandboxes/computer -p 'test_*.py' -v
pnpm exec vitest run packages/adapters/src/ultrafast-result.test.ts
```

`test_ultrafast_live.py` is opt-in (`RAKAZO_ULTRAFAST_LIVE=1`) inside a running computer.
Place it beside the runner with its `vendor/` directory. It serves a temporary controlled fixture
on that computer's loopback, drives the real visible tab via CDP without calling any model,
checks URL/link/text/network/public JSON reads, sensitive body omission, stale-link rejection,
and terminal evidence. It restores the original tab URL and closes the fixture server.
This proves the browser/executor primitives, not paid TypeSafe/Mercury end-to-end behavior.

### Updating live computers without restarting

Hot-copy the runner to `/usr/local/bin/rakazo-ultrafast` and changed vendor files to
`/usr/local/lib/rakazo-ultrafast/jev_ultrafast/` in **both** the single-bot and team containers;
verify SHA-256 readbacks and run the live regression in each. New runner invocations use the
new files; already-running Python invocations retain their imports. Never restart a computer
with a renderer sidecar sharing its network namespace.

Build the computer image with a **new versioned tag**, leaving the configured computer image
tag untouched during a no-restart rollout. The supervisor compares immutable image IDs and
would otherwise replace a live computer on its next ensure. The versioned image is available
for a later scheduled image adoption. App/executor changes require rebuilding and recreating
only API/worker/web (`--no-deps`), preserving the existing compose `.env`, database, volumes,
supervisor and both computers. No environment or database settings need to change.
