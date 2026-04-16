# IDA Pro Documentation Site Map

## IDAPython Reference (python.docs.hex-rays.com)

### Module Index
Landing page: https://python.docs.hex-rays.com/

Modules available:
- Core: idautils, idc, ida_idaapi, idaapi
- Functions: ida_funcs, ida_frame, ida_name, ida_entry
- Data: ida_bytes, ida_nalt, ida_offset, ida_fixup
- Disassembly: ida_ua, ida_idp, ida_search, ida_gdl, ida_graph
- Decompiler: ida_hexrays
- Types: ida_typeinf, ida_struct (deprecated), ida_enum (deprecated)
- UI: ida_kernwin, ida_lines, ida_moves, ida_dirtree
- Debugging: ida_dbg, ida_idd
- Database: ida_netnode, ida_loader, ida_auto, ida_diskio
- Analysis: ida_problems, ida_libfuncs, ida_lumina, ida_tryblks
- Utilities: ida_pro, ida_ida, ida_expr, ida_strlist, ida_registry, ida_fpro, ida_ieee, ida_bitrange, ida_tryblks, ida_undo, ida_merge, ida_mergemod, ida_srclang, ida_regfinder, idadex, init, lumina_model

### Quick Reference by Task
URL: https://python.docs.hex-rays.com/ (scroll to "Quick Reference by Task")
- Reading/Writing Bytes
- Working with Functions
- Names and Labels
- Segments
- Cross-References
- Types and Structures
- Decompilation
- UI and Dialogs
- Debugging
- Search

## IDAPython Examples (docs.hex-rays.com)

### Category Index
URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples

Categories:
1. **User Interface (UI)** - Widgets, dialogs, forms, actions, coloring, graphs
2. **Disassembly** - Flowchart, prefixes, imports, patched bytes, problems, segments, strings
3. **Decompilation** - Decompile, microcode, c-tree, user lvars, hints
4. **Debuggers** - Registers, call stack, breakpoints, tracing
5. **Working with Types** - Structures, enums, arrays, bitfields, stack frames, type libraries
6. **Miscellaneous** - IDAPythonrc, IDC extension

Difficulty levels: Beginner, Intermediate, Advanced

### Example Source Code
GitHub repository: https://github.com/HexRaysSA/IDAPython
Path pattern: https://github.com/HexRaysSA/IDAPython/tree/9.0sp1/examples/<category>/<example>.py

## Developer Guide Index
URL: https://docs.hex-rays.com/developer-guide

Contains:
- IDAPython
  - Getting Started: https://docs.hex-rays.com/developer-guide/idapython/idapython-getting-started
  - Examples: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples
  - Porting Guide (IDA 9): https://docs.hex-rays.com/developer-guide/idapython/idapython-porting-guide-ida-9
  - Writing Plugins: https://docs.hex-rays.com/developer-guide/idapython/how-to-create-a-plugin
- C++ SDK
- Release Notes

## IDA Domain API (ida-domain.docs.hex-rays.com)

### Overview
URL: https://ida-domain.docs.hex-rays.com/
Purpose: High-level Python API for IDA, simpler than IDAPython
Requirements: IDA Pro 9.1.0 or later
Open Source: https://github.com/HexRaysSA/ida-domain
PyPI: https://pypi.org/project/ida-domain/

### Documentation Structure
- **Intro**: https://ida-domain.docs.hex-rays.com/
- **Getting Started**: https://ida-domain.docs.hex-rays.com/getting_started/
- **Examples**: https://ida-domain.docs.hex-rays.com/examples/
  - Basic Database Operations
  - Function Analysis
  - Signature Files (FLIRT)
  - String Analysis
  - Bytes Analysis
  - Type Analysis
  - Cross-Reference Analysis
  - Event Handling (Hooks)
- **API Reference**: https://ida-domain.docs.hex-rays.com/usage/
  - Database
  - Flowchart
  - Bytes
  - Comments
  - Entries
  - Hooks
  - Functions
  - Heads
  - Imports
  - Instructions
  - Names
  - Operands
  - Segments
  - Signature Files
  - Strings
  - Types
  - Xrefs

### Key Advantages over IDAPython
- Domain-focused design (Functions, Types, Xrefs as first-class)
- Open source and community-driven
- Pure Python (no compilation needed)
- Modern Python best practices
- Independently versioned
- Simple installation via pip

## Release Notes (docs.hex-rays.com/release-notes)

### Version History
URL: https://docs.hex-rays.com/release-notes

Recent versions (newest first):
- IDA 9.3sp1, 9.3, 9.3 Beta
- IDA 9.2, 9.2 Beta
- IDA 9.1
- IDA 9.0sp1, 9.0
- IDA 8.5, 8.4sp2, 8.4sp1, 8.4
- IDA 8.3, 8.2sp1, 8.2, 8.1, 8.0sp1, 8.0
- And older versions back to IDA 5.0

### Use Cases
- API changes between versions
- Deprecated feature alerts
- New feature discovery
- Version-specific behavior
- Migration planning

## Getting Started for New Users (docs.hex-rays.com/getting-started)

### Topics
URL: https://docs.hex-rays.com/getting-started
- License activation (My Hex-Rays portal)
- Install IDA
- Basic IDA usage
- Begin scripting with Domain API

## Documentation Hub (docs.hex-rays.com)

### Top-Level Index
URL: https://docs.hex-rays.com/

Links to:
- Getting Started (for new users)
- Developer Guide (IDAPython, C++ SDK)
- Release Notes
- All Hex-Rays documentation

## IDA SDK GitHub Repository (github.com/HexRaysSA/ida-sdk)

### Official IDAPython Examples
URL: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples

### Categories
1. **debugger/** - Debugging session examples
2. **decompiler/** - Decompiler/Hex-Rays examples
3. **disassembler/** - Disassembly listing examples
4. **idbs/** - Database handling examples
5. **misc/** - Miscellaneous examples
6. **types/** - Type system (structures, enums) examples
7. **ui/** - User interface (widgets, dialogs, actions) examples

### Example Structure
Each example includes:
- Source code: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/<category>/<example>.py
- Summary and description
- APIs used (list of module.function)
- Difficulty level (Beginner/Intermediate/Advanced)

### Key Differences from docs.hex-rays.com/examples
- Source code is directly accessible (not just documentation)
- Examples are tested and maintained by Hex-Rays developers
- Includes all categories (debugger, decompiler, etc.)
- Community-driven via GitHub issues/PRs

### Raw Index File
URL: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/index.md (3677 lines)
