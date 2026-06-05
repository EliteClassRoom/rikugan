# Binary Ninja Removal — Pre-flight Inventory

**Date**: 2026-06-05
**Branch**: refactor/remove-binja-support
**Baseline tag**: pre-binja-removal

## Summary

- **Total BN reference matches**: 494
- **Baseline test count**: 1326 passed, 8 skipped, 4 subtests passed in 3.40s

## Files to delete in Phase 1 (pure BN, no inbound imports from survivors)

### Package: rikugan/binja/ (24 .py files, 4,139 LOC)
- rikugan/binja/__init__.py
- rikugan/binja/bootstrap.py
- rikugan/binja/tools/__init__.py
- rikugan/binja/tools/annotations.py
- rikugan/binja/tools/comment_utils.py
- rikugan/binja/tools/compat.py
- rikugan/binja/tools/database.py
- rikugan/binja/tools/decompiler.py
- rikugan/binja/tools/disasm_utils.py
- rikugan/binja/tools/disassembly.py
- rikugan/binja/tools/fn_utils.py
- rikugan/binja/tools/functions.py
- rikugan/binja/tools/il.py
- rikugan/binja/tools/il_analysis.py
- rikugan/binja/tools/il_transform.py
- rikugan/binja/tools/navigation.py
- rikugan/binja/tools/registry.py
- rikugan/binja/tools/scripting.py
- rikugan/binja/tools/strings.py
- rikugan/binja/tools/sym_utils.py
- rikugan/binja/tools/type_utils.py
- rikugan/binja/tools/types_tools.py
- rikugan/binja/tools/xrefs.py
- rikugan/binja/ui/__init__.py
- rikugan/binja/ui/actions.py
- rikugan/binja/ui/panel.py
- rikugan/binja/ui/session_controller.py

### Root-level files
- rikugan_binaryninja.py (18 LOC)
- install_binaryninja.sh (212 LOC)
- install_binaryninja.bat (207 LOC)
- plugin.json (40 LOC)

### Skill folders
- rikugan/skills/builtins/binja-scripting/SKILL.md (314 LOC)
- rikugan/skills/builtins/binja-scripting/references/api-reference.md (460 LOC)
- rikugan/skills/builtins/smart-patch-binja/SKILL.md (95 LOC)
- rikugan/skills/builtins/deobfuscation/references/binja/algorithm-reference.md (201 LOC)
- rikugan/skills/builtins/deobfuscation/references/binja/guide.md (157 LOC)
- rikugan/skills/builtins/deobfuscation/references/binja/il-guide.md (194 LOC)
- rikugan/skills/builtins/deobfuscation/references/binja/tools.md (58 LOC)

### Test files
- tests/tools/test_binja_actions.py (249 LOC)
- tests/tools/test_binja_common.py (291 LOC)
- tests/tools/test_binja_panel.py (106 LOC)
- tests/tools/test_binja_types_tools.py (109 LOC)
- tests/tools/test_rikugan_binaryninja.py (290 LOC)
- tests/core/test_host_matrix.py (252 LOC)

## Files to delete in Phase 2 (after BN prompt is unwired)
- rikugan/agent/prompts/binja.py (53 LOC)

## Files to delete in Phase 3 (after IDA tools switch imports)
- rikugan/tools/xrefs.py (140 LOC)
- rikugan/tools/functions.py (129 LOC)

## Files to modify

### Phase 2 (core BN detection strip)
- rikugan/core/host.py
- rikugan/agent/system_prompt.py
- rikugan/core/log_sinks.py
- rikugan/state/history.py
- rikugan/skills/loader.py
- rikugan/core/thread_safety.py
- rikugan/ui/session_controller_base.py
- rikugan/ui/panel.py
- rikugan/ui/action_handlers.py
- rikugan/ui/tool_widgets.py

### Phase 3 (dedup)
- rikugan/ida/tools/xrefs.py (import update)
- rikugan/ida/tools/functions.py (import update)
- rikugan/tools/__init__.py (docstring update)

### Phase 4 (skill content)
- rikugan/skills/builtins/deobfuscation/SKILL.md
- (additional files listed below)

### Phase 5 (tests)
- tests/core/test_host.py
- tests/tools/test_panel_core.py
- tests/tools/test_tool_widget_logic.py
- tests/tools/test_context_bar.py
- tests/tools/test_sanitize.py

### Phase 6 (docs + config)
- AGENTS.md
- CLAUDE.md
- ARCHITECTURE.md
- README.md
- DEVELOPMENT.md
- llms.txt
- .github/workflows/ci.yml
- pyproject.toml
- CHANGELOG.md

## Phase 4 (skill content) — additional files

Step 7 grep for `binja|Binary Ninja|BN` in `rikugan/skills/builtins/`, excluding the BN-specific skills already listed in Phase 1, found the following additional files that need Phase 4 cleanup:

- `rikugan/skills/builtins/deobfuscation/SKILL.md` (line 33) — references `Binary Ninja` and links to the four `references/binja/*.md` files
  - Match: `- **Binary Ninja**: references/binja/tools.md (available tools), guide.md (workflow & technique rules), il-guide.md (reading/writing BNIL), algorithm-reference.md (recognition & methodology)`

This is the only remaining match outside the dedicated BN skills. The line is part of a host-tools reference list and should be removed (along with the `**BN**` portion of the `BNIL` mention) when Phase 4 runs.

## Verification commands for end of every phase

```bash
cd D:/re_dev_projects/Rikugan
python -m ruff check rikugan/ tests/
python -m mypy rikugan/core rikugan/providers
python -m pytest tests/ -q
```
