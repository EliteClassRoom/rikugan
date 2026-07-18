# Test-Isolation Fix: `_NETNODE_STORE` leak + `core/host.py` cached `_HOST`

**Date**: 2026-07-18
**Status**: Planned (follow-up, not a regression)
**Parent**: Chat History On-Demand (final review APPROVE-WITH-FOLLOWUPS)

## Problem

Two controller tests fail only when run after history test files in the same
pytest session:

```
tests/agent/test_session_controller.py::TestIdaSessionController::test_restore_preserves_token_usage
tests/agent/test_session_controller.py::TestIdaSessionController::test_restore_preserves_tool_calls
```

Each file passes individually. Verified pre-existing at baseline `bf1faa6`
via stash round-trip (10 failed + 7 errors baseline; same shape).

## Root cause (two-layer)

1. **`core/host.py` caches `_HOST` at import time** (`host.py:17,22-54`).
   `_HOST = HOST_STANDALONE` by default; set to `HOST_IDA` only if
   `importlib.import_module("idaapi")` succeeds during `host.py`'s first
   import. Once frozen, `is_ida()` cannot flip back to True even after a
   later test module installs `idaapi` into `sys.modules`.

2. **`tests/mocks/ida_mock.py:40` clears `_NETNODE_STORE` on every
   `install_ida_mocks()` call.** With 50+ test files calling
   `install_ida_mocks()` at module-import time, collection order decides
   whether a controller's `db_instance_id` survives to the next
   controller. When it does not, `ctrl2` generates a fresh ephemeral ID
   that no longer matches the persisted session → `WRONG_IDB`.

The two layers compound: `_HOST` frozen + store cleared = any
save/load round-trip across two controllers (the `test_restore_preserves_*`
shape) is order-dependent.

## Evidence

- `python -m pytest tests/state/test_history_on_demand.py tests/agent/test_session_controller.py`
  → 2 failed, 70 passed (deterministic, 5/5 stress runs).
- `python -m pytest tests/agent/test_session_controller.py` alone
  → 37 passed.
- Instrumented: after `install_ida_mocks()` reinstall,
  `host._idaapi is sys.modules['idaapi']` flips False;
  `set_database_instance_id('X')` returns False (`is_ida()` cached False).

## Fix (planned, not yet implemented)

Two independent, minimal changes — either alone unblocks; both together
remove the order dependency permanently.

### Fix A: `core/host.py` lazy host resolution

Make `is_ida()` and the `_idaapi`-reading helpers resolve the live module
from `sys.modules` instead of the import-time cache. Keep `_HOST` as a
fast-path hint; fall back to `sys.modules.get("idaapi") is not None` when
the cache says standalone. This is a small, additive change that does not
alter production behavior under IDA (where `idaapi` is in `sys.modules`
from the start) but makes test re-install safe.

Risk: low. `is_ida()` is called in hot paths but the fallback is a dict
lookup. Must verify `has_ida_kernwin()` / `is_ida_headless()` /
`IDA_AVAILABLE` still behave — `IDA_AVAILABLE` is module-level and will
stay standalone-friendly; callers that need live truth already call
`is_ida()`.

### Fix B: `tests/mocks/ida_mock.py` stop clearing on reinstall

- Remove `_NETNODE_STORE.clear()` from `install_ida_mocks()`.
- Add `reset_netnode_store()` for tests that genuinely want a clean IDB
  identity (IDB-switch simulation).
- Audit the 50+ call sites: any test that relied on the implicit clear
  must add an explicit `reset_netnode_store()` in `setUp`.

Risk: medium. The implicit clear is load-bearing for IDB-switch tests
(`test_memory_binding`, integration scenario). Audit must be complete.

### Recommended order

Fix B first (test-only, no production risk), then Fix A only if Fix B
leaves residual order-dependence.

## Verification

- `python -m pytest tests/state/test_history_on_demand.py tests/agent/test_session_controller.py`
  green (currently 2 failed).
- `./ci-local.sh` full-suite green (currently ~23 collection-order
  failures, all same root cause).
- Stress: 20× `pytest tests/ tests/integration/` in randomized order
  (`pytest-randomly`) stays green.

## Scope

Test infrastructure only. No feature behavior change. No production
runtime change under Fix B; minimal additive under Fix A.

## Acceptance

1. `./ci-local.sh` passes locally with no collection-order failures.
2. `pytest tests/ tests/integration/` green 20/20 stress runs.
3. No regression in IDA Pro smoke test (manual, after Fix A).
