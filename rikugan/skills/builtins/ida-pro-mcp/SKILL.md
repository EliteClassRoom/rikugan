---
name: IDAPython Reference
description: IDA Pro Python scripting for reverse engineering. Use when writing IDAPython scripts, analyzing binaries, working with IDA's API for disassembly, decompilation (Hex-Rays), type systems, cross-references, functions, segments, or any IDA database manipulation.
tags: [ida, idapython, scripting, reverse-engineering, api-reference]
triggers:
  - idapython
  - ida python
  - write ida script
  - ida api
  - ida_bytes
  - ida_funcs
  - ida_hexrays
  - ida_typeinf
  - ida_name
  - ida_segment
  - ida_xref
  - ida_kernwin
  - idautils
author: Rikugan (sourced from mrexodia/ida-pro-mcp)
version: 1.0
allowed_tools:
  - web_fetch
  - execute_python
  - decompile_function
  - get_decompiler_variables
  - get_pseudocode
  - list_functions
  - search_functions
  - get_function_info
  - list_strings
  - search_strings
  - get_string_at
  - read_bytes
  - read_disassembly
  - read_function_disassembly
  - get_instruction_info
  - set_comment
  - set_function_comment
  - set_type
  - rename_function
  - rename_address
  - rename_variable
  - xrefs_to
  - xrefs_from
  - function_xrefs
---

# IDAPython

Use modern `ida_*` modules. Avoid legacy `idc` module.

## Module Router

| Task | Module | Key Items |
|------|--------|-----------|
| Bytes/memory | `ida_bytes` | `get_bytes`, `patch_bytes`, `get_flags`, `create_*` |
| Functions | `ida_funcs` | `func_t`, `get_func`, `add_func`, `get_func_name` |
| Names | `ida_name` | `set_name`, `get_name`, `demangle_name` |
| Types | `ida_typeinf` | `tinfo_t`, `apply_tinfo`, `parse_decl` |
| Decompiler | `ida_hexrays` | `decompile`, `cfunc_t`, `lvar_t`, ctree visitor |
| Segments | `ida_segment` | `segment_t`, `getseg`, `add_segm` |
| Xrefs | `ida_xref` | `xrefblk_t`, `add_cref`, `add_dref` |
| Instructions | `ida_ua` | `insn_t`, `op_t`, `decode_insn` |
| Stack frames | `ida_frame` | `get_frame`, `define_stkvar` |
| Iteration | `idautils` | `Functions()`, `Heads()`, `XrefsTo()`, `Strings()` |
| UI/dialogs | `ida_kernwin` | `msg`, `ask_*`, `jumpto`, `Choose` |
| Database info | `ida_ida` | `inf_get_*`, `inf_is_64bit()` |
| Analysis | `ida_auto` | `auto_wait`, `plan_and_wait` |
| Flow graphs | `ida_gdl` | `FlowChart`, `BasicBlock` |
| Register tracking | `ida_regfinder` | `find_reg_value`, `reg_value_info_t` |

## Core Patterns

### Iterate functions
```python
for ea in idautils.Functions():
    name = ida_funcs.get_func_name(ea)
    func = ida_funcs.get_func(ea)
```

### Iterate instructions in function
```python
for head in idautils.FuncItems(func_ea):
    insn = ida_ua.insn_t()
    if ida_ua.decode_insn(insn, head):
        print(f"{head:#x}: {insn.itype}")
```

### Cross-references
```python
for xref in idautils.XrefsTo(ea):
    print(f"{xref.frm:#x} -> {xref.to:#x} type={xref.type}")
```

### Read/write bytes
```python
data = ida_bytes.get_bytes(ea, size)
ida_bytes.patch_bytes(ea, b"\x90\x90")
```

### Names
```python
name = ida_name.get_name(ea)
ida_name.set_name(ea, "new_name", ida_name.SN_NOCHECK)
```

### Decompile function
```python
cfunc = ida_hexrays.decompile(ea)
if cfunc:
    print(cfunc)  # pseudocode
    for lvar in cfunc.lvars:
        print(f"{lvar.name}: {lvar.type()}")
```

### Walk ctree (decompiled AST)
```python
class MyVisitor(ida_hexrays.ctree_visitor_t):
    def visit_expr(self, e):
        if e.op == ida_hexrays.cot_call:
            print(f"Call at {e.ea:#x}")
        return 0

cfunc = ida_hexrays.decompile(ea)
MyVisitor().apply_to(cfunc.body, None)
```

### Apply type
```python
tif = ida_typeinf.tinfo_t()
if ida_typeinf.parse_decl(tif, None, "int (*)(char *, int)", 0):
    ida_typeinf.apply_tinfo(ea, tif, ida_typeinf.TINFO_DEFINITE)
```

### Create structure
```python
# IDA 9.x: udm_t.offset and udm_t.size are in BITS, not bytes.
# Always multiply byte offsets/sizes by 8.
udt = ida_typeinf.udt_type_data_t()
m = ida_typeinf.udm_t()
m.name = "field1"
t = ida_typeinf.tinfo_t()
t.create_simple_type(ida_typeinf.BT_INT32)  # preferred over tinfo_t(BTF_INT32)
m.type = t
m.offset = 0 * 8   # BITS (byte 0)
m.size = 4 * 8     # BITS (4 bytes)
udt.push_back(m)
tif = ida_typeinf.tinfo_t()
tif.create_udt(udt, ida_typeinf.BTF_STRUCT)
tif.set_named_type(None, "MyStruct", ida_typeinf.NTF_REPLACE)
```
⚠ **Critical**: Offsets/sizes in bits, not bytes. Use `create_simple_type()` not `tinfo_t(BTF_*)` constructor.

### Strings list
```python
for s in idautils.Strings():
    print(f"{s.ea:#x}: {str(s)}")
```

### Wait for analysis
```python
ida_auto.auto_wait()  # Block until autoanalysis completes
```

## Key Constants

| Constant | Value/Use |
|----------|-----------|
| `BADADDR` | Invalid address sentinel |
| `ida_name.SN_NOCHECK` | Skip name validation |
| `ida_typeinf.TINFO_DEFINITE` | Force type application |
| `o_reg`, `o_mem`, `o_imm`, `o_displ`, `o_near` | Operand types |
| `dt_byte`, `dt_word`, `dt_dword`, `dt_qword` | Data types |
| `fl_CF`, `fl_CN`, `fl_JF`, `fl_JN`, `fl_F` | Code xref types |
| `dr_R`, `dr_W`, `dr_O` | Data xref types |

## Critical Rules

1. **Wait for analysis**: Call `ida_auto.auto_wait()` before reading results
2. **Thread safety**: IDA SDK calls must run on main thread (Rikugan handles this automatically via `@idasync`)
3. **64-bit addresses**: Always assume `ea_t` can be 64-bit
4. **For hex conversion**: Use Python f-strings like `f"{ea:#x}"` or `hex(ea)`

## Anti-Patterns

| Avoid | Do Instead |
|-------|------------|
| `idc.*` functions | Use `ida_*` modules |
| Hardcoded addresses | Use names, patterns, or xrefs |
| Guessing at types | Derive from disassembly/decompilation |

## Detailed API Reference

Comprehensive module references are available via `web_fetch` from GitHub raw URLs:
```
web_fetch(url="https://raw.githubusercontent.com/mrexodia/ida-pro-mcp/main/skills/idapython/docs/<module>.md")
```

Key modules to fetch on demand:
- **High-use**: `ida_bytes.md`, `ida_funcs.md`, `ida_hexrays.md`, `ida_typeinf.md`, `ida_name.md`, `idautils.md`
- **Medium-use**: `ida_segment.md`, `ida_xref.md`, `ida_ua.md`, `ida_frame.md`, `ida_kernwin.md`
- **Specialized**: `ida_dbg.md` (debugger), `ida_nalt.md` (netnode storage), `ida_regfinder.md` (register tracking)

A complete module index is available in the skill's `references/index.md`.
Source: https://github.com/mrexodia/ida-pro-mcp