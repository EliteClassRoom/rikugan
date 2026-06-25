"""Skill discovery and loading from the Rikugan skills directory."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import SkillError
from ..core.logging import log_debug, log_error

# ---------------------------------------------------------------------------
# Minimal frontmatter parser (no PyYAML dependency)
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse YAML-like frontmatter between --- markers.

    Supports:
      key: value              → str
      key: [a, b, c]          → list (inline)
      key:                     → list (block)
        - item1
        - item2
      key:                     → dict (nested key-value)
        subkey: value
        subkey2: value2
    """
    result: dict[str, Any] = {}
    lines = text.strip().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip blank lines and comments
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue

        # key: value
        m = re.match(r"^(\w[\w\-]*)\s*:\s*(.*)", line)
        if not m:
            i += 1
            continue

        key = m.group(1).strip()
        value_part = m.group(2).strip()

        if value_part:
            # Inline list: [a, b, c]
            if value_part.startswith("[") and value_part.endswith("]"):
                inner = value_part[1:-1]
                items = [s.strip().strip("\"'") for s in inner.split(",") if s.strip()]
                result[key] = items
            else:
                # Scalar — strip surrounding quotes
                result[key] = value_part.strip("\"'")
        else:
            # Check for block list (next lines starting with "  - ")
            # or nested dict (next lines starting with "  key: value")
            block_items: list[str] = []
            nested_dict: dict[str, str] = {}
            j = i + 1
            while j < len(lines):
                bline = lines[j]
                # Skip comments inside a block (consistent with top-level parsing)
                if bline.strip().startswith("#"):
                    j += 1
                    continue
                # Block list item
                bm = re.match(r"^\s+-\s+(.*)", bline)
                if bm:
                    block_items.append(bm.group(1).strip().strip("\"'"))
                    j += 1
                    continue
                # Nested key-value pair (indented)
                nm = re.match(r"^\s+(\w[\w\-]*)\s*:\s+(.*)", bline)
                if nm:
                    nested_dict[nm.group(1).strip()] = nm.group(2).strip().strip("\"'")
                    j += 1
                    continue
                if not bline.strip():
                    j += 1
                    continue
                break
            if block_items:
                result[key] = block_items
                i = j
                continue
            elif nested_dict:
                result[key] = nested_dict
                i = j
                continue
            else:
                result[key] = ""

        i += 1

    return result


def _split_frontmatter(text: str) -> tuple:
    """Split a SKILL.md into (frontmatter_text, body_text).

    Returns ("", text) if no frontmatter markers found.
    """
    stripped = text.lstrip("\ufeff\n")  # strip BOM (if present) + leading newlines
    if not stripped.startswith("---"):
        return ("", text)

    # Find closing ---
    rest = stripped[3:].lstrip("\n")
    idx = rest.find("\n---")
    if idx == -1:
        return ("", text)

    fm_text = rest[:idx]
    body = rest[idx + 4 :]  # skip past "\n---"
    return (fm_text, body.lstrip("\n"))


def _read_frontmatter_only(md_path: str) -> str:
    """Read only the YAML frontmatter block (up to the closing ``---``) from *md_path*.

    Stops reading once the closing marker is found, avoiding loading the
    entire body text and reference files during discovery.  Returns the
    raw frontmatter text (without the opening ``---``) or ``""`` if no
    frontmatter is found.

    Tolerates leading blank lines and BOM characters so that
    indented/commented frontmatter still parses correctly.
    """
    try:
        with open(md_path, encoding="utf-8-sig") as f:
            # Skip leading blank lines and BOM characters
            line = f.readline()
            while line and line.lstrip("\ufeff").strip() == "":
                line = f.readline()
            if not line:
                return ""
            if not line.lstrip("\ufeff").startswith("---"):
                return ""
            lines: list[str] = []
            for line in f:
                if line.strip() == "---":
                    return "\n".join(lines)
                lines.append(line.rstrip("\r\n"))
    except OSError as e:
        log_debug(f"Failed to read skill frontmatter {md_path}: {e}")
    return ""


# ---------------------------------------------------------------------------
# SkillDefinition
# ---------------------------------------------------------------------------


@dataclass
class SkillDefinition:
    """A loaded skill from the Rikugan skills directory<slug>/SKILL.md."""

    name: str
    description: str
    directory: str
    allowed_tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    mode: str = ""  # e.g. "exploration" to trigger exploration mode
    author: str = ""
    version: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    _body: str | None = field(default=None, repr=False)
    _md_path: str = field(default="", repr=False)

    @property
    def slug(self) -> str:
        """Slug = directory basename, used as /slug invocation."""
        return os.path.basename(self.directory)

    @property
    def body(self) -> str:
        """Lazy-load the body text on first access."""
        if self._body is None:
            self._body = _load_body(self._md_path)
        return self._body


def _load_body(md_path: str) -> str:
    """Read the body (everything after frontmatter) from a SKILL.md file."""
    try:
        with open(md_path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        raise SkillError(f"Cannot read skill file {md_path}: {e}") from e

    _fm, body = _split_frontmatter(text)
    body = body.strip()

    # Append reference files from <skill>/references/ if they exist
    refs = _load_references(os.path.dirname(md_path))
    if refs:
        body += "\n\n" + refs

    return body


def _load_references(skill_dir: str) -> str:
    """Load .md files from <skill>/references/ and concatenate them.

    Also loads host-specific references from <skill>/references/ida/ depending on the active host, so generic
    skills can ship separate reference docs per tool without injecting
    both into the context.
    """
    from ..core.host import HOST_IDA, host_kind

    refs_dir = os.path.join(skill_dir, "references")
    if not os.path.isdir(refs_dir):
        return ""

    _HOST_SUBDIR = {HOST_IDA: "ida"}

    parts: list[str] = []

    def _load_dir(directory: str) -> None:
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(directory, fname)
            try:
                with open(fpath, encoding="utf-8-sig") as f:
                    content = f.read().strip()
                if content:
                    parts.append(f"## Reference: {fname}\n{content}")
                    log_debug(f"Loaded skill reference: {fpath}")
            except OSError as e:
                log_error(f"Failed to load skill reference {fpath}: {e}")

    # Flat references — always loaded
    _load_dir(refs_dir)

    # Host-specific subdirectory — only the active host's folder is loaded
    host_subdir = _HOST_SUBDIR.get(host_kind())
    if host_subdir:
        host_refs_dir = os.path.join(refs_dir, host_subdir)
        if os.path.isdir(host_refs_dir):
            _load_dir(host_refs_dir)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_skills(skills_dir: str) -> list[SkillDefinition]:
    """Scan skills_dir for <slug>/SKILL.md, return loaded SkillDefinitions.

    Each subdirectory with a SKILL.md is treated as a skill.
    **Only frontmatter metadata is loaded eagerly.**  The body text and
    reference files are loaded lazily on first access via ``SkillDefinition.body``.

    This avoids reading potentially large reference files (*.md) during
    discovery, which runs in the background runtime init thread on panel boot.
    """
    if not os.path.isdir(skills_dir):
        log_debug(f"Skills directory not found: {skills_dir}")
        return []

    skills: list[SkillDefinition] = []

    for entry in sorted(os.listdir(skills_dir)):
        skill_dir = os.path.join(skills_dir, entry)
        md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(md_path):
            continue

        try:
            # Read only frontmatter during discovery — the body is loaded
            # lazily on first access via SkillDefinition.body.
            fm_text = _read_frontmatter_only(md_path)
            fm = _parse_frontmatter(fm_text) if fm_text else {}

            # Extract author/version from top-level or nested metadata
            meta = fm.get("metadata", {})
            author = fm.get("author", "")
            version = fm.get("version", "")
            if isinstance(meta, dict):
                author = author or meta.get("author", "")
                version = version or meta.get("version", "")

            # Parse triggers — list of keywords that auto-activate this skill
            raw_triggers = fm.get("triggers", [])
            if isinstance(raw_triggers, str):
                raw_triggers = [t.strip() for t in raw_triggers.split(",") if t.strip()]
            triggers = [t.lower() for t in raw_triggers]

            skill = SkillDefinition(
                name=fm.get("name", entry),
                description=fm.get("description", ""),
                directory=skill_dir,
                allowed_tools=fm.get("allowed_tools", []),
                tags=fm.get("tags", []),
                triggers=triggers,
                mode=fm.get("mode", ""),
                author=author,
                version=version,
                frontmatter=fm,
                _body=None,  # lazy — loaded on first access via SkillDefinition.body
                _md_path=md_path,
            )

            skills.append(skill)
            log_debug(f"Discovered skill: /{entry} — {skill.description or '(no description)'}")

        except (OSError, ValueError, KeyError) as e:
            log_error(f"Failed to load skill from {md_path}: {e}")

    return skills
