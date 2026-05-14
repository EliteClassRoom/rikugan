# Binary Ninja Vulnerability Audit Tools

## Evidence Gathering (Read-Only)

Use these in this order for each suspected finding:

1. **`get_binary_info`** — file format, architecture, bitness, entry point, function count, file type hints.
2. **`list_segments`** — segment ranges and permissions; flag W+X segments and unusual executable data.
3. **`list_imports`** — full API surface: memory ops, network, files, process launch, crypto, IPC, kernel interfaces.
4. **`list_exports`** — externally reachable entry points.
5. **`decompile_function`** — primary evidence source. Read the HLIL pseudocode for the function.
6. **`get_pseudocode`** — raw HLIL lines with addresses (useful for evidence snippets).
7. **`get_decompiler_variables`** — stack variables, argument types, local sizes. Map every buffer and its capacity.
8. **`xrefs_to`** — find all call sites of a dangerous API; trace callers of a source input.
9. **`function_xrefs`** — map callers and callees to place a function in the call graph. Use before decompiling to prioritize which functions need deep analysis.
10. **`read_disassembly`** / **`read_function_disassembly`** — raw disassembly when HLIL is ambiguous.
11. **`search_strings`** / **`list_strings`** — find format strings, command templates, path patterns, and credential references.

## IL/SSA Evidence Tools (Binary Ninja Only)

When HLIL is ambiguous or folds away important details, drop to IL:

- **`get_il(address, level)`** — read all IL instructions for a function. Use MLIL to see typed variables and data flow; LLIL for instruction-level detail. MLIL is usually the right level for taint tracing — it shows variable types and arithmetic without HLIL's expression folding.
- **`get_cfg(address, level)`** — control flow graph: blocks, edges, back-edges, dominators, loop headers. Use to verify that a suspicious code path is reachable and not dead code behind an always-false condition.
- **`track_variable_ssa(address, variable_name, level)`** — trace a variable through SSA definitions and uses. Every assignment, every phi node, every constant value. The primary tool for source-to-sink taint tracking — follow an attacker-controlled variable from input to sink through every intermediate definition.

### IL Level Selection

| Level | When to use |
|---|---|
| HLIL | Primary analysis — start here with `decompile_function`. |
| MLIL | When HLIL folds checks away, when arithmetic types are ambiguous, when tracing variable assignments through phi nodes. |
| LLIL | When you need instruction-level detail for architecture-specific checks (e.g., verifying a `CMP`/`JBE` pair exists). |

## Helper Analysis

- **`execute_python`** — use only for bounded analysis when built-in tools are insufficient:
  - Calculating integer overflow boundaries for attacker-controlled sizes.
  - Decoding constant arrays that appear to be encryption keys or encoded strings.
  - Checking simple constraints (e.g., "does this check actually guard that copy?").
  - NEVER use for bulk searching, renaming, or mutation — keep the audit read-only.

## Binary Ninja Specific Notes

- HLIL may fold multiple checks into a single condition — if you see a complex condition in HLIL, verify with MLIL that individual checks are not being hidden.
- Inlined functions may hide dangerous calls that are visible in LLIL — use `get_il` with LLIL level to check for hidden `call` IL instructions.
- Binary Ninja's type recovery may insert casts that mask truncation — verify operand sizes at MLIL level.
- `track_variable_ssa` traces the variable through SSA, which preserves every definition including phi nodes from joined control flow paths. Use it to verify that a bounds check on one path also guards the sink on all other paths.

## Mutation (Only If User Explicitly Requests)

- **Do not** rename, retype, comment, or patch unless the user asks.
- If annotations would clarify a finding, propose them first and wait for approval.
