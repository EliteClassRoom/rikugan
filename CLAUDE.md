# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Nếu bạn là coding agent, hãy đọc [AGENTS.md](AGENTS.md) trước** — file đó là developer guide chi tiết (quy tắc code, thread safety, sanitization, IDA 9.x API changes, cách thêm tools/skills, ...). Tài liệu này là **điểm vào ngắn gọn**: commands, kiến trúc tổng quan, và những cảnh báo không thể bỏ qua.
>
> Tài liệu tham chiếu sâu hơn:
> - [AGENTS.md](AGENTS.md) — quy tắc phát triển, cách thêm tools/skills, IDA API notes
> - [ARCHITECTURE.md](ARCHITECTURE.md) — sơ đồ luồng dữ liệu, TurnEvent system, subagent model
> - [DEVELOPMENT.md](DEVELOPMENT.md) — hướng dẫn cho người đóng góp, branch workflow
> - [CHANGELOG.md](CHANGELOG.md) — release notes theo từng version (khi debug regression)
> - [llms.txt](llms.txt) — bản tóm tắt tối giản phù hợp làm context cho LLM khác

---

## Rikugan là gì?

Rikugan (六眼) là plugin **IDA Pro** nhúng một agent LLM ngay trong disassembler. Nó có **agentic loop riêng** (không phải MCP client), điều phối 60+ tools cho IDA, hỗ trợ subagents chạy song song, skills, MCP client, và **headless mode** (chạy trong `idat.exe` / `idat64` không cần Qt). Hỗ trợ Claude, OpenAI/Codex, Gemini, Ollama, MiniMax, và mọi OpenAI-compatible endpoint.

```
User message → command detection → skill resolution → build system prompt
    → stream LLM response (TurnEvent stream)
    → intercept tool calls → execute tools (main-thread marshalled)
    → feed results back → repeat
```

---

## Commands thường dùng

### Local CI (mirror đúng GitHub Actions — chạy trước khi push)

```bash
./ci-local.sh          # format + lint + mypy + pytest + desloppify score
./ci-local.sh --fix    # auto-fix ruff formatting/lint
```

`ci-local.sh` tự cài `ruff`/`mypy` nếu thiếu. Nếu muốn score desloppify khớp CI, cài `uv` để dùng Python 3.11 (xem `.python-version`).

### Từng bước riêng

```bash
# Format + lint
python3 -m ruff format rikugan/
python3 -m ruff check rikugan/ --fix

# Type check (chỉ core + providers — cấu hình trong pyproject.toml)
python3 -m mypy rikugan/core rikugan/providers

# Tests
python3 -m pytest tests/ -v                                    # toàn bộ
python3 -m pytest tests/agent/test_agent_loop.py -v            # một file
python3 -m pytest tests/agent/test_agent_loop.py::TestFoo -v   # một class
python3 -m pytest tests/agent/test_agent_loop.py -k "cancel"   # theo tên
```

Tests stub IDA API (xem `tests/mocks/ida_mock.py`) — **không cần IDA Pro để chạy test**.

### Code quality (desloppify)

```bash
desloppify scan            # chạy scan
desloppify status          # xem score dashboard
desloppify issues          # work queue
```

Baseline objective score: **89.0/100** (CI fail nếu giảm > 0.5 điểm). Subjective review (`desloppify review`) chạy thủ công trước release, không chạy mỗi PR.

### Headless mode (chạy ngoài IDA)

```bash
export IDA_PATH="/path/to/idat64"   # hoặc idat.exe trên Windows

# One-shot
python -m rikugan.cli.headless ask /path/to/sample.exe "summarize metadata"

# Server (HTTP control server trên 127.0.0.1, cần bearer token)
python -m rikugan.cli.headless serve /path/to/sample.exe --ready-file ready.json
cat ready.json  # → {"url": "...", "token": "..."}
```

Xem thêm chi tiết trong `DEVELOPMENT.md` (mục "Developing Headless Mode") — bao gồm `/events`, `/cancel`, `/shutdown`, run-id semantics, và security rules.

### Branch & commit

Fork này dùng `master` làm branch chính (không có `dev`/`main` như upstream). Branch off `master` với prefix `feat/`, `fix/`, `refactor/`, `chore/`. Commit format: `type(scope): description`.

**Release flow** (khi ready cho release):

1. **Bump version ở cả 3 nguồn** (sync — origin đã có bug bump 2/3):
   - `pyproject.toml` (`version = "..."`)
   - `ida-plugin.json` (`"version": "..."`)
   - `rikugan/constants.py` (`PLUGIN_VERSION = "..."`)
2. Commit riêng với message `chore(release): bump version to X.Y.Z`
3. Tạo tag annotated: `git tag -a vX.Y.Z -m "Rikugan vX.Y.Z\n\n<commit list since last tag>"` (từ HEAD)
4. Push: `git push origin master vX.Y.Z`
5. Đợi CI workflow (`.github/workflows/ci.yml` trigger trên cả `push` và `pull_request` tới `[master, main, dev]` — push thẳng master vẫn chạy CI; nhưng nên dùng branch + PR cho safety)

> **Lưu ý remote:** `origin` → fork `EliteClassRoom/rikugan` (master), `tuna-main` → upstream `tuna1999/Rikugan` (main). Đừng push nhầm remote. Fork này không có required-PR workflow, nên force-push nhầm lên master bypass review — dùng branch + PR. Vẫn nên chạy `./ci-local.sh` trước khi push để bắt lỗi sớm (CI trên runner chậm hơn local).

---

## Kiến trúc tổng quan

### Phân lớp chính

```
┌──────────────────────────────────────────────────────────────┐
│  rikugan_plugin.py           (IDA entry: PLUGIN_ENTRY)       │
│  rikugan/cli/headless.py     (Headless CLI: ask, serve)      │
└─────────────────┬────────────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│ agent/ │  │ tools/   │  │ ui/      │  ← host-agnostic core
│ loop.py│  │ base.py  │  │ panel_…  │
│ turn.py│  │ registry │  │ chat_…   │
│ explor.│  │ IDA impls│  │ session_ │
│ subag. │  │ in rikug.│  │ control… │
│ plan_  │  │ an/tools/│  │          │
└────────┘  └────┬─────┘  └──────────┘
                 │
                 ▼
           ┌──────────┐
           │ rikugan/ │
           │   ida/   │  ← IDA Pro host (tools, UI, dispatch, headless bootstrap)
           └──────────┘

  providers/  mcp/  skills/  state/  core/  control/  headless/
                (tất cả host-agnostic, được ghép vào tùy host)
```

- **`agent/`** chứa core agentic loop (host-agnostic) — `AgentLoop.run()` là generator, yield `TurnEvent` cho UI consume
- **`tools/`** là framework chung (`@tool` decorator, `ToolDefinition`, `ToolRegistry`). Implementations cụ thể nằm trong cùng package (`navigation.py`, `decompiler.py`, `microcode.py`, ...) và được host-specific registry pull vào
- **`ida/`** chỉ chứa glue cho IDA Pro: `dispatch.py` (main-thread marshalling), `headless_bootstrap.py` (entry point khi chạy qua `idat -S`), `ui/panel.py` (Qt panel wrapper), `ui/session_controller.py` (kế thừa `SessionControllerBase`)
- **`ui/`** chứa Qt widgets dùng chung (host-agnostic về lý thuyết, hiện tại chỉ dùng trong IDA host)
- **`core/`** chứa config, errors, sanitization, thread-safety helpers, host context
- **`providers/`** — Anthropic, OpenAI, Gemini, Ollama, MiniMax, Codex, OpenAI-compat; mọi provider implement `LLMProvider` ABC
- **`headless/`** + **`control/`** — utilities cho headless execution, HTTP control server (stdlib `ThreadingHTTPServer`)
- **`agent/pseudo_tool_schemas.py`** + **`agent/orchestra/`** — synthetic tool schemas + multi-agent orchestration pipeline (khi trace tool dispatch cho subagent)

### TurnEvent stream (huyết mạch giao tiếp)

Mọi thứ chảy qua một stream `TurnEvent` từ background thread → `queue.Queue` → Qt `QTimer._poll_events()` → UI. **Không bao giờ** dùng Qt signal xuyên thread.

Các loại event: `TURN_START`/`END`, `TEXT_DELTA`/`DONE`, `TOOL_CALL_START`/`DONE`, `TOOL_RESULT`, `EXPLORATION_*`, `MUTATION_RECORDED`, `SUBAGENT_*`, `ERROR`, `CANCELLED`, `USER_QUESTION`, `PLAN_GENERATED`, ... (xem `rikugan/agent/turn.py`).

### Modes (chế độ hoạt động)

| Mode | Trigger | Đặc điểm |
|------|---------|----------|
| Normal | mọi message | stream → tool → repeat |
| Plan | `/plan <msg>` | sinh plan → user approve bằng nút → execute từng bước |
| Exploration | `/modify <msg>` | 4 pha EXPLORE (subagent) → PLAN → EXECUTE → SAVE |
| Explore-only | `/explore <msg>` | tự động điều tra, không patch |

Subagent (xem `rikugan/agent/subagent_manager.py` + `rikugan/agent/agents/`) chạy một `SubagentRunner` riêng — isolation hoàn toàn, có thể chạy song song qua `ThreadPoolExecutor`. A2A bridge (`rikugan/agent/a2a/`) cho phép delegate task sang agent bên ngoài (Claude Code CLI, Codex CLI, A2A-compatible server).

### Skills & MCP

- **Skills**: Markdown + YAML frontmatter trong `rikugan/skills/builtins/<slug>/SKILL.md`. User tự thêm vào `~/.idapro/rikugan/skills/`. 11 skill built-in: `malware-analysis`, `linux-malware`, `deobfuscation`, `ctf`, `modify`, `smart-patch-ida`, `vuln-audit`, `ida-scripting`, `driver-analysis`, `generic-re`, `naming-convention`.
- **MCP**: client JSON-RPC 2.0 trong `rikugan/mcp/`. Tools từ MCP server được bridge vào `ToolRegistry` với prefix `mcp_<server>_<tool>`.

### Approval gates (cổng phê duyệt)

- **Plan & Save approval**: button-only state — input bị disable, mọi free-text đều bị bỏ qua. Tự re-enable khi click nút, agent xong, cancel, hoặc error
- **Script execution** (`execute_python` tool): LUÔN LUÔN cần user click Allow/Deny. Blocklist pattern (`subprocess`, `os.system`, ...) reject trước khi tới approval
- **Câu hỏi giữa chừng** (`USER_QUESTION` với options): cũng vào button-only state

### Mutation tracking & undo

Mọi tool call mutate database đều capture pre-state + build reverse operation. `/undo [N]` replay ngược. Mutating tool **phải** set `mutating=True` trong `@tool` và **phải** có entry trong `rikugan/agent/mutation.py` (cả `build_reverse_record` lẫn `capture_pre_state`).

### Context window

Auto-compaction khi vượt 80% token window. Tóm tắt đi qua `strip_injection_markers()` trước khi lưu. Persistent memory chạy trên **central memory subsystem** (`BinaryMemoryService` — SQLite structured facts + `MEMORY.md` manual notes) luôn-on; agent ghi qua `save_memory` tool, load vào system prompt mỗi session.

---

## Cảnh báo quan trọng (đọc trước khi sửa code)

### 1. Shiboken UAF — IDA Pro + Python ≥ 3.11

IDA Pro Qt binding (Shiboken) có bug Use-After-Free khi import C-extension trong lúc Qt signal đang dispatch. Hai mitigation đã có sẵn:

1. Mọi `import ida_*` **phải** đi qua `importlib.import_module()` bên trong `try/except ImportError` — KHÔNG bao giờ `import ida_funcs` ở module level
2. `rikugan_plugin.py` cài một re-entrancy guard trên `builtins.__import__`

**Python 3.10 là lựa chọn an toàn nhất** cho IDA. Version cao hơn có thể vẫn chạy nhưng không ổn định. Xem `rikugan_plugin.py` header và AGENTS.md mục "IDA API Notes".

- **Qt binding: PySide6 only.** Rikugan targets IDA ≥ 9.0, which ships PySide6 (Qt6). The `PyQt5` module in IDA 9.x is a shim over PySide6 and is not used. `rikugan/ui/qt_compat.py` is the single Qt import seam — import Qt symbols from there, not from `PySide6` directly.

### 2. Thread safety

- **Mọi IDA API call phải chạy trên main thread.** `@idasync` decorator trong `core/thread_safety.py` xử lý chuyện này — được `@tool` decorator tự động áp dụng cho IDA tools
- **Không** dùng Qt signal xuyên thread. Dùng `queue.Queue` + `QTimer` để poll
- **Cancellation** dùng `threading.Event` (`_cancelled`) — check tại: đầu mỗi retry loop, mỗi backoff sleep (0.5s), trước mỗi tool execution, trong streaming chunk loop

### 3. Untrusted binary content

Binary được analyze chứa strings, function names, decompiled code — tất cả chảy thẳng vào LLM prompt. Mọi đường từ binary đến prompt/user là attack surface. Mọi untrusted data **phải** đi qua `core/sanitize.py`:

| Hàm | Áp dụng cho |
|-----|------------|
| `sanitize_tool_result()` | mọi tool result trước khi append history |
| `sanitize_mcp_result()` | mọi MCP server response |
| `sanitize_binary_context()` | binary info trong system prompt |
| `sanitize_memory()` | nội dung MEMORY.md (manual notes) |
| `sanitize_skill_body()` | skill bodies, kể cả user-created |
| `strip_injection_markers()` | mọi raw binary data tại điểm vào |

### 4. Script execution là attack surface cao nhất

- `execute_python` **KHÔNG BAO GIỜ** auto-approve, kể cả headless mode, kể cả "fast"/"batch" mode
- **Constant centralization** (security invariant): mọi tham chiếu tới tên tool `execute_python` **phải** dùng `rikugan.constants.EXECUTE_PYTHON_TOOL_NAME` — KHÔNG bao giờ hardcode string. Typo ở bất kỳ vị trí nào sẽ silently disable approval gate. Centralize giúp grep audit dễ.
- **IDAPython docs-review gate** (origin `4295fdc`; post-error migration): docs-reviewer subagent (`rikugan/agent/agents/ida_docs_reviewer.py`) chạy **sau khi** `execute_python` fail với API-shaped error (`ImportError`, `AttributeError` cho module/attr không tồn tại), KHÔNG pre-execute. Traceback classifier (`rikugan/tools/idapython_complexity.py::classify_traceback`) quyết định có spawn reviewer không. Khi trigger, reviewer được inject Module Quick Reference (top-N IDA modules thường dùng, preloaded trong system prompt section `IDA_API_MODULE_REFERENCE_SECTION`) trước khi judge. Configurable qua `docs_review_mode` enum (`"on_error"` / `"off"`, default `"on_error"`) trong Settings. Legacy `require_ida_docs_for_complex_scripts` boolean tự migrate.
- Blocklist patterns (`subprocess`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `Popen`, `__import__("subprocess")`) → thêm vào các frozenset trong `script_guard.py`: `_BLOCKED_MODULES` (tên module), `_BLOCKED_CALLS` (tên callable), `_BLOCKED_ATTRS` (cặp `(obj, attr)`), `_BLOCKED_DUNDER_ATTRS` (dunder nguy hiểm), `_REMOVED_BUILTINS` (builtins bị strip khỏi exec namespace). AST check trong `_check_ast()` reject trước khi tới approval.
- `exec()` chạy trong namespace hạn chế, `stdout`/`stderr` redirect về `StringIO`
- Không thêm `os`, `sys`, `subprocess`, `shutil`, `pathlib` vào default namespace

### 5. Headless security

- Control server chỉ bind `127.0.0.1`. `--host 0.0.0.0` bị block
- Mọi endpoint (trừ `/health`) đều cần `Bearer <TOKEN>`. Auth token chỉ xuất hiện trong ready-file / startup stdout, KHÔNG log ra
- `/health` chỉ trả `{"status": "ok"}` — không leak path, token, config
- Bootstrap params truyền qua env var JSON file (`RIKUGAN_HEADLESS_BOOTSTRAP`), KHÔNG qua `-S` args (Windows quoting dễ vỡ)
- `IdaHeadlessDispatcher` **không** được import `ida_kernwin`

### 6. IDA 9.x API changes (cần biết khi sửa tools)

- `ida_struct` / `ida_enum` đã bị remove → dùng `ida_typeinf` UDT API (`tinfo_t.create_udt()`, `add_udm()`, `iter_struct()`, `iter_enum()`)
- `idc` vẫn còn wrapper cho enum (`add_enum`, `get_enum`, ...)
- UDT offsets đơn vị **bits** — nhân 8 trước khi truyền vào `udm_t` / `add_udm()`
- `lvar_t.set_user_type()` không nhận args — dùng `modify_user_lvar_info(ea, MLI_TYPE, lsi)` để persist
- `tinfo_t.parse(decl)` chấp nhận `til=None` (dùng default IDB TIL)
- `ida_hexrays.decompile()` raise `DecompilationFailure` — luôn wrap `try/except`

### 7. Style & import conventions

- Mọi module bắt đầu bằng `from __future__ import annotations`
- Type hints ở mọi signature. Tool params dùng `typing.Annotated[type, "description"]`
- Dataclass cho mọi structured data (config, events, records) — không xài dict lung tung
- **Cross-package imports**: `from rikugan.tools.base import tool` (absolute)
- **Within package**: cũng absolute: `from rikugan.tools.navigation import jump_to`
- **Host API imports**: `importlib.import_module()` trong `try/except ImportError`
- f-string cho format, hex address `f"0x{ea:x}"`. Không mutation, không bare `except:`, không magic numbers

---

## Cách thêm thứ mới (cheat sheet)

### Tool mới

```python
# File: rikugan/tools/my_category.py
from typing import Annotated
from rikugan.tools.base import tool

@tool(category="navigation", mutating=False)
def my_tool(address: Annotated[str, "Target address (hex)"]) -> str:
    """Tool description cho LLM đọc."""
    ea = parse_addr(address)
    return f"Jumped to 0x{ea:x}"
```

Rồi thêm module vào `_BOOT_TOOL_MODULES` trong `rikugan/ida/tools/registry.py`. Nếu `mutating=True`, **bắt buộc** thêm `build_reverse_record` + `capture_pre_state` vào `rikugan/agent/mutation.py`.

### Skill mới

Tạo `rikugan/skills/builtins/<slug>/SKILL.md` với YAML frontmatter:

```markdown
---
name: My Skill
description: One-line description
tags: [analysis]
allowed_tools: [decompile_function, rename_function]
---
Task: <instruction cho agent>
```

Thư mục `references/` (optional) chứa file `.md` sẽ auto-append vào prompt.

### Provider LLM mới

Kế thừa `LLMProvider` ABC trong `rikugan/providers/base.py`, đăng ký trong `rikugan/providers/registry.py`. OpenAI-compatible (MiniMax, custom endpoint) có thể kế thừa `OpenAICompatProvider` cho gọn.

### Config field mới

Thêm vào `RikuganConfig` dataclass (`rikugan/core/config.py`), cập nhật `load()`/`validate()`/`save()`. Nếu cần UI, thêm vào `SettingsDialog._build_behavior_group()` và wire trong `_on_accept()`.

---

## Verify trước khi merge

- [ ] `./ci-local.sh` pass (format + lint + mypy + pytest + desloppify)
- [ ] Tool mới đã register trong `rikugan/ida/tools/registry.py`
- [ ] Mutating tool có `build_reverse_record` + `capture_pre_state` trong `mutation.py`
- [ ] Getter tool dùng bởi `capture_pre_state` trả raw data, không format string
- [ ] `_check_cancelled()` có mặt trong mọi loop/blocking wait mới
- [ ] Host API imports dùng `importlib.import_module()` + `try/except ImportError`
- [ ] Config field mới có đủ `load()`/`validate()`/`save()` + settings dialog
- [ ] Không dùng `threading.Event`/Qt signal cho cross-thread communication
- [ ] Mọi untrusted data đi qua `core/sanitize.py`
- [ ] `execute_python` KHÔNG auto-approve
