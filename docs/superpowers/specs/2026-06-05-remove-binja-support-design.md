# Remove Binary Ninja Support — Rikugan IDA-Only Refactor

**Date**: 2026-06-05
**Status**: Approved (pending user review of written spec)
**Author**: Brainstorming session with user

## Problem Statement

Rikugan currently ships as a **dual-host** plugin supporting both **IDA Pro**
and **Binary Ninja**. The dual-host architecture was added early in the
project's life, but maintaining it has concrete costs:

1. **Code duplication**: The Binary Ninja tool implementations in
   `rikugan/binja/tools/` (~3,500 LOC) mirror the IDA implementations in
   `rikugan/ida/tools/` line-for-line, with host-API calls swapped. Every
   new tool must be implemented twice and tested twice.
2. **Hidden duplication in shared module**: `rikugan/tools/xrefs.py` and
   `rikugan/tools/functions.py` are **near-duplicates** of
   `rikugan/ida/tools/xrefs.py` and `functions.py` (verified via `diff`:
   identical function bodies, only the relative import paths differ —
   `from ..core.logging` vs `from ...core.logging` because the files
   sit in different packages). They only exist because the BN versions
   needed access to the shared formatting helpers (`format_callers_callees`,
   `format_function_summary`); the IDA versions are nominally the
   "owners" of that logic but it was copy-pasted into the shared package
   to share with BN. After BN removal, the duplication is pure waste.
3. **Core abstractions carry dead branches**: `rikugan/core/host.py` has
   full Binary Ninja detection logic (`HOST_BINARY_NINJA`, `is_binary_ninja()`,
   `_bn_bv`, BN metadata storage, BN config dir resolution) that exists
   only to support the second host.
4. **Documented focus drift**: AGENTS.md, CLAUDE.md, and the README all
   describe a "multi-host" plugin, but the project releases, CI, and
   actual day-to-day development are anchored on IDA Pro (per
   `CLAUDE.md` Windows dev notes, which mention only IDA install paths).
5. **User-visible complexity**: The Settings dialog, installer scripts
   (`install_binaryninja.sh/.bat`), and the `rikugan_binaryninja.py`
   entry point exist solely to support BN, and confuse first-time users
   about what Rikugan actually is.

The user has decided to **drop Binary Ninja support entirely** and focus
Rikugan exclusively on IDA Pro.

## Goals

1. **Complete removal of Binary Ninja host package**: Delete
   `rikugan/binja/` (~3,500 LOC), `rikugan_binaryninja.py` entry point,
   `install_binaryninja.sh` and `install_binaryninja.bat` installers,
   `plugin.json` (BN plugin manifest), and all BN-specific skill
   folders (`binja-scripting/`, `smart-patch-binja/`, deobfuscation
   references `binja/`).
2. **Strip BN detection from core abstractions**: Remove all BN branches
   from `rikugan/core/host.py`, `rikugan/agent/system_prompt.py`,
   `rikugan/core/log_sinks.py`, `rikugan/state/history.py`, and
   `rikugan/skills/loader.py`. The codebase must have **no working
   knowledge of Binary Ninja** after this refactor.
3. **Deduplicate IDA tool helpers**: Extract the shared formatting
   helpers (`format_callers_callees`, `format_function_summary`) from
   the duplicated `rikugan/tools/xrefs.py` and `functions.py` files
   into a new clean module `rikugan/tools/formatting.py`, and delete
   the duplicate files. The IDA tool implementations import from the
   new shared module.
4. **Update all documentation to IDA-only**: Rewrite AGENTS.md, CLAUDE.md,
   ARCHITECTURE.md, README.md, DEVELOPMENT.md, and llms.txt to describe
   a single-host (IDA Pro) plugin. Remove all dual-host diagrams, "How
   to Add a New Host" sections, and BN-specific install instructions.
5. **Update tests to match the new architecture**: Delete all BN tests
   (~6 files) and the host matrix test. Update remaining tests that
   referenced BN host setup, fixtures, or constants.
6. **Preserve CI green throughout**: Every phase must leave the
   codebase in a state where `ruff check`, `mypy rikugan/core rikugan/providers`,
   and `pytest tests/` all pass.

## Non-Goals

- **No migration tool for existing BN users**: Users who installed
  Rikugan for Binary Ninja can keep using the last version that
  supported it. We are not building an upgrade path; we are simply
  dropping forward support.
- **No new features for IDA**: This refactor does not add any tools,
  fix any bugs, or change IDA Pro behavior. It is purely a removal.
- **No code-style or quality improvements unrelated to the removal**:
  We will not refactor for style while we're here, except where
  removal makes style cleanup natural (e.g., updating a docstring
  that referenced BN).
- **No restore path**: Once removed, BN code is gone from `main`. We
  do not preserve a `binja-legacy` branch.
- **No rebranding**: The project name, version, and IDA-plugin metadata
  stay the same.

## Section 1: Architecture Overview

### Before (dual-host)

```
rikugan/
├── tools/    # Shared framework: base.py, registry.py, cache.py,
│             # script_guard.py, value_format.py, pagination.py
│             # PLUS: xrefs.py, functions.py  ← DUPLICATES of ida/tools/
├── ida/      # IDA Pro host package (tools/ + ui/)
├── binja/    # Binary Ninja host package (tools/ + ui/)  ← DELETE
├── agent/    # Host-agnostic, but has prompts/{ida.py, binja.py}
└── core/     # Host detection: HOST_IDA, HOST_BINARY_NINJA, HOST_STANDALONE
```

### After (IDA-only)

```
rikugan/
├── tools/    # Shared framework (unchanged) + NEW formatting.py
│             # (shared helpers extracted from duplicates)
│             # xrefs.py and functions.py DELETED (dedup cleanup)
├── ida/      # IDA Pro host package — UI only, tools/ inlined per (3) below
├── agent/    # Host-agnostic, only prompts/ida.py + base.py
│             # prompts/binja.py DELETED
└── core/     # Host detection: HOST_IDA, HOST_STANDALONE only
              # All is_binary_ninja() branches removed
```

The two main structural changes from removal:

1. **`rikugan/binja/` is gone.** All its contents are deleted, not
   refactored or moved.
2. **`rikugan/tools/xrefs.py` and `functions.py` are gone** because
   they only existed as duplicates carrying shared helpers. The
   shared helpers move to a new `rikugan/tools/formatting.py`.

The IDA tool implementations in `rikugan/ida/tools/` are **not
moved** — they stay where they are, with imports updated to pull
from `rikugan.tools.formatting`.

## Section 2: Component-Level Changes

### 2.1 Phase 1 Pure Deletions (safe in Phase 1)

These files have no inbound imports from anything that survives
the refactor (other than the BN code being deleted alongside them).
They can be deleted in Phase 1 without coordination.

| Path | Reason | Verified LOC |
|------|--------|--------------|
| `rikugan/binja/` (entire package) | Full BN host package | 4,139 |
| `rikugan_binaryninja.py` | BN plugin entry point | 18 |
| `install_binaryninja.sh` | BN installer | 212 |
| `install_binaryninja.bat` | BN installer | 207 |
| `plugin.json` | BN plugin manifest | 40 |
| `rikugan/skills/builtins/binja-scripting/` (SKILL.md + references/) | BN Python API skill | 774 |
| `rikugan/skills/builtins/smart-patch-binja/` | BN patching workflow | 95 |
| `rikugan/skills/builtins/deobfuscation/references/binja/` (4 files) | BN deobfuscation refs | 610 |
| `tests/tools/test_binja_actions.py` | BN test | 249 |
| `tests/tools/test_binja_common.py` | BN test | 291 |
| `tests/tools/test_binja_panel.py` | BN test | 106 |
| `tests/tools/test_binja_types_tools.py` | BN test | 109 |
| `tests/tools/test_rikugan_binaryninja.py` | BN test | 290 |
| `tests/core/test_host_matrix.py` | Host matrix test | 252 |
| **Total Phase 1** | | **7,392** |

### 2.1b Coordinated Deletions (require import update first)

These files cannot be deleted in Phase 1 because the IDA tools
currently import from them. They are deleted in **Phase 2 or Phase 3**
after the import edges are rewired.

| Path | Deleted in | Reason | Verified LOC |
|------|------------|--------|--------------|
| `rikugan/agent/prompts/binja.py` | Phase 2 | After `system_prompt.py` drops the import | 53 |
| `rikugan/tools/xrefs.py` | Phase 3 | After `ida/tools/xrefs.py` switches to `rikugan.tools.formatting` | 140 |
| `rikugan/tools/functions.py` | Phase 3 | After `ida/tools/functions.py` switches to `rikugan.tools.formatting` | 129 |
| **Total Phase 2+3 deletions** | | | **322** |

### 2.2 Core Abstraction Modifications

#### `rikugan/core/host.py`

Remove:
- `HOST_BINARY_NINJA` constant
- `is_binary_ninja()` function
- `BINARY_NINJA_AVAILABLE` module-level constant
- `set_binary_ninja_context()`, `get_binary_ninja_view()`
- `_bn_bv`, `_bn_address`, `_bn_navigate_cb`, `_ctx_lock` globals
- All `is_binary_ninja()` branches inside `get_current_address()`,
  `set_current_address()`, `navigate_to()`, `get_user_config_base_dir()`,
  `get_database_path()`, `get_database_instance_id()`,
  `set_database_instance_id()`

Keep (and update `host_display_name()` to drop BN):
- `HOST_IDA`, `HOST_STANDALONE`
- `is_ida()`, `IDA_AVAILABLE`, `HAS_HEXRAYS`
- `host_kind()` — returns "ida" or "standalone"
- `host_display_name()` — returns "IDA Pro" or "Standalone Python"

#### `rikugan/agent/system_prompt.py`

Remove:
- `from .prompts.binja import BINJA_BASE_PROMPT`
- `"Binary Ninja": BINJA_BASE_PROMPT` entry from `_HOST_PROMPTS`

Keep:
- Default `host_name="IDA Pro"` parameter
- `_HOST_PROMPTS = {"IDA Pro": IDA_BASE_PROMPT}` (single entry, fallback to IDA)

#### `rikugan/core/log_sinks.py`

Remove any `~/.binaryninja/rikugan/` log path branches; only `~/.idapro/rikugan/` remains.

#### `rikugan/state/history.py`

Remove `.bndb` path handling; only IDB paths are processed.

#### `rikugan/skills/loader.py`

Remove `~/.binaryninja/rikugan/skills/` discovery; only `~/.idapro/rikugan/skills/` is searched.

#### `rikugan/ui/session_controller_base.py`

The `host_name` parameter is kept for future-proofing but is effectively
always `"IDA Pro"`. Remove any docstring or comment mentions of BN.

#### UI files

- `rikugan/ui/panel.py`
- `rikugan/ui/action_handlers.py`
- `rikugan/ui/tool_widgets.py`

Find and remove any user-visible string `"Binary Ninja"` or `"BN"` that
referenced the second host. (Most UI text already mentions only "IDA"
or is host-neutral.)

### 2.3 Deduplication Refactor (cleanup bonus)

The pre-refactor state has `rikugan/tools/xrefs.py` and
`rikugan/tools/functions.py` as **byte-for-byte duplicates** of
`rikugan/ida/tools/xrefs.py` and `functions.py`. The only purpose of
the duplicates was to host the shared formatting helpers
(`format_callers_callees`, `format_function_summary`) so BN tools
could import them.

After BN removal, the duplicates are dead weight. We:

1. Create `rikugan/tools/formatting.py` with the two helpers.
2. Update `rikugan/ida/tools/xrefs.py` to import
   `format_callers_callees` from `rikugan.tools.formatting` (one-line
   import change; the rest of the file is unchanged).
3. Update `rikugan/ida/tools/functions.py` similarly for
   `format_function_summary`.
4. Delete `rikugan/tools/xrefs.py` and `rikugan/tools/functions.py`.
5. Update `rikugan/tools/__init__.py` docstring to no longer say
   "IDA tool implementations live in their respective packages" or
   "rikugan.binja.tools (Binary Ninja)" — replace with a description
   of the new shared framework that includes `formatting.py` and
   notes that IDA tool implementations live in `rikugan.ida.tools/`.

### 2.4 Skill Content Updates (Phase 4)

`rikugan/skills/builtins/deobfuscation/SKILL.md` likely contains
phrases like "for BN use X; for IDA use Y". After Phase 4 these
become simply "use X" (or "use Y" if Y was the IDA branch).

Grep for any other skill in `rikugan/skills/builtins/` that mentions
BN/Binja and update inline.

### 2.5 Test Updates (Phase 5)

- `tests/core/test_host.py`: Remove test cases for
  `is_binary_ninja()`, `BINARY_NINJA_AVAILABLE`, `set_binary_ninja_context()`,
  `get_binary_ninja_view()`. Keep all `is_ida()`, `HAS_HEXRAYS`,
  `host_display_name()` tests.
- `tests/tools/test_panel_core.py`, `tests/tools/test_tool_widget_logic.py`,
  `tests/tools/test_context_bar.py`, `tests/tools/test_sanitize.py`:
  Sweep for any `host_name="Binary Ninja"` parameter or BN constants
  in fixtures. Update to use `"IDA Pro"` (or remove the parameter).
- `tests/core/test_host_matrix.py`: Already deleted in Phase 1.

### 2.6 Documentation Rewrite (Phase 6)

Each of these files is rewritten to describe a single-host (IDA Pro)
plugin. The rewrite removes:

- `AGENTS.md`:
  - "Multi-Host Structure" wording
  - "How to Add a New Host" section (replace with "How to Add New
    Tools" if useful; otherwise drop)
  - `prompts/binja.py` and `binja/` from directory tree
  - BN rows in the Key Files table
  - "Binary Ninja plugin manager tracks this branch directly" in
    Branch Strategy
  - "Binary Ninja's API is thread-safe" in Threading section
- `CLAUDE.md`:
  - `rikugan_binaryninja.py` entry
  - BN install instructions
  - `~/.binaryninja/rikugan/` config path
- `ARCHITECTURE.md`: BN references
- `README.md`: BN screenshots, badges, mentions
- `DEVELOPMENT.md`: BN install/test instructions
- `llms.txt`: BN mentions
- `.github/workflows/ci.yml`: BN test job if present
- `pyproject.toml`:
  - Remove `"rikugan/binja/**" = ["F401", "E741"]` per-file-ignores
    (no longer needed; folder is gone)
  - Remove `"rikugan/tools/functions.py" = ["RUF001"]` per-file-ignores
    (file is gone after Phase 3)

## Section 3: Implementation Order (7 Phases)

Each phase is **one commit** with a clear message. The codebase must
pass `ruff check` + `mypy` + `pytest` after every phase.

### Phase 0 — Research & Inventory

**Goal**: Comprehensive inventory of every BN reference before touching code.

Actions:
- `git checkout -b refactor/remove-binja-support` (from `dev`)
- Grep entire project for: `binja|BN|BinaryNinja|binaryninja|bn_`
- Build inventory table: file → line → context (BN-specific vs shared)
- Capture all `from rikugan.binja...` imports
- Run baseline: `pytest tests/` to confirm current green
- Save inventory to `docs/superpowers/research/binja-removal-inventory.md`
- Tag `pre-binja-removal` on `dev` as a safety net

**Commit**: None (research doc committed separately if useful)

### Phase 1 — Pure Deletions (zero risk)

Delete all files in Section 2.1 that are pure BN-specific and not
imported by anything else.

Verification: `pytest tests/` — IDA tests still pass.

**Commit**: `refactor(binja): remove Binary Ninja package and entry points`

### Phase 2 — Strip BN Detection from Core

Modify the files in Section 2.2 to remove BN branches. No deletions
of files in this phase (except `rikugan/agent/prompts/binja.py`).

Verification:
- `pytest tests/core/ tests/tools/test_host.py tests/tools/test_panel_core.py`
- `grep -r 'binaryninja' rikugan/ --include='*.py'` returns no matches

**Commit**: `refactor(core): strip Binary Ninja host detection and dispatch`

### Phase 3 — Deduplicate `rikugan/tools/` and `rikugan/ida/tools/`

Execute the Section 2.3 refactor.

Verification:
- `python -c "from rikugan.ida.tools.xrefs import xrefs_to, xrefs_from, function_xrefs"`
- `python -c "from rikugan.ida.tools.functions import list_functions, get_function_info, search_functions"`
- `python -c "from rikugan.tools.formatting import format_callers_callees, format_function_summary"`
- `pytest tests/` + `ruff check rikugan/` + `mypy rikugan/core rikugan/providers`

**Commit**: `refactor(tools): extract shared formatting helpers, drop duplicate IDA tools`

### Phase 4 — Skill Content Cleanup

Grep all remaining skills for BN mentions; rewrite or remove.

Verification:
- `grep -ri 'binja\|binary.ninja\|Binary Ninja' rikugan/skills/builtins/` returns no matches

**Commit**: `refactor(skills): strip Binary Ninja references from shared skill content`

### Phase 5 — Test Updates

Update test files in Section 2.5. After this phase, no test references BN.

Verification:
- `pytest tests/ -v` — 100% pass
- `pytest --cov=rikugan --cov-report=term-missing` — coverage ≥ 80%

**Commit**: `test(core): drop Binary Ninja test cases, ensure IDA-only coverage`

### Phase 6 — Documentation Rewrite

Rewrite all docs per Section 2.6.

Verification:
- `grep -ri 'binja\|binary.ninja\|Binary Ninja' --include='*.md' --include='*.yml' --include='*.json' .` returns no matches (with allowed exceptions for any deliberate historical note)

**Commit**: `docs: rewrite documentation for IDA-only support`

### Phase 7 — Final Verification

Run the full local CI script:
- `./ci-local.sh` (Windows: `python -m ruff check`, `python -m mypy ...`, `python -m pytest`)
- `desloppify scan --profile objective` — score must not drop below 89.0 baseline
- Smoke test (manual): verify `rikugan_plugin.py` import chain works, all IDA tool imports succeed

**Commit**: `chore: final cleanup pass for IDA-only support` (only if fixes needed)

### Phase Summary

| Phase | Risk | LOC delta | Commits |
|-------|------|-----------|---------|
| 0: Research | none | 0 | 0 |
| 1: Pure deletes | low | -7,392 | 1 |
| 2: Strip BN core | medium | -350 (incl. `prompts/binja.py` = 53, plus core mods ~300) | 1 |
| 3: Dedup tools | low | -219 (= -269 deleted + ~50 new `formatting.py`) | 1 |
| 4: Skills content | low | -100 (in-place rewrites in remaining skills) | 1 |
| 5: Test updates | low | -200 (removing test code in `tests/core/test_host.py` etc.) | 1 |
| 6: Docs rewrite | none | 0 (rewrite) | 1 |
| 7: Final verify | none | 0 | 0-1 |
| **Total** | | **~-8,260 LOC** | **7-8 commits** |

## Section 4: Data Flow & Integration Points

### Critical Paths to Verify

#### Path A: IDA Entry → UI → SessionController
```
rikugan_plugin.py
  → rikugan.ida.ui.panel.RikuganPlugin
  → rikugan.ida.ui.session_controller.SessionController
  → rikugan.ui.session_controller_base.SessionControllerBase
```
**Verify**: `python -c "from rikugan.ida.ui.session_controller import SessionController"`

#### Path B: Tool Registration (IDA)
```
rikugan.ida.tools.registry.create_default_registry()
  → rikugan.tools.registry.ToolRegistry
  → rikugan.tools.base.tool decorator
  → rikugan.ida.tools.{navigation, functions, strings, ...}
  → rikugan.tools.formatting (NEW, post-Phase 3)
```
**Verify**: 
```python
from rikugan.ida.tools.registry import create_default_registry
r = create_default_registry()
assert len(r.list_tools()) > 0
```

#### Path C: Host Detection
```
rikugan.core.host
  → importlib.import_module("idaapi")  # tries at import time
  → _HOST = HOST_IDA or HOST_STANDALONE
```
**Verify**:
- In IDA: `is_ida() == True`, `host_kind() == "ida"`, `host_display_name() == "IDA Pro"`
- Outside IDA: `is_ida() == False`, `host_kind() == "standalone"`, `host_display_name() == "Standalone Python"`

#### Path D: System Prompt Selection
```
rikugan.agent.system_prompt.build_system_prompt(host_name)
  → _HOST_PROMPTS[host_name]  # only "IDA Pro" remains
  → IDA_BASE_PROMPT
```
**Verify**: `build_system_prompt()` and `build_system_prompt(host_name="IDA Pro")` both return IDA prompt.

#### Path E: Config & Skill Directories
```
rikugan.core.host.get_user_config_base_dir()
  → "ida": _idaapi.get_user_idadir()
  → "standalone": ~/.idapro/
rikugan.skills.loader  → reads from ~/.idapro/rikugan/skills/
```

### Cross-Cutting Concerns

- **Test isolation**: No test may leak state from a previous test
- **Module re-import**: After Phase 3, no code may import from
  `rikugan.tools.xrefs` or `rikugan.tools.functions`
- **Backward compat**: Old config files with `enabled_external_skills`
  containing BN slugs must not crash — silently skip unknown skills
- **External imports**: After Phase 2, no code may import `binaryninja`
  (verified by grep)
- **Type annotations**: MyPy should remain clean; some `Any` types
  in `host.py` may become unnecessary (cleanup if obvious)

## Section 5: Error Handling, Testing, and Risks

### Error Handling

| Expected failure | Detection | Recovery |
|------------------|-----------|----------|
| Import chain leftover | Phase 1 `pytest` ImportError | Grep + fix inline |
| MyPy on modified core | Phase 2 mypy | Fix types inline |
| Test fixtures with BN setup | Phase 5 | Update fixtures |
| `py_compile` failure on edited file | Per phase | Fix syntax error |
| Hidden `binaryninja` import in "host-agnostic" file | Phase 2 grep | Manual removal |
| Docs cross-reference broken | Phase 6 manual review | Update links |

### Testing Strategy

Every phase must pass:

```bash
python -m ruff check rikugan/ tests/                                  # exit 0
python -m mypy rikugan/core rikugan/providers                          # exit 0
python -m pytest tests/ -v                                            # all pass
python -m py_compile $(git diff --name-only HEAD~1 HEAD -- '*.py')    # exit 0
grep -r 'from rikugan.binja' rikugan/ tests/                          # no match
grep -r 'binaryninja' rikugan/ --include='*.py'                       # no match (after Phase 2)
```

**Coverage target**: ≥ 80%. Removing code tends to increase coverage, not decrease.

**Smoke test after Phase 7** (manual):
```python
from rikugan.core.host import is_ida, host_kind, host_display_name
from rikugan.tools.formatting import format_callers_callees, format_function_summary
from rikugan.ida.tools.xrefs import xrefs_to, xrefs_from, function_xrefs
from rikugan.ida.tools.functions import list_functions, get_function_info
from rikugan.ida.tools.registry import create_default_registry
```

### Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | Build/import chain breakage from missed import | Medium | High | Phase 1 `pytest` catches it immediately |
| R2 | MyPy complaints on type changes | Low | Medium | Phase 2 mypy run; fix inline |
| R3 | Test fixtures with shared BN setup | Low | Medium | Phase 5 fixture-by-fixture analysis |
| R4 | Docs link rot | High | Low | Phase 6 manual review |
| R5 | Shiboken UAF regression | Low | High | Don't change `importlib.import_module()` pattern |
| R6 | CI matrix test breaks | Low | High | Phase 6 verify `.github/workflows/ci.yml` |
| R7 | `desloppify` score drop | Low | Medium | Phase 7 scan + refactor if needed |
| R8 | Hidden coupling in `rikugan.tools` (already found — formatting helpers) | Low | Medium | Phase 0 inventory catches it |
| R9 | User upgrade confusion (BN config leftover) | Low | Low | Doc note in CHANGELOG |
| R10 | External docs/blogs refer to BN support | High | None | Out of scope |

### Safety Nets

1. **Branch protection**: All work on `refactor/remove-binja-support`,
   PR into `dev` (not `main`).
2. **Checkpoint tag**: `git tag pre-binja-removal dev` before Phase 1.
3. **Small revertible commits**: One commit per phase.
4. **No test skipping**: Never use `--no-verify`, never delete a test
   to make it pass. Fix root cause.
5. **No destructive git ops**: No `reset --hard`, no `push --force` on
   shared branches.

## Section 6: Out-of-Scope Items (Explicitly NOT Touched)

- Provider code in `rikugan/providers/` — host-agnostic
- MCP client in `rikugan/mcp/` — host-agnostic
- State persistence in `rikugan/state/` (except `.bndb` removal in
  history.py)
- Most of `rikugan/ui/` (only BN string references removed)
- `rikugan/agent/` core loop (only `prompts/binja.py` deleted)
- `rikugan/ida/ui/` — fully retained as the only UI
- `rikugan/ida/tools/` — fully retained (just import paths updated)
- `rikugan/tools/{base,registry,cache,script_guard,value_format,pagination}.py` —
  fully retained (shared framework)
- IDA-specific skills (`ida-scripting/`, `smart-patch-ida/`,
  `deobfuscation/references/ida/`) — fully retained
- Host-agnostic skills (malware-analysis, linux-malware, vuln-audit,
  driver-analysis, ctf, generic-re, modify) — fully retained

## Section 7: Success Criteria

This refactor is **done** when:

1. `grep -ri 'binja\|binaryninja\|Binary Ninja' rikugan/ tests/ docs/ 2>/dev/null`
   returns no matches (or only deliberate historical notes).
2. `./ci-local.sh` (or Windows equivalent) passes locally.
3. `pytest tests/ --cov=rikugan` reports coverage ≥ 80%.
4. `desloppify scan --profile objective` reports score ≥ 89.0.
5. The branch `refactor/remove-binja-support` contains 7-8 commits,
   each phase passing CI in isolation.
6. AGENTS.md, CLAUDE.md, README.md describe a single-host (IDA Pro)
   plugin with no BN references.
7. The IDA plugin loads and runs in IDA Pro (smoke test on a real IDB).
8. CHANGELOG.md records the removal as a breaking change.
