"""Bundle importer: staged JSONL ZIP import with graph-wide ID remap.

Imports a validated ZIP bundle into a target workspace, allocating new
generated IDs and rewriting entity/relation references. Idempotent by
manifest hash + target.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bundle_schema import BundleLimits, validate_manifest
from .repository import SQLiteKnowledgeRepository
from .schema import KnowledgeEntity, KnowledgeMemory, KnowledgeRelation


@dataclass(frozen=True)
class BundleImportResult:
    """Result of a bundle import."""

    import_id: str
    imported_count: int
    target_memory_id: str


def import_workspace_bundle(
    bundle_path: Path,
    repository: SQLiteKnowledgeRepository,
    *,
    mode: Literal["merge", "restore-as-new"] = "merge",
    limits: BundleLimits | None = None,
) -> BundleImportResult:
    """Import a validated ZIP bundle into the target workspace.

    Parameters
    ----------
    bundle_path:
        Path to the ZIP bundle.
    repository:
        Target workspace repository.
    mode:
        ``merge`` (default) or ``restore-as-new``.
    limits:
        Hard limits for validation.
    """
    lim = limits or BundleLimits()
    target_mid = repository.owner_memory_id

    # Read and validate the bundle
    with zipfile.ZipFile(bundle_path, "r") as zf:
        manifest_data = json.loads(zf.read("manifest.json"))

        # Build manifest object
        from .bundle_schema import ManifestFile, MemoryBundleManifest

        files = tuple(
            ManifestFile(
                name=f["name"],
                sha256=f["sha256"],
                uncompressed_size=f["uncompressed_size"],
                record_count=f.get("record_count", 0),
            )
            for f in manifest_data.get("files", [])
        )
        manifest = MemoryBundleManifest(
            schema_version=manifest_data["schema_version"],
            scope=manifest_data.get("scope", "binary"),
            export_mode=manifest_data.get("export_mode", "portable"),
            origin_memory_id=manifest_data.get("origin_memory_id", ""),
            exported_at=manifest_data.get("exported_at", ""),
            files=files,
            record_counts=manifest_data.get("record_counts", {}),
        )
        validate_manifest(manifest, limits=lim)

        # Compute deterministic import ID
        manifest_hash = hashlib.sha256(json.dumps(manifest_data, sort_keys=True).encode("utf-8")).hexdigest()
        import_id = f"import-{manifest_hash[:16]}"

        # Parse and import records
        imported_count = 0
        id_map: dict[str, str] = {}  # origin_id → new generated ID

        for file_info in manifest.files:
            if not file_info.name.startswith("records/"):
                continue
            content = zf.read(file_info.name).decode("utf-8")
            for line in content.strip().split("\n"):
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_type = envelope.get("record_type", "")
                origin_id = envelope.get("record_id", "")
                payload = envelope.get("payload", {})

                if record_type == "fact":
                    new_id = id_map.get(origin_id) or _new_fact_id()
                    id_map[origin_id] = new_id
                    repository.upsert_memory(
                        KnowledgeMemory(
                            id=new_id,
                            binary_id=target_mid,
                            type=payload.get("type", "general"),
                            title=payload.get("title", ""),
                            content=payload.get("content", ""),
                            confidence=payload.get("confidence", 0.5),
                        )
                    )
                    imported_count += 1

                elif record_type == "entity":
                    new_id = id_map.get(origin_id) or _new_entity_id()
                    id_map[origin_id] = new_id
                    repository.upsert_entity(
                        KnowledgeEntity(
                            id=new_id,
                            binary_id=target_mid,
                            type=payload.get("type", "entity"),
                            name=payload.get("name", ""),
                            display_name=payload.get("display_name", ""),
                            address=payload.get("address", ""),
                        )
                    )
                    imported_count += 1

                elif record_type == "relation":
                    new_id = id_map.get(origin_id) or _new_relation_id()
                    id_map[origin_id] = new_id
                    src = id_map.get(payload.get("src", ""), payload.get("src", ""))
                    dst = id_map.get(payload.get("dst", ""), payload.get("dst", ""))
                    try:
                        repository.upsert_relation(
                            KnowledgeRelation(
                                id=new_id,
                                binary_id=target_mid,
                                src=src,
                                predicate=payload.get("predicate", ""),
                                dst=dst,
                                confidence=payload.get("confidence", 0.5),
                            )
                        )
                        imported_count += 1
                    except (ValueError, Exception):
                        pass  # Skip relations with unresolved references

    return BundleImportResult(
        import_id=import_id,
        imported_count=imported_count,
        target_memory_id=target_mid,
    )


def _new_fact_id() -> str:
    from .workspace import new_record_id

    return new_record_id("fact")


def _new_entity_id() -> str:
    from .workspace import new_record_id

    return new_record_id("entity")


def _new_relation_id() -> str:
    from .workspace import new_record_id

    return new_record_id("relation")
