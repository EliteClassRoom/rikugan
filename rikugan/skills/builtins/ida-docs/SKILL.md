---
name: IDA Pro Documentation Search
description: Search and browse official IDA Pro documentation — IDAPython API reference, examples, getting started guides, C++ SDK, Domain API, and release notes
tags: [ida, documentation, idapython, domain-api, search, reference]
triggers:
  - ida documentation
  - idapython documentation
  - ida docs
  - search ida
  - how to use ida_bytes
  - ida_hexrays example
  - ida function
  - ida type
  - domain api
  - ida 9.1
  - ida_domain
  - ida release notes
  - ida version
  - ida example
  - idapython example
  - ida scripting
  - how do i read bytes
  - how to iterate functions
  - how to rename
  - how to create structure
  - how to use decompiler
  - how to find xrefs
author: Rikugan
version: 2.0
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

Task: IDA Documentation Search & Script Writing. You are helping the user find information in official IDA Pro documentation and write correct IDAPython scripts.

## Your Workflow

When the user asks about IDA functionality or wants to write an IDAPython script:

### Step 1 — Identify the Task
Understand what the user wants to accomplish:
- Read data at an address? → `ida_bytes` module
- Iterate over functions? → `idautils.Functions()` or Domain API
- Rename something? → `ida_name` or Domain API `db.names`
- Use the decompiler? → `ida_hexrays`
- Analyze xrefs? → Domain API `db.xrefs`
- Create structures? → `ida_typeinf` (IDA 9+)
- Find strings? → Domain API `db.strings`

### Step 2 — Fetch the Relevant Documentation

**For IDAPython Examples (recommended first step):**
```
web_fetch(url="https://docs.hex-rays.com/developer/idapython/idapython-examples", format="markdown")
```
Browse the examples index to find a category matching the user's task (UI, Disassembly, Decompilation, Debugger, Types, Miscellaneous).

**For specific example source code:**
Fetch from the official IDA SDK GitHub repo:
```
web_fetch(url="https://raw.githubusercontent.com/HexRaysSA/ida-sdk/main/src/plugins/idapython/examples/<category>/<example>.py")
```
Example categories: `debugger`, `decompiler`, `disassembler`, `idbs`, `misc`, `types`, `ui`

**For IDAPython API Reference:**
```
web_fetch(url="https://python.docs.hex-rays.com/ida_<module>/index.html", format="markdown")
```
For example: `ida_bytes`, `ida_funcs`, `ida_hexrays`, `ida_kernwin`, `ida_typeinf`, `idautils`

**For a specific function:**
```
web_fetch(url="https://python.docs.hex-rays.com/ida_bytes/index.html#ida_bytes.get_byte", format="markdown")
```

**For Domain API (IDA 9.1+, simpler interface):**
```
web_fetch(url="https://ida-domain.docs.hex-rays.com/examples/", format="markdown")
web_fetch(url="https://ida-domain.docs.hex-rays.com/getting_started/", format="markdown")
```

**For Release Notes (API changes):**
```
web_fetch(url="https://docs.hex-rays.com/release-notes/9_2.md", format="markdown")
```

### Step 3 — Read and Understand the Example/Code
Parse the fetched content:
- Identify the key API calls used
- Note the function signatures
- Understand the pattern/approach

### Step 4 — Write the Script
Use `execute_python` tool to write and run the IDAPython script:
- Use the API calls from the documentation
- Follow the patterns from the examples
- Include proper error handling

### Step 5 — Validate Against API Docs
After writing the script, fetch the relevant API reference page to verify:
- Function names are correct
- Parameter types match
- Return values are handled properly

```
web_fetch(url="https://python.docs.hex-rays.com/ida_<module>/index.html", format="markdown")
```

## Available Documentation Sources

### 1. IDAPython API Reference
URL: https://python.docs.hex-rays.com/
Purpose: Complete function/class/constant reference for all IDAPython modules
Navigation: Module index at root, individual module pages (e.g., ida_bytes, ida_funcs, idautils)
Search tip: Append /genindex.html for full-text search

### 2. IDAPython Examples
URL: https://docs.hex-rays.com/developer/idapython/idapython-examples
Purpose: Real-world code samples organized by category and difficulty
Categories: UI, Disassembly, Decompilation, Debugger, Types, Miscellaneous
Each example lists: source code link, APIs used, difficulty level

### 3. IDAPython Getting Started
URL: https://docs.hex-rays.com/developer/idapython/idapython-getting-started
Purpose: Beginner-friendly introduction with basic code snippets
Covers: Common variables (ea, BADADDR), basic operations per topic

### 4. IDAPython Porting Guide (IDA 8.x → 9.0)
URL: https://docs.hex-rays.com/developer/idapython/idapython-porting-guide-ida-9
Purpose: API changes and migration instructions

### 5. C++ SDK Reference
URL: https://cpp.docs.hex-rays.com/
Purpose: Native C++ SDK reference (for plugin development)

### 6. IDA Domain API (NEW - Recommended for IDA 9.1+)
URL: https://ida-domain.docs.hex-rays.com/
Purpose: High-level Python API built on top of IDAPython. Simpler, more Pythonic interface
Key Features: Domain-focused design, open source, pure Python, compatible with IDAPython
Requirements: IDA Pro 9.1.0 or later
Resources:
- Getting Started: https://ida-domain.docs.hex-rays.com/getting_started/
- Examples: https://ida-domain.docs.hex-rays.com/examples/
- API Reference: https://ida-domain.docs.hex-rays.com/usage/
- GitHub: https://github.com/HexRaysSA/ida-domain
- PyPI: https://pypi.org/project/ida-domain/

### 7. IDA Release Notes
URL: https://docs.hex-rays.com/release-notes
Purpose: Historical release notes for all IDA versions (5.0 through 9.3+)
Useful for: API changes between versions, deprecated features, new features
Latest versions: IDA 9.3, 9.2, 9.1, 9.0, 8.5, 8.4, 8.3, etc.

### 8. IDA Getting Started (For New Users)
URL: https://docs.hex-rays.com/getting-started
Purpose: Onboarding guide for new IDA users
Topics: License activation, installation, basic IDA usage

### 9. Documentation Hub (Index)
URL: https://docs.hex-rays.com/
Purpose: Top-level index to all Hex-Rays documentation

### 10. IDA SDK GitHub Repository (Official Examples)
URL: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples
Purpose: Official IDAPython examples from Hex-Rays developers. Production-quality, tested code.
Categories:
- debugger - Debugging examples
- decompiler - Decompiler/Hex-Rays examples
- disassembler - Disassembly listing examples
- idbs - Database handling examples
- misc - Miscellaneous examples
- types - Type system examples
- ui - User interface examples
Each example includes:
- Source code (Python)
- Keywords
- Difficulty level (Beginner/Intermediate/Advanced)
- List of APIs used
Source code URL pattern: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/<category>/<example>.py

## How to Search

### Finding IDAPython API Reference
1. For a specific module (e.g., ida_bytes):
   URL: https://python.docs.hex-rays.com/ida_bytes/index.html
2. For a specific function (e.g., get_byte):
   URL: https://python.docs.hex-rays.com/ida_bytes/index.html#ida_bytes.get_byte
3. For full-text search:
   URL: https://python.docs.hex-rays.com/genindex.html?search=<term>

### Finding Code Examples
1. Main examples page:
   URL: https://docs.hex-rays.com/developer/idapython/idapython-examples
2. For category-specific examples (e.g., UI):
   URL: https://docs.hex-rays.com/developer/idapython/idapython-examples#ui
3. GitHub source (replace version in path):
   https://github.com/HexRaysSA/IDAPython/tree/9.0sp1/examples/<category>/<example>.py

### Finding Domain API (IDA 9.1+)
1. Main documentation: https://ida-domain.docs.hex-rays.com/
2. Getting started: https://ida-domain.docs.hex-rays.com/getting_started/
3. Examples by task: https://ida-domain.docs.hex-rays.com/examples/
4. API Reference: https://ida-domain.docs.hex-rays.com/usage/

### Finding Release Notes
1. Release notes index: https://docs.hex-rays.com/release-notes
2. For specific version (e.g., IDA 9.2): https://docs.hex-rays.com/release-notes/9_2.md
3. For version comparison, fetch relevant release notes and compare API sections

### Finding Getting Started Content
URL: https://docs.hex-rays.com/developer/idapython/idapython-getting-started
Sections: Basics, Code snippets by topic

### Finding IDA SDK GitHub Examples
1. Main examples index: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples
2. For specific category (e.g., types): https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/types
3. For specific source code: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/<category>/<example>.py

## Common Patterns

| Task | IDAPython | Domain API (IDA 9.1+) |
|------|-----------|----------------------|
| Iterate functions | `idautils.Functions()` | `db.functions` |
| Read bytes | `ida_bytes.get_byte(ea)` | `db.read(ea, size)` |
| Get xrefs | `idautils.XrefsTo(ea)` | `db.xrefs.to(ea)` |
| Rename | `ida_name.set_name(ea, name)` | `db.names[ea] = name` |
| Create struct | `ida_typeinf.tinfo_t.create_udt()` | `db.types.create_struct()` |
| Decompile | `ida_hexrays.decompile(ea)` | `db.decompile(ea)` |
| Find strings | `idautils.Strings()` | `db.strings` |

## Important Notes

- For IDA 9.1+, consider Domain API first for simpler, more Pythonic interface
- Always verify function signatures against the IDAPython Reference after writing a script
- Examples in "idapython-examples" are from the IDA GitHub repository and may be version-specific
- For IDA 9.x API changes, check the Porting Guide
- When unsure which module to use, start with idautils (high-level) or idc (IDC compatibility)
- Domain API sits on top of IDAPython — they can be used together
- IDA SDK GitHub examples are production-quality and tested by Hex-Rays
- GitHub raw content is rate-limited at ~60 requests/hour unauthenticated — batch reads when possible
- Hex-Rays docs pages are large GitBook pages. Use `format='markdown'` and read in chunks with `offset`/`limit` (default 7400 chars per call). The `markdown` format will extract the documentation body from the page.
- When format='markdown' returns mostly CSS/JS, try format='html' and look for `<main>` or `<article>` sections.