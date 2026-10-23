# Ultrafast browser

Default page tools (`browser_navigate`, `browser_snapshot`, `browser_act`) stay as they are.

In bot settings, **Ativar ultrafast** replaces those tools with `browser_ultrafast`. That runner attaches to the Chromium already on the computer screen, brings the tab forward, and runs [Jev Ultrafast](https://github.com/browser-use/jev-ultrafast). Text fields use `inception/mercury-2.5` on OpenRouter. TypeSafe still chooses the operation and the target.

Set these on the API process. They are forwarded into the computer only for that tool call:

- `TYPESAFE_API_KEY`
- `TEXT_MODEL_API_KEY`
- `TEXT_MODEL` defaults to `inception/mercury-2.5`
- `TEXT_MODEL_BASE_URL` defaults to `https://openrouter.ai/api/v1`
- `TEXT_MODEL_REASONING` defaults to `none`

The computer image must include `/usr/local/bin/rakazo-ultrafast`. Rebuild `infra/sandboxes/computer` after this fork. The running published image does not have the runner until that rebuild.
