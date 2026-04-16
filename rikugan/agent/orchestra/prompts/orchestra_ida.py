"""IDA-specific Orchestra prompts."""

from __future__ import annotations

ORCHESTRA_IDA_PROMPT = """

## IDA Pro Analysis Context

When analyzing binaries in IDA Pro:

- **Decompiler tools**: `decompile_function`, `get_function_at`, `fetch_disassembly`
- **Xref tools**: `get_xrefs_to`, `get_xrefs_from`, `get_function_xrefs`
- **Type tools**: `get_type_info`, `apply_type`, `declare_c_type`
- **String tools**: `list_strings`, `get_string_at`
- **Function tools**: `list_functions`, `get_function_name`, `rename_function`
- **Annotation tools**: `set_comment`, `set_function_comment`

## Delegation Recommendations

| Task Type | Recommended Tools | Model |
|-----------|------------------|-------|
| String extraction | `list_strings` | haiku |
| Xref chasing | `get_xrefs_to`, `get_xrefs_from` | sonnet |
| Function decompilation | `decompile_function` | sonnet |
| Type analysis | `get_type_info`, `apply_type` | sonnet |
| Quick rename | `rename_function` | haiku |
| Full analysis | All tools above | sonnet |

## Context Tips

- Pass the current function address and name in context
- Pass relevant xref targets/addresses
- Pass any known string constants or structure names
"""
