# Example Queries and Expected Documentation

## Query: "How do I read a byte at an address?"

**Preferred (Domain API - IDA 9.1+):**
- Documentation: https://ida-domain.docs.hex-rays.com/ref/bytes/
- Code:
```python
from ida_domain import Database
with Database.open() as db:
    byte_val = db.bytes.get_byte_at(0x401000)
```

**Alternative (IDAPython):**
- Documentation: https://python.docs.hex-rays.com/ida_bytes/index.html#ida_bytes.get_byte
- Code:
```python
byte_value = idc.get_wide_byte(0x401000)  # Read a byte
```
**Module:** idc or ida_bytes
**Function:** get_byte, get_wide_byte

---

## Query: "How do I iterate all functions in the database?"

**Preferred (Domain API - IDA 9.1+):**
- Documentation: https://ida-domain.docs.hex-rays.com/ref/functions/
- Examples: https://ida-domain.docs.hex-rays.com/examples/#function-analysis
- Code:
```python
from ida_domain import Database
with Database.open() as db:
    for func in db.functions:
        print(f"{func.name}: {hex(func.start_ea)}")
```

**Alternative (IDAPython):**
- Documentation: https://python.docs.hex-rays.com/idautils/index.html#idautils.Functions
- Code:
```python
for func_ea in idautils.Functions():
    func_name = idc.get_func_name(func_ea)
    print(f"{hex(func_ea)}: {func_name}")
```
**Module:** idautils
**Function:** Functions()

---

## Query: "How do I analyze cross-references?"

**Preferred (Domain API - IDA 9.1+):**
- Documentation: https://ida-domain.docs.hex-rays.com/ref/xrefs/
- Examples: https://ida-domain.docs.hex-rays.com/examples/#cross-reference-analysis
- Code:
```python
from ida_domain import Database
with Database.open() as db:
    for xref in db.xrefs.to_ea(target_addr):
        print(f"From {hex(xref.from_ea)} to {hex(xref.to_ea)}")
```

**Alternative (IDAPython):**
- Documentation: https://python.docs.hex-rays.com/idautils/index.html#idautils.XrefsTo
- Code:
```python
for xref in idautils.XrefsTo(target_addr):
    print(f"From {hex(xref.frm)} to {hex(xref.to)}")
```

---

## Query: "How do I create a custom action in IDA?"

**Documentation to fetch:**
1. https://docs.hex-rays.com/developer-guide/idapython/idapython-examples#actions (Intermediate)
2. https://python.docs.hex-rays.com/ida_kernwin/index.html (UI module)
3. GitHub source: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/ui/actions.py

**Relevant APIs:**
- ida_kernwin.register_action
- ida_kernwin.action_handler_t
- ida_kernwin.action_desc_t
- ida_kernwin.attach_action_to_menu

**Note:** Domain API doesn't cover UI actions - use IDAPython for this

---

## Query: "How do I work with structures in IDA 9?"

**Documentation to fetch:**
1. https://docs.hex-rays.com/developer-guide/idapython/idapython-examples#working-with-types
2. https://python.docs.hex-rays.com/ida_typeinf/index.html
3. GitHub types examples: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/types

**Relevant APIs (IDA 9+):**
- tinfo_t.create_udt()
- tinfo_t.add_udm()
- udm_t (member info)
- ida_typeinf.parse_decl()

---

## Query: "How do I decompile a function?"

**Documentation to fetch:**
1. https://python.docs.hex-rays.com/ida_hexrays/index.html#id0
2. https://docs.hex-rays.com/developer-guide/idapython/idapython-examples#vds1
3. GitHub decompiler examples: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/decompiler

**Relevant code snippet:**
```python
cfunc = ida_hexrays.decompile(ea)
print(cfunc)
```
**Module:** ida_hexrays
**Function:** decompile()

**Note:** Domain API doesn't provide decompilation - use IDAPython's ida_hexrays

---

## Query: "What changed in IDA 9.2?"

**Documentation to fetch:**
- Release notes: https://docs.hex-rays.com/release-notes/9_2.md

**Relevant sections to look for:**
- "API Changes"
- "Breaking Changes"
- "Deprecations"
- "New Features"

---

## Query: "How do I install the Domain API?"

**Documentation to fetch:**
- Getting Started: https://ida-domain.docs.hex-rays.com/getting_started/

**Relevant steps:**
1. Set IDADIR environment variable
2. pip install ida-domain
3. Verify installation

**Code:**
```bash
# Set IDADIR (example for Linux)
export IDADIR="/opt/ida-9.2/"

# Install via pip
pip install ida-domain

# Verify
python -c "from ida_domain import Database; print('OK')"
```

---

## Query: "Find an example of how to work with types/structures"

**Documentation to fetch:**
- GitHub SDK examples (types): https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/types
- Documentation examples: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples#working-with-types

**GitHub Examples (recommended):**
- Beginner: create_struct_by_parsing.py, list_struct_member.py
- Intermediate: create_structure_programmatically.py, apply_callee_tinfo.py
- Advanced: operand_to_struct_member.py, change_stkvar_type.py

**Source code URLs:**
- https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/types/create_struct_by_parsing.py
- https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/types/create_structure_programmatically.py

---

## Query: "Find debugger examples from the SDK"

**Documentation to fetch:**
- GitHub SDK examples (debugger): https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/debugger

**Examples available:**
- Beginner: print_registers.py, show_debug_names.py
- Intermediate: print_call_stack.py, registers_context_menu.py
- Advanced: automatic_steps.py, dbg_trace.py, simple_appcall_linux.py, simple_appcall_win.py

**Source code URL:**
- https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/debugger/print_registers.py

---

## Query: "How do I iterate strings in the database?"

**Preferred (Domain API - IDA 9.1+):**
- Documentation: https://ida-domain.docs.hex-rays.com/ref/strings/
- Examples: https://ida-domain.docs.hex-rays.com/examples/#string-analysis
- Code:
```python
from ida_domain import Database
with Database.open() as db:
    for item in db.strings:
        print(f"{hex(item.address)}: {str(item)}")
```

**Alternative (IDAPython):**
- Documentation: https://python.docs.hex-rays.com/ida_strlist/ or idautils.Strings()
- Code:
```python
for s in idautils.Strings():
    print(f"{hex(s.ea)}: {s}")
```

---

## Query: "How do I add a breakpoint?"

**Documentation to fetch:**
1. https://python.docs.hex-rays.com/ida_dbg/index.html
2. GitHub debugger examples: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/debugger

**Relevant APIs:**
- ida_dbg.add_bpt()
- ida_dbg.enable_bpt()
- ida_dbg.delete_bpt()

**Example (IDAPython):**
```python
ida_dbg.add_bpt(0x401000)
ida_dbg.enable_bpt(0x401000, True)
```

---

## Query: "How do I get xrefs to a function?"

**Preferred (Domain API - IDA 9.1+):**
- Documentation: https://ida-domain.docs.hex-rays.com/ref/xrefs/
- Code:
```python
from ida_domain import Database
with Database.open() as db:
    # Get xrefs TO a function
    for xref in db.xrefs.calls_to(func.start_ea):
        print(f"Call from {hex(xref.from_ea)}")
```

**Alternative (IDAPython):**
- Documentation: https://python.docs.hex-rays.com/idautils/index.html#idautils.XrefsTo
- Code:
```python
for xref in idautils.XrefsTo(func_ea, 0):
    print(f"{hex(xref.frm)} -> {hex(xref.to)}")
```
