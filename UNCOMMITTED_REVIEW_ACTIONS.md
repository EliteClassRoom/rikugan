# Uncommitted Review Actions

Scope: current uncommitted headless-mode, control-server, provider-override, and documentation changes.

Verification already run:

```bash
python -m pytest tests/headless tests/control tests/ida -q
python -m py_compile rikugan/cli/headless.py rikugan/control/protocol.py rikugan/control/server.py rikugan/headless/runner.py rikugan/ida/dispatch.py rikugan/ida/headless_bootstrap.py rikugan/ida/headless_controller.py rikugan/ida/session_controller.py rikugan/core/host.py rikugan/core/thread_safety.py
python -m ruff check rikugan/cli/headless.py rikugan/control/server.py rikugan/control/protocol.py rikugan/headless/runner.py rikugan/ida/dispatch.py rikugan/ida/headless_bootstrap.py rikugan/ida/headless_controller.py rikugan/core/config.py rikugan/core/host.py rikugan/core/thread_safety.py rikugan/ida/tools/registry.py rikugan/tools/registry.py tests/headless tests/control tests/ida
git diff --check
```

These pass, but the passing tests do not cover the issues below.

## Blockers

1. Fix the headless dispatcher timeout race in `rikugan/ida/dispatch.py`.

   Current behavior at `IdaHeadlessDispatcher.wrap()` lines 144-176 can return `None` as a successful tool result when the main thread has claimed a job but the job runs longer than `_DEFAULT_JOB_TIMEOUT`. The timeout path sees `job.try_claim()` return false, treats that as normal completion, sets the event, and returns `job.result` before the pump has set it.

   Required changes:
   - Track job states separately: queued, running/claimed, completed, cancelled/timed-out.
   - A worker must never return success until the pump has finished the job and set the result or exception.
   - If a job is still queued at timeout, it may be cancelled/skipped and should raise `DispatcherTimeoutError`.
   - If a job is already running at timeout, either continue waiting for completion or raise an explicit timeout without pretending the result is complete. Do not set `job.event` from the worker while the pump is still executing the function.
   - Add a regression test where `_DEFAULT_JOB_TIMEOUT` is short, the pump starts a slow function, and the worker does not receive `None` success.

2. Restrict control-server bind hosts to loopback only.

   `ControlServer.__init__()` rejects `0.0.0.0`, `::`, and empty host at `rikugan/control/server.py:890`, but it still accepts externally reachable addresses such as `192.168.x.x`. `cmd_serve()` has the same gap at `rikugan/cli/headless.py:517`. This violates the headless secure-coding rule that the control server must be local-only.

   Required changes:
   - Accept only loopback hosts: `127.0.0.1`, `localhost`, and optionally `::1` if IPv6 is intentionally supported and tested.
   - Reject every other host in both CLI validation and `ControlServer` construction.
   - Add tests for `192.168.1.10`, `10.0.0.5`, `0.0.0.0`, empty host, accepted loopback values, and the CLI path.

3. Do not silently deny malformed approval requests.

   `_handle_tool_approval()` defaults a missing `decision`/`approved` payload to deny at `rikugan/control/server.py:593-596`. `_handle_approval()` does the same at `rikugan/control/server.py:637-649`. A client typo or empty body can accidentally drive agent state instead of getting a validation error.

   Required changes:
   - Require exactly one canonical decision field for new clients.
   - Keep backward-compatible `approved: true|false` only if the field is explicitly present and is a boolean.
   - Return HTTP 400 for missing decisions, wrong types, unknown strings, or conflicting `decision` and `approved` fields.
   - Add tests that missing decision fields have no side effects and return 400 for both `/tool-approval` and `/approval`.

4. Implement provider-specific missing-key guidance instead of raw `Invalid or missing API key`.

   The docs promise actionable guidance, but OpenAI, Gemini, and MiniMax still raise the default `AuthenticationError` at `rikugan/providers/openai_provider.py:46`, `rikugan/providers/gemini_provider.py:49`, and `rikugan/providers/minimax_provider.py:69`. `SessionControllerBase.start_agent()` then returns only `Provider error: {e}` at `rikugan/ui/session_controller_base.py:454`.

   Required changes:
   - Add provider-specific authentication guidance at the provider or error-formatting layer.
   - Mention accepted environment variables and saved GUI config path where relevant:
     - Anthropic: `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.
     - OpenAI: `OPENAI_API_KEY`.
     - Gemini: `GOOGLE_API_KEY` or `GEMINI_API_KEY`.
     - Ollama: no API key required; optional `OLLAMA_BASE_URL`.
     - MiniMax: either add actual `MINIMAX_API_KEY` support or remove that env-var claim from docs.
     - OpenAI-compatible/custom: saved config/custom provider settings; `--api-base` does not supply a key.
   - Add tests that missing keys produce provider-specific guidance for headless startup errors.

5. Remove accidental repeated implementation-plan blocks from `AGENTS.md`.

   `AGENTS.md` now contains repeated `Headless Provider/API Key Fix Plan` blocks at lines 1267, 1350, 1433, 1516, 1599, 1682, and 1765. This looks like local planning text pasted into the repository guide multiple times.

   Required changes:
   - Remove all repeated `Headless Provider/API Key Fix Plan` blocks from `AGENTS.md`.
   - Keep only durable developer guidance that belongs in `AGENTS.md`.
   - Put implementation handoff material in this file or another explicitly named handoff file, not in the project guide.

## High Priority

6. Correct and align headless API documentation.

   `ARCHITECTURE.md:1166` says `/health` includes database and provider details, but the implementation intentionally returns only `status`, `ready`, and `running`. `ARCHITECTURE.md:1158` shows `/tool-approval {"approved": true}` without `run_id`, but the server requires `run_id` for side-effect endpoints.

   Required changes:
   - Document `/health` as unauthenticated and non-sensitive: no paths, tokens, config, provider names, or database names.
   - Update `/answer`, `/tool-approval`, `/approval`, and `/cancel` examples to include `run_id`.
   - Document the canonical decision payloads after fixing item 3.

7. Remove or implement inert serve flags.

   `serve --timeout` is parsed at `rikugan/cli/headless.py:743` as "not yet enforced" and is never used. Exposed no-op flags are poor CLI API because scripts can depend on behavior that does not exist.

   Required changes:
   - Either remove `serve --timeout`, or implement actual process lifetime supervision.
   - If implemented, ensure it does not conflict with `--ready-timeout` and add tests for timeout behavior.

8. Validate user-supplied server tokens.

   `serve --token` is documented as a `64-char hex` token at `rikugan/cli/headless.py:738`, but any string is accepted and passed through to the server. A weak token is especially risky if host validation regresses.

   Required changes:
   - Enforce a strong token format when provided, preferably 64 hex characters, or change the help text and docs.
   - Add CLI and `ControlServer` tests for accepted and rejected tokens.

9. Remove local/generated artifacts before commit.

   `rikugan_decrypt_analysis_result.json` is untracked local output and should not be committed. Keep `.reasonix/` ignored, but do not add generated result JSON files unless they are intentional fixtures.

   Required changes:
   - Delete `rikugan_decrypt_analysis_result.json` or move it into a deliberate fixture path with a clear test using it.
   - Confirm `git status --short` contains no accidental local output or `__pycache__` files.

## Medium Priority

10. Move or justify the new provider-override tests under `rikugan/tests`.

    `rikugan/tests/test_headless_provider.py` is untracked under the package tree, while CI guidance says tests live under root `tests/`. The manual verification command above also did not run it.

    Required changes:
    - Move it to `tests/headless/test_provider_config.py`, or document why package-level tests are intentional and ensure CI runs them.
    - Avoid duplicating parser tests that are already covered in `tests/headless/test_cli.py`; prefer tests that call real handlers with mocks so bootstrap dict generation is actually verified.

11. Avoid hardcoded provider default drift.

    `rikugan/core/config.py` adds `PROVIDER_DEFAULT_MODELS`, duplicating defaults in provider constructors and model listings. This can drift silently.

    Required changes:
    - Prefer a single source of truth for built-in provider defaults.
    - If avoiding provider imports at config-load time is required, add tests that compare `PROVIDER_DEFAULT_MODELS` to provider constructor defaults or documented built-in model metadata.

12. Stop using `json.dumps(..., default=str)` for structured control API responses.

    `make_json_response()` in `rikugan/control/protocol.py` still stringifies non-serializable objects globally. `/tools` was corrected, but `default=str` can hide future API bugs by returning implementation strings instead of failing tests.

    Required changes:
    - Remove `default=str` from control API JSON serialization.
    - Convert any non-JSON values at endpoint boundaries.
    - Add a test that non-serializable response data fails during development rather than being stringified into the API.

## Suggested Final Verification

Run after implementing the fixes:

```bash
python -m py_compile rikugan/cli/headless.py rikugan/control/protocol.py rikugan/control/server.py rikugan/headless/runner.py rikugan/ida/dispatch.py rikugan/ida/headless_bootstrap.py rikugan/ida/headless_controller.py rikugan/ida/session_controller.py rikugan/core/config.py rikugan/core/host.py rikugan/core/thread_safety.py
python -m pytest tests/headless tests/control tests/ida -q
python -m ruff check rikugan/cli/headless.py rikugan/control/server.py rikugan/control/protocol.py rikugan/headless/runner.py rikugan/ida/dispatch.py rikugan/ida/headless_bootstrap.py rikugan/ida/headless_controller.py rikugan/core/config.py rikugan/core/host.py rikugan/core/thread_safety.py rikugan/ida/tools/registry.py rikugan/tools/registry.py tests/headless tests/control tests/ida
git diff --check
```

If IDA is available, also smoke-test:

```bash
python -m rikugan.cli.headless ask <sample> "summarize metadata" --json --ida <idat>
python -m rikugan.cli.headless serve <sample> --ready-file rikugan-ready.json --ida <idat>
python -m rikugan.cli.headless status --server <url>
python -m rikugan.cli.headless prompt --server <url> --token <token> --prompt "summarize metadata"
python -m rikugan.cli.headless events --server <url> --token <token> --run-id <run_id> --follow
python -m rikugan.cli.headless shutdown --server <url> --token <token>
```
