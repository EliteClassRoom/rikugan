# How to Search IDA Documentation Effectively

## Identifying What to Search For

### When User Asks About...
- "How do I read bytes at an address?" → ida_bytes module OR Domain API Bytes
- "How do I iterate functions?" → idautils.Functions() OR Domain API db.functions
- "How do I rename something?" → ida_name or idc OR Domain API db.names
- "How do I create a custom UI?" → ida_kernwin, UI examples
- "How do I work with structures?" → ida_typeinf (IDA 9+), Type examples
- "How do I use the decompiler?" → ida_hexrays, Decompilation examples
- "How do I add a breakpoint?" → ida_dbg, Debugger examples
- "How do I analyze xrefs?" → Domain API db.xrefs (simplest for IDA 9.1+)
- "How do I find strings?" → Domain API db.strings (simplest for IDA 9.1+)
- "What changed in IDA 9.2?" → Release notes for 9.2
- "How do I install domain API?" → Domain API Getting Started

## Decision: Domain API vs IDAPython

**Use Domain API when:**
- Task is straightforward (iterate functions, get xrefs, read bytes)
- Writing new scripts for IDA 9.1+
- Simpler, more readable code is preferred
- No need for advanced/specialized features

**Use IDAPython when:**
- Need advanced/deprecated features
- Working with version 8.x compatibility
- Specific SDK functionality required
- Contributing to existing codebase

## Search Strategies

### 1. Domain API First (IDA 9.1+)
1. Go to: https://ida-domain.docs.hex-rays.com/
2. Check Getting Started: https://ida-domain.docs.hex-rays.com/getting_started/
3. Find relevant example: https://ida-domain.docs.hex-rays.com/examples/
4. For API details: https://ida-domain.docs.hex-rays.com/usage/

### 2. IDAPython API Lookup (Precise Function/Class)
1. Go to: https://python.docs.hex-rays.com/
2. Find module in left sidebar (e.g., "ida_bytes")
3. Open module page: https://python.docs.hex-rays.com/ida_bytes/index.html
4. Search page for function name (Ctrl+F)

### 3. Task-Based Search (What API do I use?)
1. Go to: https://python.docs.hex-rays.com/
2. Scroll to "Quick Reference by Task" section
3. Find your task category
4. Note the recommended modules/functions

### 4. Code Examples Search
1. Go to: https://docs.hex-rays.com/developer-guide/idapython/idapython-examples
2. Find category matching your task
3. Browse examples by difficulty level
4. Click example to see details (source code, APIs used)

### 5. Full-Text Search
Use browser search (Ctrl+F) on:
- https://python.docs.hex-rays.com/genindex.html for API search
- https://docs.hex-rays.com/developer-guide/idapython/idapython-examples for examples

### 6. Release Notes Search
1. Go to: https://docs.hex-rays.com/release-notes
2. For specific version: https://docs.hex-rays.com/release-notes/9_2.md
3. Look for "API Changes", "Breaking Changes", or "Deprecations" sections

### 7. IDA SDK GitHub Examples Search
1. Go to: https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples
2. Browse by category folder
3. For specific example source code:
   URL: https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/<category>/<example>.py
4. Search across all examples:
   URL: https://github.com/search?q=repo%3AHexRaysSA%2Fida-sdk+IDAPython&type=code

## Common Query Patterns

| User Query Type | Target | URL Pattern |
|-----------------|--------|------------|
| Function signature | ida_bytes.get_byte | https://python.docs.hex-rays.com/ida_bytes/index.html#ida_bytes.get_byte |
| Module overview | ida_hexrays | https://python.docs.hex-rays.com/ida_hexrays/index.html |
| Code example | Custom action | https://docs.hex-rays.com/developer-guide/idapython/idapython-examples#actions |
| Migration | IDA 8 to 9 | https://docs.hex-rays.com/developer-guide/idapython/idapython-porting-guide-ida-9 |
| Getting started | First steps | https://docs.hex-rays.com/developer-guide/idapython/idapython-getting-started |
| Domain API intro | High-level API | https://ida-domain.docs.hex-rays.com/ |
| Domain API examples | Task examples | https://ida-domain.docs.hex-rays.com/examples/ |
| IDA 9.2 release notes | Version info | https://docs.hex-rays.com/release-notes/9_2.md |
| Domain API installation | pip install | https://ida-domain.docs.hex-rays.com/getting_started/#installation |
| GitHub SDK example | UI action | https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples/ui |
| GitHub SDK source | Custom action | https://github.com/HexRaysSA/ida-sdk/blob/main/src/plugins/idapython/examples/ui/actions.py |

## Fetching Documentation in Sub-Agent

When the sub-agent needs to fetch documentation:

1. Use web_fetch or mcp_fetch tool with the appropriate URL
2. Parse the returned content for relevant information
3. Extract code snippets if available
4. Summarize findings for the user

Example fetch calls:
```
# IDAPython API
web_fetch(url="https://python.docs.hex-rays.com/ida_bytes/index.html", format="markdown")

# Domain API
web_fetch(url="https://ida-domain.docs.hex-rays.com/examples/", format="markdown")

# Release Notes
web_fetch(url="https://docs.hex-rays.com/release-notes/9_2.md", format="markdown")

# GitHub SDK Examples Index
web_fetch(url="https://github.com/HexRaysSA/ida-sdk/tree/main/src/plugins/idapython/examples", format="markdown")

# GitHub SDK Example Source Code
web_fetch(url="https://raw.githubusercontent.com/HexRaysSA/ida-sdk/main/src/plugins/idapython/examples/ui/actions.py")
```
