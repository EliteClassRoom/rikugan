# PROJECT_MODIFICATION_PLAN.md — Rikugan

> Plan tổng hợp các thay đổi cần thực hiện cho project Rikugan (current: `D:/re_dev_projects/vibe-clone/rikugan`).
> Đề xuất này dựa trên báo cáo đánh giá so sánh với fork (`D:/re_dev_projects/Rikugan`) chạy ngày 2026-06-12.
> Xem chi tiết workflow đánh giá tại [EVALUATION_WORKFLOW.md](EVALUATION_WORKFLOW.md).

---

## Status Overview

| Phase | Trạng thái | Ghi chú |
|-------|------------|---------|
| **Phase A: Quick Wins** | ✅ Hoàn thành (2026-06-12) | 4/5 fix đã apply, 1 fix không cần (đã đúng) |
| **Phase B: Provider Porting** | ⏳ Pending | Port `codex_provider`, `auth_compat`, `pseudo_tool_schemas` từ fork |
| **Phase C: UI/Code Refactor** | ⏳ Pending | Tách nhỏ 5 file >800 dòng, port theme watcher |
| **Phase D: Security Hardening** | ⏳ Pending | Path traversal, subprocess injection, 6 test isolation bugs |
| **Phase E: Documentation Sync** | ⏳ Pending | AGENTS.md, llms.txt, webpage/* cập nhật |

---

## Phase A: Quick Wins — ✅ DONE

### A.1: Remove 3 binary archives + extend .gitignore

**Status**: ✅ Applied (commit pending)

**Changes**:
- `git rm rikugan/agent.rar` (200KB)
- `git rm rikugan/ida.rar` (124KB)
- `git rm rikugan/ida.7z` (80KB)
- `.gitignore` additions: `.coverage`, `.coverage.*`, `htmlcov/`, `.tox/`, `.nox/`, `.cache/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `*.rar`, `*.7z`

**Verification**: `git status` confirms 3 deletions + .gitignore modifications. Lưu file archives trong `.gitignore` ngăn tái phạm.

### A.2: Remove `rikugan/debug_test.py`

**Status**: ✅ Applied (commit pending)

**Changes**:
- `git rm rikugan/debug_test.py` (26 dòng, dùng `sys.path.insert` + `print`)

**Verification**: `grep -r "debug_test"` confirms no file imports it (only test `test_logging.py:82` uses "debug_test_message" string, unrelated).

### A.3: Document 12 built-in skills in README.md

**Status**: ✅ Applied (commit pending)

**Changes**:
- `README.md` — Thêm bảng 12 skills (ctf, deobfuscation, driver-analysis, generic-re, ida-docs, ida-pro-mcp, ida-scripting, linux-malware, malware-analysis, modify, smart-patch-ida, vuln-audit) với description ngắn.

**Rationale**: Trước đó README chỉ nói "12 built-in skills" mà không list. Người dùng không biết có `/smart-patch-ida` hay `/ida-docs`. Bảng giúp discoverability.

### A.4: ARCHITECTURE.md duplicate "Microcode" row

**Status**: ✅ Verified clean (không cần fix)

**Rationale**: Synthesis ghi nhận duplicate tồn tại ở **fork** (`D:/re_dev_projects/Rikugan/ARCHITECTURE.md:277`). Current đã đúng rồi — chỉ có 1 dòng "Microcode (IDA)" ở line 276.

**Note**: Khi merge upstream về sau, cần double-check duplicate này không lan vào current.

### A.5: Test verification

**Results**:
- ✅ `tests/core/`: 247 passed, 2 skipped
- ✅ `tests/tools/`: tất cả pass
- ✅ `tests/agent/`: 207 passed
- ✅ `tests/providers/`: tất cả pass
- ⚠️ 6 tests fail khi full suite — pre-existing Qt signal/slot test pollution (đã xác nhận fail cả khi stash fixes)

---

## Phase B: Provider Porting — ⏳ PENDING

### B.1: Port `codex_provider.py` từ fork

**Priority**: HIGH (rank 4 trong migration plan)
**Effort**: M
**Risk**: medium

**Source**: `D:/re_dev_projects/Rikugan/rikugan/providers/codex_provider.py`
**Target**: `D:/re_dev_projects/vibe-clone/rikugan/rikugan/providers/codex_provider.py`

**Rationale**: Codex provider (OpenAI Responses API) thiếu trong current. Fork đã có implementation ổn định. Cần cho users muốn dùng Codex backend.

**Steps**:
1. Diff `providers/` giữa 2 projects để identify differences
2. Copy `codex_provider.py` từ fork
3. Copy `providers/__init__.py` registration entry
4. Add to provider registry (priority 4)
5. Add tests: `tests/providers/test_codex_provider.py` (port từ fork)
6. Update `AGENTS.md` provider table
7. Update `README.md` Recommended Providers table
8. Run `pytest tests/providers/` to verify

### B.2: Port `auth_compat.py` từ fork

**Priority**: MEDIUM (rank 6)
**Effort**: S
**Risk**: low

**Source**: `D:/re_dev_projects/Rikugan/rikugan/providers/auth_compat.py`
**Target**: `D:/re_dev_projects/vibe-clone/rikugan/rikugan/providers/auth_compat.py` (new)

**Rationale**: Fork tách auth compatibility logic ra file riêng (61 dòng) — single responsibility. Current inlined vào `auth_cache.py` (112 dòng).

**Steps**:
1. Copy `auth_compat.py` từ fork
2. Refactor `auth_cache.py` để dùng `auth_compat` (giảm xuống ~64 dòng)
3. Verify providers vẫn load đúng
4. Run tests

### B.3: Port `pseudo_tool_schemas.py` từ fork

**Priority**: MEDIUM (rank 5)
**Effort**: M
**Risk**: medium

**Source**: `D:/re_dev_projects/Rikugan/rikugan/agent/pseudo_tool_schemas.py` (likely)
**Target**: Tách từ `rikugan/agent/loop.py:1967` → `pseudo_tool_schemas.py`

**Rationale**: `loop.py` 1967 dòng — quá lớn. Schema definitions nên tách riêng. Fork có refactor này rồi.

**Steps**:
1. Đọc `loop.py` section có schema definitions (search cho `"description":` blocks)
2. Tạo `pseudo_tool_schemas.py` với extracted schemas
3. Update `loop.py` imports
4. Verify agent loop vẫn hoạt động
5. Run `tests/agent/test_agent_loop.py`

### B.4: Refactor `providers/registry.py`

**Priority**: LOW (rank 14)
**Effort**: S
**Risk**: medium

**Current**: 285 dòng
**Target**: <150 dòng

**Rationale**: Fork's `registry.py` chỉ 121 dòng. 164 dòng thừa có thể do inlined provider registration hoặc duplicate code.

**Steps**:
1. Diff registry.py
2. Identify bloat
3. Extract to provider-specific files nếu cần
4. Verify codex_provider (sau B.1) registered đúng
5. Run tests

---

## Phase C: UI/Code Refactor — ⏳ PENDING

### C.1: Port `theme/watcher.py` từ fork

**Priority**: HIGH (rank 10)
**Effort**: M
**Risk**: low

**Source**: `D:/re_dev_projects/Rikugan/rikugan/ui/theme/watcher.py` (likely in fork)
**Target**: `D:/re_dev_projects/vibe-clone/rikugan/rikugan/ui/theme/watcher.py`

**Rationale**: Live theme reload — khi user edit theme file, UI update ngay. Fork có `QFileSystemWatcher`. Current 4-mode theme system nhưng phải restart IDA.

**Steps**:
1. Check if fork has watcher (look in `ui/` or `ui/theme/`)
2. Copy implementation
3. Wire vào `ThemeManager`
4. Test: edit theme file → UI updates

### C.2: Split `rikugan/ui/styles.py` (2758 dòng)

**Priority**: MEDIUM (rank 11)
**Effort**: XL
**Risk**: high

**Current**: `rikugan/ui/styles.py` — 2758 dòng, 1 file
**Target**: <800 dòng/file, organized by theme/component

**Rationale**: 2758 dòng vượt 800-line limit ~3.5x. Khó maintain, test, review. Có thể split theo:
- `styles/tokens.py` (color, typography, spacing tokens)
- `styles/dark.py`, `styles/light.py`, `styles/ida_dark.py`, `styles/ida_light.py` (per-theme)
- `styles/widgets.py` (QSS cho từng widget class)
- `styles/__init__.py` (entry point)

**Steps**:
1. Read full `styles.py` to understand current structure
2. Plan split layout
3. Extract incrementally (run tests after each extraction)
4. Final: keep `styles.py` as thin entry point that imports from `styles/`
5. Run `tests/ui/` + visual regression

### C.3: Split `rikugan/ui/chat_view.py` (2003 dòng)

**Priority**: MEDIUM (rank 13)
**Effort**: L
**Risk**: medium

**Current**: 2003 dòng
**Target**: <800 dòng/file

**Possible split**:
- `chat_view.py` (core)
- `chat_restore_worker.py` (QThread background restore)
- `chat_streaming.py` (streaming handler)
- `chat_message_render.py` (message rendering)

### C.4: Split `rikugan/agent/loop.py` (1967 dòng)

**Priority**: MEDIUM (rank 12, after B.3)
**Effort**: XL
**Risk**: high

**Current**: 1967 dòng (after porting B.3 should drop ~200-400 dòng)
**Target**: <1200 dòng (still need to extract more)

**Possible split**:
- `loop.py` (main turn cycle)
- `tool_execution.py` (extract from `_execute_tool_calls`)
- `state_management.py` (extract state mutations)
- `pseudo_tool_schemas.py` (already in B.3)

### C.5: Split `rikugan/ui/panel_core.py` (2026 dòng)

**Priority**: MEDIUM
**Effort**: XL
**Risk**: high

**Current**: 2026 dòng
**Target**: <800 dòng/file

### C.6: Split `rikugan/ui/settings_dialog.py` (1297 dòng)

**Priority**: LOW
**Effort**: L
**Risk**: medium

**Current**: 1297 dòng
**Target**: <800 dòng/file

---

## Phase D: Security Hardening — ⏳ PENDING

### D.1: Fix path traversal in `research_mode`

**Priority**: CRITICAL (rank 1 trong issues)
**Effort**: S
**Risk**: low

**File**: `rikugan/agent/modes/research.py:170-200, 270-300, 380-470`

**Issue**: `note_path = os.path.join(idb_dir, 'research_notes', genre, f'{slug}.md')`. `genre` comes từ LLM tool call, không có validation. Cho phép LLM ghi file ở bất kỳ đâu IDA process có quyền.

**Fix**:
```python
import os
from pathlib import Path

NOTES_ROOT = Path(idb_dir) / "research_notes"

def _safe_note_path(genre: str, slug: str) -> Path:
    """Validate genre and slug, return safe Path under NOTES_ROOT."""
    # Strip dangerous chars
    safe_genre = "".join(c for c in genre if c.isalnum() or c in "-_")
    safe_slug = "".join(c for c in slug if c.isalnum() or c in "-_")
    if not safe_genre or not safe_slug:
        raise ValueError("Invalid genre/slug")
    path = (NOTES_ROOT / safe_genre / f"{safe_slug}.md").resolve()
    # Containment check
    if not str(path).startswith(str(NOTES_ROOT.resolve())):
        raise ValueError(f"Path traversal blocked: {path}")
    return path
```

**Steps**:
1. Apply fix to all 3 path-construction sites
2. Add test: `tests/agent/test_research_mode.py` — verify path traversal blocked
3. Verify `tests/agent/test_research_mode.py` passes (currently 17 tests pass)

### D.2: Fix subprocess injection in `a2a SubprocessBridge`

**Priority**: HIGH
**Effort**: S
**Risk**: medium

**File**: `rikugan/agent/a2a/subprocess_bridge.py:110-116`

**Issue**: Task từ LLM được nối thẳng vào `['claude', '--print', '--output-format', 'json', task]`. Nếu LLM output `--help` hoặc shell metachar, có thể inject flags.

**Fix**: Whitelist args hoặc escape:
```python
import shlex
# Instead of:
command = ['claude', '--print', '--output-format', 'json', task]
# Use:
command = ['claude', '--print', '--output-format', 'json', '--', task]
# Or validate task doesn't start with '-':
if task.startswith('-'):
    raise ValueError("Invalid task argument")
```

### D.3: Fix 6 pre-existing test isolation bugs

**Priority**: MEDIUM
**Effort**: M
**Risk**: low

**Files**:
- `tests/agent/test_session_controller.py::TestIdaFunctionEnumerationImportFailures` (3 tests)
- `tests/test_light_theme_widgets.py::TestSettingsDialogAppliesThemeOnShow` (2 tests)
- `tests/tools/test_rikugan_plugin.py::TestGuardedImport::test_not_double_wrapped` (1 test)

**Issue**: Qt signal/slot state leaks between tests. ThemeManager.instance() và signal connections persist.

**Fix**:
1. Add teardown hooks to disconnect signals
2. Reset ThemeManager.instance() between tests
3. Use pytest fixtures with proper scope (`function` instead of `module`)

---

## Phase E: Documentation Sync — ⏳ PENDING

### E.1: Update `AGENTS.md` with new providers

**When**: After B.1
**Changes**: Add `codex_provider` row to provider table, mention `auth_compat.py` in shared infrastructure.

### E.2: Update `llms.txt` with new skills/providers

**When**: After A.3 (already done partially), B.1
**Changes**: Skills list + providers list.

### E.3: Update `webpage/` static HTML

**When**: After all code changes
**Changes**: `index.html`, `docs.html`, `ARCHITECTURE.html` — sync with new providers, skills.

### E.4: Sync with upstream `buzzer-re/Rikugan`

**Ongoing**: When upstream releases new version, diff against current. Bằng cách này ta có thể merge upstream improvements mà không bị stuck.

---

## Migration Plan Summary

| # | Action | Priority | Effort | Risk | Phase |
|---|--------|----------|--------|------|-------|
| 1 | Remove 3 binary archives | HIGH | S | low | A ✅ |
| 2 | Remove debug_test.py | HIGH | S | low | A ✅ |
| 3 | Extend .gitignore | HIGH | S | low | A ✅ |
| 4 | Document 12 skills in README | MED | S | low | A ✅ |
| 5 | Fix path traversal in research_mode | CRIT | S | low | D.1 |
| 6 | Fix subprocess injection in a2a | HIGH | S | med | D.2 |
| 7 | Port codex_provider | HIGH | M | med | B.1 |
| 8 | Port auth_compat | MED | S | low | B.2 |
| 9 | Port pseudo_tool_schemas | MED | M | med | B.3 |
| 10 | Refactor providers/registry.py | LOW | S | med | B.4 |
| 11 | Port theme/watcher.py | HIGH | M | low | C.1 |
| 12 | Split styles.py (2758 lines) | MED | XL | high | C.2 |
| 13 | Split chat_view.py (2003 lines) | MED | L | med | C.3 |
| 14 | Split loop.py (1967 lines) | MED | XL | high | C.4 |
| 15 | Split panel_core.py (2026 lines) | MED | XL | high | C.5 |
| 16 | Split settings_dialog.py (1297 lines) | LOW | L | med | C.6 |
| 17 | Fix 6 test isolation bugs | MED | M | low | D.3 |
| 18 | Update AGENTS.md / llms.txt / webpage | LOW | M | low | E |

---

## Execution Order (Recommended)

1. **Week 1**: Security fixes (D.1, D.2) — CRITICAL/HIGH, low effort
2. **Week 1-2**: Provider porting (B.1, B.2, B.3) — additive, easy to verify
3. **Week 2-3**: Test isolation fixes (D.3) — improves test reliability
4. **Week 3-4**: Theme watcher (C.1) — feature add, low risk
5. **Week 4+**: File splits (C.2-C.6) — large refactor, schedule carefully
6. **Ongoing**: Doc sync (E)

---

## Success Metrics

- ✅ All 6 pre-existing test failures fixed
- ✅ Test coverage ≥80% (currently unknown — needs measurement)
- ✅ No file >800 dòng (currently 5 files violate)
- ✅ Zero CRITICAL security findings
- ✅ Branch: master up to date with `tuna-main/main` regularly (weekly rebase)

---

## References

- [EVALUATION_WORKFLOW.md](EVALUATION_WORKFLOW.md) — Reusable evaluation workflow
- [AGENTS.md](../AGENTS.md) — Developer guide
- [ARCHITECTURE.md](../ARCHITECTURE.md) — Internal architecture
- [DEVELOPMENT.md](../DEVELOPMENT.md) — Human contributor guide
