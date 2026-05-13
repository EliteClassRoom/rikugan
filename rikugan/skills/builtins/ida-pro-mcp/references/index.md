# IDA Module Reference Index

Detailed API documentation for each IDA module is available in `resources/`.
These were sourced from https://github.com/mrexodia/ida-pro-mcp.

## High-Use Modules
- `ida_bytes.md` — Byte/memory operations
- `ida_funcs.md` — Function management
- `ida_hexrays.md` — Decompiler (Hex-Rays) API
- `ida_typeinf.md` — Type system, structs, enums
- `ida_name.md` — Symbol naming
- `idautils.md` — High-level iterators

## Medium-Use Modules
- `ida_segment.md` — Segment management
- `ida_xref.md` — Cross-references
- `ida_ua.md` — Instruction decoding
- `ida_frame.md` — Stack frame analysis
- `ida_kernwin.md` — UI, dialogs, user input

## Specialized Modules
- `ida_dbg.md` — Debugger API
- `ida_nalt.md` — Netnode storage (persistent data)
- `ida_regfinder.md` — Register value tracking
- `ida_auto.md` — Auto-analysis control
- `ida_search.md` — Binary pattern search
- `ida_loader.md` — File format loading
- `ida_entry.md` — Entry point management
- `ida_gdl.md` — Graph/flow chart
- `ida_lines.md` — Line/pseudocode formatting
- `ida_problems.md` — Problem reporting

## Additional Modules
- `ida_bitrange.md`, `ida_dirtree.md`, `ida_diskio.md`, `ida_expr.md`
- `ida_fixup.md`, `ida_fpro.md`, `ida_graph.md`, `ida_ida.md`
- `ida_idaapi.md`, `ida_idc.md`, `ida_idd.md`, `ida_idp.md`
- `ida_ieee.md`, `ida_libfuncs.md`, `ida_merge.md`, `ida_mergemod.md`
- `ida_moves.md`, `ida_netnode.md`, `ida_offset.md`, `ida_pro.md`
- `ida_range.md`, `ida_registry.md`, `ida_segregs.md`, `ida_srclang.md`
- `ida_strlist.md`, `ida_tryblks.md`, `ida_undo.md`
- `idaapi.md`, `idadex.md`, `idc.md`, `init.md`

When you need detailed documentation about a specific module, use `web_fetch` to read the raw file from GitHub:
```
web_fetch(url="https://raw.githubusercontent.com/mrexodia/ida-pro-mcp/main/skills/idapython/docs/<module>.md")
```
