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
author: Rikugan
version: 1.0
allowed_tools:
  - web_fetch
  - mcp_fetch
---

Task: IDA Documentation Search. You are helping the user find information in official IDA Pro documentation.

## Available Documentation Sources

### 1. IDAPython API Reference
URL: https://python.docs.hex-rays.com/
Purpose: Complete function/class/constant reference for all IDAPython modules
Navigation: Module index at root, individual module pages (e.g., ida_bytes, ida_funcs, idautils)
Search tip: Append /genindex.html for full-text search

### 2. IDAPython Examples
URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples
Purpose: Real-world code samples organized by category and difficulty
Categories: UI, Disassembly, Decompilation, Debugger, Types, Miscellaneous
Each example lists: source code link, APIs used, difficulty level

### 3. IDAPython Getting Started
URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-getting-started
Purpose: Beginner-friendly introduction with basic code snippets
Covers: Common variables (ea, BADADDR), basic operations per topic

### 4. IDAPython Porting Guide (IDA 8.x → 9.0)
URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-porting-guide-ida-9
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
   URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples
2. For category-specific examples (e.g., UI):
   URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples#ui
3. GitHub source (replace version in path):
   https://github.com/HexRaysSA/IDAPython/tree/9.0sp1/examples/<category>/<example>.py

### Finding Domain API (IDA 9.1+)
1. Main documentation: https://ida-domain.docs.hex-rays.com/
2. Getting started: https://ida-domain.docs.hex-rays.com/getting_started/
3. Examples by task: https://ida-domain.docs.hex-rays.com/examples/
   - Database Operations
   - Function Analysis
   - String Analysis
   - Bytes Analysis
   - Type Analysis
   - Cross-Reference Analysis
   - Hooks/Event Handling
4. API Reference: https://ida-domain.docs.hex-rays.com/usage/

### Finding Release Notes
1. Release notes index: https://docs.hex-rays.com/release-notes
2. For specific version (e.g., IDA 9.2): https://docs.hex-rays.com/release-notes/9_2.md
3. For version comparison, fetch relevant release notes and compare API sections

### Finding Getting Started Content
URL: https://docs.hex-rays.com/developer-guide/idapython/idapython-getting-started
Sections: Basics, Code snippets by topic

### Finding IDA SDK GitHub Examples
1. Main examples index: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples
2. For specific category (e.g., types): https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/types
3. For specific source code: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/<category>/<example>.py

## Workflow for Answering User Questions

When the user asks about IDA functionality:

1. Identify the topic (module, function, concept)
2. Determine if Domain API (IDA 9.1+) is appropriate (simpler, high-level tasks)
3. Select appropriate documentation source
4. Fetch relevant page(s) using web_fetch or mcp_fetch tool
5. Extract and summarize the relevant information
6. Provide code example if available

## Important Notes

- For IDA 9.1+, consider Domain API first for simpler, more Pythonic interface
- Always verify function signatures against the IDAPython Reference
- Examples in "idapython-examples" are from the IDA GitHub repository and may be version-specific
- For IDA 9.x API changes, check the Porting Guide
- When unsure which module to use, start with idautils (high-level) or idc (IDC compatibility)
- Domain API sits on top of IDAPython - they can be used together
- IDA SDK GitHub examples are production-quality and tested by Hex-Rays
