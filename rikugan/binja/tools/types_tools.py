"""Type tools for Binary Ninja."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from ...core.errors import ToolError
from ...core.logging import log_debug
from ...tools.base import tool
from .compat import get_bn_module, parse_addr_like, require_bv, update_analysis_and_wait
from .fn_utils import get_function_at
from .type_utils import define_user_type, parse_type_string


def _named_types_map(bv: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    types_obj = getattr(bv, "types", None)
    if isinstance(types_obj, dict):
        for qname, t in types_obj.items():
            out[str(qname)] = t

    get_types = getattr(bv, "get_types", None)
    if callable(get_types):
        try:
            for qname, t in dict(get_types()).items():
                out[str(qname)] = t
        except Exception as e:
            log_debug(f"_named_types_map get_types failed: {e}")
    return out


def _get_type_by_name(bv: Any, name: str) -> Any:
    get_type = getattr(bv, "get_type_by_name", None)
    if callable(get_type):
        try:
            t = get_type(name)
            if t is not None:
                return t
        except Exception as e:
            log_debug(f"_get_type_by_name get_type_by_name failed for {name!r}: {e}")
    return _named_types_map(bv).get(name)


def _type_class_name(t: Any) -> str:
    tc = getattr(t, "type_class", None)
    if tc is None:
        tc = getattr(t, "typeClass", None)
    if tc is None:
        return ""
    name = getattr(tc, "name", None)
    if name:
        return str(name)
    return str(tc)


def _is_struct_type(t: Any) -> bool:
    cls_name = _type_class_name(t).lower()
    if "struct" in cls_name:
        return True
    return getattr(t, "structure", None) is not None


def _is_enum_type(t: Any) -> bool:
    cls_name = _type_class_name(t).lower()
    if "enum" in cls_name:
        return True
    return getattr(t, "enumeration", None) is not None


def _type_to_str(t: Any) -> str:
    if t is None:
        return "void"
    get_string = getattr(t, "get_string_before_name", None)
    if callable(get_string):
        try:
            s = get_string()
            if s:
                return str(s)
        except Exception as e:
            log_debug(f"_type_to_str get_string_before_name failed: {e}")
    return str(t)


def _sizeof_type(bv: Any, type_str: str, default: int = 4) -> int:
    try:
        t, _ = parse_type_string(bv, f"{type_str} __rikugan_tmp")
    except Exception:
        try:
            t, _ = parse_type_string(bv, type_str)
        except Exception:
            return default
    for attr in ("width", "size", "length"):
        v = getattr(t, attr, None)
        if isinstance(v, int) and v > 0:
            return int(v)
    return default


def _extract_types_dict(res: Any) -> dict[str, Any] | None:
    """Extract a ``{name: type}`` dict from whatever ``parse_types_from_*`` returns.

    Returns ``None`` when the format is not recognised so the caller can try
    the next API variant.
    """
    if res is None:
        return None

    # Legacy BN 3.x: (types_dict, variables, functions) tuple
    if isinstance(res, tuple) and res:
        first = res[0]
        if isinstance(first, dict):
            return {str(k): v for k, v in first.items()}

    # BN 4.x TypeParserResult: .types is a dict, list of (QualifiedName, Type) pairs,
    # or list of ParsedTypeInfo objects
    types_attr = getattr(res, "types", None)
    if types_attr is None:
        return None
    if isinstance(types_attr, dict):
        return {str(k): v for k, v in types_attr.items()}

    result: dict[str, Any] = {}
    for item in types_attr:
        if isinstance(item, tuple) and len(item) == 2:
            result[str(item[0])] = item[1]
        else:
            iname = getattr(item, "name", None)
            itype = getattr(item, "type", None)
            if iname is not None and itype is not None:
                result[str(iname)] = itype
    return result


def _parse_types_from_source(bv: Any, source: str) -> dict[str, Any]:
    """Parse C declarations into a {name: type} map.

    ``parse_types_from_string`` takes a C string and is tried first.
    ``parse_types_from_source`` takes a filename and is kept only as a
    last-resort fallback for older BN builds where the string variant may
    not exist.
    """
    for meth_name in (
        "parse_types_from_string",
        "parseTypesFromString",
        "parse_types_from_source",
        "parseTypesFromSource",
    ):
        meth = getattr(bv, meth_name, None)
        if not callable(meth):
            continue
        try:
            res = meth(source)
        except Exception as e:
            log_debug(f"_parse_types_from_source {meth_name} failed: {e}")
            continue

        parsed = _extract_types_dict(res)
        if parsed is not None:
            return parsed
        log_debug(f"_parse_types_from_source {meth_name} returned unrecognised format: {type(res)}")

    raise ToolError("Binary Ninja failed to parse C declarations")


def _define_types_from_source(bv: Any, source: str) -> dict[str, Any]:
    parsed = _parse_types_from_source(bv, source)
    defined: dict[str, Any] = {}
    for name, t in parsed.items():
        if define_user_type(bv, name, t):
            defined[name] = t
    if defined:
        update_analysis_and_wait(bv)
    return defined


def _extract_struct_members(t: Any) -> list[dict[str, Any]]:
    st = getattr(t, "structure", None) or t
    members = list(getattr(st, "members", []) or [])
    rows: list[dict[str, Any]] = []
    for m in members:
        off = int(getattr(m, "offset", 0))
        mname = str(getattr(m, "name", f"field_{off:x}"))
        mt = getattr(m, "type", None)
        msize = None
        if mt is not None:
            msize = getattr(mt, "width", None) or getattr(mt, "size", None)
        if not isinstance(msize, int) or msize <= 0:
            msize = 4
        rows.append(
            {
                "name": mname,
                "type": _type_to_str(mt),
                "offset": off,
                "size": int(msize),
                "comment": "",
            }
        )
    rows.sort(key=lambda x: int(x["offset"]))
    return rows


def _extract_enum_members(t: Any) -> list[tuple[str, int]]:
    enum_obj = getattr(t, "enumeration", None) or t
    members = list(getattr(enum_obj, "members", []) or [])
    out: list[tuple[str, int]] = []
    for m in members:
        name = str(getattr(m, "name", ""))
        value = getattr(m, "value", None)
        if isinstance(value, int):
            out.append((name, value))
    return out


def _build_struct_decl(name: str, fields: list[dict[str, Any]]) -> str:
    # Keep explicit offsets when present by inserting synthetic padding.
    explicit = all(isinstance(f.get("offset"), int) and int(f["offset"]) >= 0 for f in fields)
    ordered = sorted(fields, key=lambda x: int(x.get("offset", 0))) if explicit else list(fields)
    lines = [f"struct {name} {{"]
    cur = 0
    for f in ordered:
        fname = f["name"]
        ftype = f.get("type", "int")
        off = int(f.get("offset", cur if explicit else -1))
        size = int(f.get("size", 4) or 4)
        if explicit and off > cur:
            lines.append(f"    char _pad_{cur:x}[{off - cur}];")
            cur = off
        lines.append(f"    {ftype} {fname};")
        cur = max(cur, off + max(1, size)) if explicit else cur + max(1, size)
    lines.append("};")
    return "\n".join(lines)


def _parse_field_type(bv: Any, ftype_str: str) -> Any:
    """Parse a field type string, trying with a dummy variable name if needed."""
    # Try with a dummy variable name first (BN often requires a declaration)
    last_err: Exception | None = None
    for src in (f"{ftype_str} __rikugan_tmp", ftype_str):
        try:
            t, _ = parse_type_string(bv, src)
            return t
        except Exception as exc:
            last_err = exc
            continue
    if last_err is not None:
        log_debug(f"_parse_field_type: could not parse {ftype_str!r}: {last_err}")
    return None


def _redefine_struct_with_builder(bv: Any, name: str, fields: list[dict[str, Any]]) -> bool:
    """Build a struct using BN's StructureBuilder API (reliable, version-agnostic)."""
    bn = get_bn_module()
    if bn is None:
        return False
    try:
        sb_cls = getattr(bn, "StructureBuilder", None)
        if sb_cls is None:
            return False
        sb = sb_cls.create()
        added = 0
        for f in fields:
            fname = f["name"]
            ftype_str = f.get("type", "int")
            off = f.get("offset")
            ftype = _parse_field_type(bv, ftype_str)
            if ftype is None:
                log_debug(
                    f"_redefine_struct_with_builder: skipping field {fname!r}, could not parse type {ftype_str!r}"
                )
                continue
            if isinstance(off, int) and off >= 0:
                insert = getattr(sb, "insert", None)
                if callable(insert):
                    insert(off, ftype, fname)
                    added += 1
                    continue
            append = getattr(sb, "append", None)
            if callable(append):
                append(ftype, fname)
                added += 1
        if added == 0:
            log_debug("_redefine_struct_with_builder: no fields added, skipping define")
            return False
        struct_type_fn = getattr(bn, "Type", None)
        if struct_type_fn is not None:
            struct_type_fn = getattr(struct_type_fn, "structure_type", None)
        if callable(struct_type_fn):
            struct_type = struct_type_fn(sb)
        else:
            struct_type = sb.immutable_copy() if hasattr(sb, "immutable_copy") else sb
        ok = define_user_type(bv, name, struct_type)
        if ok:
            update_analysis_and_wait(bv)
        return ok
    except Exception as e:
        log_debug(f"_redefine_struct_with_builder failed: {e}")
        return False


def _redefine_struct(bv: Any, name: str, fields: list[dict[str, Any]]) -> bool:
    # Primary: use StructureBuilder directly — reliably adds fields across BN versions.
    if _redefine_struct_with_builder(bv, name, fields):
        # Verify fields were registered; fall through to C-parse path if empty.
        t = _get_type_by_name(bv, name)
        if t is not None and _extract_struct_members(t):
            return True
        log_debug("_redefine_struct_with_builder produced empty struct, trying C-parse path")

    # Fallback: parse C declaration and register via define_user_type.
    decl = _build_struct_decl(name, fields)
    log_debug(f"_redefine_struct C-parse decl:\n{decl}")
    parsed = _define_types_from_source(bv, decl)
    log_debug(f"_redefine_struct parsed keys: {list(parsed.keys())}")
    # BN may return the key as "Foo" or "struct Foo" depending on version
    return name in parsed or f"struct {name}" in parsed


@tool(category="types", mutating=True)
def create_struct(
    name: Annotated[str, "Struct name"],
    fields: Annotated[str, "JSON array of fields: [{name, type, offset?, comment?}, ...]"],
) -> str:
    """Create a new struct with typed fields."""
    bv = require_bv()
    if _get_type_by_name(bv, name) is not None:
        return f"Struct '{name}' already exists"

    try:
        field_list = json.loads(fields)
        if not isinstance(field_list, list):
            return "fields must be a JSON array"
    except Exception as e:
        return f"Invalid fields JSON: {e}"

    normalized: list[dict[str, Any]] = []
    cur = 0
    for fld in field_list:
        if not isinstance(fld, dict) or "name" not in fld:
            continue
        ftype = str(fld.get("type", "int"))
        size = _sizeof_type(bv, ftype, default=4)
        off = fld.get("offset", cur)
        if not isinstance(off, int):
            off = cur
        normalized.append(
            {
                "name": str(fld["name"]),
                "type": ftype,
                "offset": int(off),
                "size": int(size),
                "comment": str(fld.get("comment", "")),
            }
        )
        cur = max(cur, int(off) + int(size))

    if not normalized:
        return "No valid fields provided"

    if _redefine_struct(bv, name, normalized):
        t = _get_type_by_name(bv, name)
        members = _extract_struct_members(t) if t is not None else normalized
        return f"Created struct '{name}' with {len(members)} fields"
    return f"Failed to create struct '{name}'"


@tool(category="types", mutating=True)
def modify_struct(
    name: Annotated[str, "Struct name"],
    action: Annotated[
        str,
        "Action: add_field, remove_field, rename_field, retype_field, set_field_comment, resize",
    ],
    field_name: Annotated[str, "Field name to modify"] = "",
    new_name: Annotated[str, "New name (for rename_field)"] = "",
    field_type: Annotated[str, "Type string (for add_field/retype_field)"] = "int",
    offset: Annotated[int, "Offset (for add_field)"] = -1,
    comment: Annotated[str, "Comment text (for set_field_comment)"] = "",
    new_size: Annotated[int, "New struct size (for resize)"] = 0,
) -> str:
    """Modify an existing struct: add/remove/rename/retype fields."""
    bv = require_bv()
    t = _get_type_by_name(bv, name)
    if t is None or not _is_struct_type(t):
        return f"Struct '{name}' not found"

    members = _extract_struct_members(t)
    if action == "add_field":
        if not field_name:
            return "field_name is required"
        size = _sizeof_type(bv, field_type, default=4)
        if offset >= 0:
            off = int(offset)
        elif members:
            last = max(members, key=lambda x: int(x["offset"]) + int(x["size"]))
            off = int(last["offset"]) + int(last["size"])
        else:
            off = 0
        members.append(
            {
                "name": field_name,
                "type": field_type,
                "offset": off,
                "size": size,
                "comment": comment,
            }
        )
        ok = _redefine_struct(bv, name, members)
        return f"Added field '{field_name}' ({field_type}) to '{name}'" if ok else "Failed to add field"

    if action == "remove_field":
        new_members = [m for m in members if m["name"] != field_name]
        if len(new_members) == len(members):
            return f"Field '{field_name}' not found in '{name}'"
        ok = _redefine_struct(bv, name, new_members)
        return f"Removed field '{field_name}' from '{name}'" if ok else "Remove failed"

    if action == "rename_field":
        found = False
        for m in members:
            if m["name"] == field_name:
                m["name"] = new_name
                found = True
                break
        if not found:
            return f"Field '{field_name}' not found"
        ok = _redefine_struct(bv, name, members)
        return f"Renamed '{field_name}' \u2192 '{new_name}'" if ok else "Rename failed"

    if action == "retype_field":
        found = False
        for m in members:
            if m["name"] == field_name:
                m["type"] = field_type
                m["size"] = _sizeof_type(bv, field_type, default=4)
                found = True
                break
        if not found:
            return f"Field '{field_name}' not found"
        ok = _redefine_struct(bv, name, members)
        return f"Retyped '{field_name}' to '{field_type}'" if ok else "Retype failed"

    if action == "set_field_comment":
        # Binary Ninja type members do not expose stable per-field comments in all APIs.
        if any(m["name"] == field_name for m in members):
            _ = comment
            return "Field comments are not persisted in this Binary Ninja API; no-op"
        return f"Field '{field_name}' not found"

    if action == "resize":
        if new_size <= 0:
            return "New size must be positive"
        current = 0
        if members:
            current = max(int(m["offset"]) + int(m["size"]) for m in members)
        if new_size < current:
            return f"Cannot shrink struct (current={current}, requested={new_size})"
        if new_size == current:
            return f"Struct '{name}' already size {current}"
        members.append(
            {
                "name": f"_pad_end_{current:x}",
                "type": f"char[{new_size - current}]",
                "offset": current,
                "size": new_size - current,
                "comment": "",
            }
        )
        ok = _redefine_struct(bv, name, members)
        return f"Resized '{name}' from {current} to {new_size}" if ok else "Resize failed"

    return f"Unknown action: {action}"


@tool(category="types")
def get_struct_info(name: Annotated[str, "Struct name"]) -> str:
    """Get full struct layout: fields, types, offsets, sizes."""
    bv = require_bv()
    t = _get_type_by_name(bv, name)
    if t is None or not _is_struct_type(t):
        return f"Struct '{name}' not found"

    members = _extract_struct_members(t)
    size = 0
    if members:
        size = max(int(m["offset"]) + int(m["size"]) for m in members)
    lines = [
        f"Struct: {name}",
        f"Size: {size} (0x{size:x})",
        f"Members: {len(members)}",
        "",
    ]
    for m in members:
        lines.append(f"  +0x{int(m['offset']):04x}  {m['type']!s:24s} {m['name']!s:24s} ({int(m['size'])} bytes)")
    return "\n".join(lines)


@tool(category="types")
def list_structs(
    filter: Annotated[str, "Name filter (substring match)"] = "",
) -> str:
    """List all structs in the database."""
    bv = require_bv()
    lines = ["Structs:"]
    count = 0
    q = filter.lower()
    for name, t in sorted(_named_types_map(bv).items()):
        if not _is_struct_type(t):
            continue
        if q and q not in name.lower():
            continue
        members = _extract_struct_members(t)
        size = max((int(m["offset"]) + int(m["size"]) for m in members), default=0)
        lines.append(f"  {name:40s} size={size}")
        count += 1
        if count >= 200:
            lines.append("  ... (truncated)")
            break
    if count == 0:
        lines.append("  (none)")
    return "\n".join(lines)


@tool(category="types", mutating=True)
def create_enum(
    name: Annotated[str, "Enum name"],
    members: Annotated[str, "JSON array of members: [{name, value}, ...]"],
    bitfield: Annotated[bool, "Create as bitfield enum"] = False,
) -> str:
    """Create a new enum with name/value pairs."""
    bv = require_bv()
    if _get_type_by_name(bv, name) is not None:
        return f"Enum '{name}' already exists"

    try:
        member_list = json.loads(members)
        if not isinstance(member_list, list):
            return "members must be a JSON array"
    except Exception as e:
        return f"Invalid members JSON: {e}"

    lines = [f"enum {name} {{"]
    for i, m in enumerate(member_list):
        mname = str(m.get("name", f"MEMBER_{i}"))
        mval = int(m.get("value", i))
        comma = "," if i + 1 < len(member_list) else ""
        lines.append(f"    {mname} = {mval}{comma}")
    lines.append("};")
    if bitfield:
        lines.append(f"typedef enum {name} {name};")

    try:
        parsed = _define_types_from_source(bv, "\n".join(lines))
    except Exception as e:
        return f"Failed to create enum '{name}': {e}"
    return (
        f"Created enum '{name}' with {len(member_list)} members"
        if name in parsed
        else f"Failed to create enum '{name}'"
    )


@tool(category="types", mutating=True)
def modify_enum(
    name: Annotated[str, "Enum name"],
    action: Annotated[str, "Action: add_member, remove_member, rename_member"],
    member_name: Annotated[str, "Member name"] = "",
    new_name: Annotated[str, "New name (for rename)"] = "",
    value: Annotated[int, "Value (for add_member)"] = 0,
) -> str:
    """Modify an existing enum."""
    bv = require_bv()
    t = _get_type_by_name(bv, name)
    if t is None or not _is_enum_type(t):
        return f"Enum '{name}' not found"

    members = _extract_enum_members(t)
    if action == "add_member":
        members.append((member_name, int(value)))
    elif action == "remove_member":
        old_len = len(members)
        members = [m for m in members if m[0] != member_name]
        if len(members) == old_len:
            return f"Member '{member_name}' not found"
    elif action == "rename_member":
        changed = False
        new_members = []
        for mn, mv in members:
            if mn == member_name:
                new_members.append((new_name, mv))
                changed = True
            else:
                new_members.append((mn, mv))
        members = new_members
        if not changed:
            return f"Member '{member_name}' not found"
    else:
        return f"Unknown action: {action}"

    lines = [f"enum {name} {{"]
    for i, (mn, mv) in enumerate(members):
        comma = "," if i + 1 < len(members) else ""
        lines.append(f"    {mn} = {mv}{comma}")
    lines.append("};")
    try:
        _define_types_from_source(bv, "\n".join(lines))
    except Exception as e:
        return f"Failed to modify enum '{name}': {e}"

    if action == "add_member":
        return f"Added '{member_name}' = {value}"
    if action == "remove_member":
        return f"Removed '{member_name}'"
    return f"Renamed '{member_name}' \u2192 '{new_name}'"


@tool(category="types")
def get_enum_info(name: Annotated[str, "Enum name"]) -> str:
    """Get all enum members with values."""
    bv = require_bv()
    t = _get_type_by_name(bv, name)
    if t is None or not _is_enum_type(t):
        return f"Enum '{name}' not found"

    members = _extract_enum_members(t)
    lines = [f"Enum: {name}", ""]
    if not members:
        lines.append("  (no members)")
    for mn, mv in members:
        lines.append(f"  {mn:40s} = 0x{mv:x} ({mv})")
    return "\n".join(lines)


@tool(category="types")
def list_enums(
    filter: Annotated[str, "Name filter (substring match)"] = "",
) -> str:
    """List all enums in the database."""
    bv = require_bv()
    lines = ["Enums:"]
    count = 0
    q = filter.lower()
    for name, t in sorted(_named_types_map(bv).items()):
        if not _is_enum_type(t):
            continue
        if q and q not in name.lower():
            continue
        members = _extract_enum_members(t)
        lines.append(f"  {name:40s} ({len(members)} members)")
        count += 1
        if count >= 200:
            lines.append("  ... (truncated)")
            break
    if count == 0:
        lines.append("  (none)")
    return "\n".join(lines)


@tool(category="types", mutating=True)
def create_typedef(
    name: Annotated[str, "New type alias name"],
    base_type: Annotated[str, "Base type (e.g. 'unsigned int', 'DWORD')"],
) -> str:
    """Create a type alias (typedef)."""
    bv = require_bv()
    decl = f"typedef {base_type} {name};"
    try:
        parsed = _define_types_from_source(bv, decl)
    except Exception as e:
        return f"Failed to create typedef: {decl} ({e})"
    return f"Created typedef: {decl}" if name in parsed else f"Failed to create typedef: {decl}"


@tool(category="types", mutating=True)
def apply_struct_to_address(
    struct_name: Annotated[str, "Struct name to apply"],
    address: Annotated[str, "Data address (hex string)"],
) -> str:
    """Apply a struct type at a data address."""
    bv = require_bv()
    ea = parse_addr_like(address)
    t = _get_type_by_name(bv, struct_name)
    if t is None or not _is_struct_type(t):
        return f"Struct '{struct_name}' not found"

    for meth_name in ("define_user_data_var", "defineUserDataVar"):
        meth = getattr(bv, meth_name, None)
        if callable(meth):
            try:
                meth(ea, t)
                return f"Applied struct '{struct_name}' at 0x{ea:x}"
            except Exception as e:
                log_debug(f"apply_struct_to_address {meth_name} failed at 0x{ea:x}: {e}")
    return f"Failed to apply struct at 0x{ea:x}"


@tool(category="types", mutating=True)
def apply_type_to_variable(
    func_address: Annotated[str, "Function address (hex string)"],
    var_name: Annotated[str, "Variable name in the decompiler"],
    type_str: Annotated[str, "C type string to apply"],
) -> str:
    """Retype a local variable in a function."""
    bv = require_bv()
    ea = parse_addr_like(func_address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    try:
        tif, _ = parse_type_string(bv, f"{type_str} __rikugan_var")
    except Exception:
        try:
            tif, _ = parse_type_string(bv, type_str)
        except Exception as e:
            return f"Failed to parse type: {e}"

    vars_obj = getattr(func, "vars", None)
    if vars_obj is None:
        return "Variable typing is unavailable for this function"

    target = None
    for lv in list(vars_obj):
        if getattr(lv, "name", None) == var_name:
            target = lv
            break
    if target is None:
        return f"Variable '{var_name}' not found in 0x{int(getattr(func, 'start', ea)):x}"

    for meth_name in ("set_user_var_type", "setUserVarType"):
        meth = getattr(func, meth_name, None)
        if callable(meth):
            try:
                meth(target, tif)
                return f"Set type of '{var_name}' to '{type_str}'"
            except Exception as e:
                log_debug(f"apply_type_to_variable {meth_name} failed for {var_name!r}: {e}")

    for meth_name in ("create_user_var", "createUserVar"):
        meth = getattr(func, meth_name, None)
        if callable(meth):
            try:
                meth(target, tif, var_name)
                return f"Set type of '{var_name}' to '{type_str}'"
            except Exception as e:
                log_debug(f"apply_type_to_variable {meth_name} failed for {var_name!r}: {e}")

    return f"Failed to set type on '{var_name}'"


@tool(category="types", mutating=True)
def set_function_prototype(
    address: Annotated[str, "Function address (hex string)"],
    prototype: Annotated[str, "Full C prototype (e.g. 'int __fastcall foo(void* ctx, int len)')"],
) -> str:
    """Set a function's full calling convention and prototype."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    try:
        t, _name = parse_type_string(bv, prototype)
    except Exception as e:
        return f"Failed to set prototype. Check syntax: {prototype} ({e})"

    for meth_name in ("set_user_type", "setUserType"):
        meth = getattr(func, meth_name, None)
        if callable(meth):
            try:
                meth(t)
                return f"Set prototype at 0x{int(getattr(func, 'start', ea)):x}: {prototype}"
            except Exception as e:
                log_debug(f"set_function_prototype {meth_name} failed at 0x{ea:x}: {e}")
    try:
        func.type = t
        return f"Set prototype at 0x{int(getattr(func, 'start', ea)):x}: {prototype}"
    except Exception as e:
        log_debug(f"set_function_prototype setattr failed at 0x{ea:x}: {e}")
        return f"Failed to set prototype. Check syntax: {prototype}"


@tool(category="types", mutating=True)
def import_c_header(
    c_code: Annotated[str, "C header code containing struct/enum/typedef definitions"],
) -> str:
    """Parse C header code and define all structs/enums/typedefs found."""
    bv = require_bv()
    try:
        parsed = _define_types_from_source(bv, c_code)
    except Exception as e:
        return f"Failed to parse C declarations. {e}"
    return f"Successfully parsed C declarations ({len(parsed)} type(s) defined)"


@tool(category="types", requires_decompiler=True)
def suggest_struct_from_accesses(
    address: Annotated[str, "Function or pointer address to analyze (hex string)"],
) -> str:
    """Analyze access patterns and suggest a struct layout."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    hlil = getattr(func, "hlil", None)
    if hlil is None:
        return "HLIL not available for this function"

    pattern = re.compile(r"\+\s*0x([0-9a-fA-F]+)")
    offsets: dict[int, int] = {}
    instructions = list(getattr(hlil, "instructions", []) or [])
    for ins in instructions:
        text = str(ins)
        for m in pattern.finditer(text):
            off = int(m.group(1), 16)
            offsets[off] = offsets.get(off, 0) + 1

    if not offsets:
        return "No pointer field accesses detected in this function"

    lines = [
        f"Suggested struct from access analysis at 0x{int(getattr(func, 'start', ea)):x}:",
        "",
    ]
    for off, count in sorted(offsets.items()):
        lines.append(f"  +0x{off:04x}  uint32_t         field_{off:x};    // accessed {count}x")
    est_size = max(offsets.keys()) + 4
    lines.append(f"\nEstimated struct size: {est_size} (0x{est_size:x}) bytes")
    lines.append("\nSuggested C declaration:")
    lines.append(f"struct auto_struct_{ea:x} {{")
    for off in sorted(offsets.keys()):
        lines.append(f"    uint32_t field_{off:x};")
    lines.append("};")
    return "\n".join(lines)


@tool(category="types", mutating=True)
def propagate_type(
    struct_name: Annotated[str, "Struct name to propagate"],
    field_index: Annotated[int, "Specific field index to propagate (-1 for all)"] = -1,
) -> str:
    """Re-run analysis after struct changes to update references."""
    bv = require_bv()
    t = _get_type_by_name(bv, struct_name)
    if t is None or not _is_struct_type(t):
        return f"Struct '{struct_name}' not found"
    _ = field_index
    update_analysis_and_wait(bv)
    return f"Triggered type propagation for '{struct_name}'"


@tool(category="types")
def get_type_libraries() -> str:
    """List loaded type libraries."""
    bv = require_bv()
    lines = ["Type libraries:"]

    platform = getattr(bv, "platform", None)
    libs = getattr(platform, "type_libraries", None) if platform is not None else None
    count = 0
    if libs:
        if isinstance(libs, dict):
            for name, lib in libs.items():
                desc = getattr(lib, "description", "")
                lines.append(f"  {name}" + (f" - {desc}" if desc else ""))
                count += 1
        else:
            for lib in list(libs):
                name = getattr(lib, "name", None) or str(lib)
                desc = getattr(lib, "description", "")
                lines.append(f"  {name}" + (f" - {desc}" if desc else ""))
                count += 1

    if count == 0:
        lines.append("  (none)")
    return "\n".join(lines)


@tool(category="types", mutating=True)
def import_type_from_library(
    til_name: Annotated[str, "Type library name"],
    type_name: Annotated[str, "Type name to import"],
) -> str:
    """Import a specific type from a loaded type library."""
    bv = require_bv()
    if _get_type_by_name(bv, type_name) is not None:
        return f"Type '{type_name}' already exists locally"

    platform = getattr(bv, "platform", None)
    libs = getattr(platform, "type_libraries", None) if platform is not None else None
    if not libs:
        return f"Type library '{til_name}' not found"

    candidates = []
    if isinstance(libs, dict):
        for key, lib in libs.items():
            lname = str(getattr(lib, "name", key))
            if lname == til_name or str(key) == til_name:
                candidates.append(lib)
    else:
        for lib in list(libs):
            lname = str(getattr(lib, "name", lib))
            if lname == til_name:
                candidates.append(lib)

    if not candidates:
        return f"Type library '{til_name}' not found"

    for lib in candidates:
        for meth_name in ("get_named_type", "getNamedType"):
            meth = getattr(lib, meth_name, None)
            if callable(meth):
                try:
                    t = meth(type_name)
                except Exception as e:
                    log_debug(f"import_type_from_library {meth_name} failed for {type_name!r}: {e}")
                    t = None
                if t is not None and define_user_type(bv, type_name, t):
                    return f"Imported '{type_name}' from '{til_name}'"

    # Fallback: attempt parser include from library name in a typedef import line.
    try:
        parsed = _define_types_from_source(bv, f"typedef {type_name} {type_name};")
    except Exception as e:
        log_debug(f"import_type_from_library fallback parse failed for {type_name!r}: {e}")
        parsed = {}
    if type_name in parsed:
        return f"Imported '{type_name}' from '{til_name}'"

    return f"Type '{type_name}' not found in '{til_name}'"
