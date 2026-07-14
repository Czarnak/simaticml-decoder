"""Analysis-only, atomic JSON manifest emitter for ``ProjectIndex``.

This module is the last stage of project-scale ingestion (Tasks 1-4 built
``project_model.py``'s immutable contracts, ``project_discovery.py``'s bounded
walk, ``project_xml.py``'s per-file V21 adapter, and ``project_index.py``'s
in-memory resolver). Given a fully-resolved ``ProjectIndex``, it serializes a
JSON-native manifest and writes it atomically.

Scope boundary: ``ArtifactRecord`` has no content-hash or byte-size field --
Tasks 1-4 never added one, and this task does not add one either. The only
SHA-256 anywhere in this codebase lives inside a diagnostic *message string*
for one UDT-parse-failure case in ``project_xml.py``, not as a structured
field. Recomputing a hash here would require reopening an artifact's file by
its stored relative path, which is exactly the TOCTOU reopen this plan's
earlier security review closed off (every artifact's bytes are read exactly
once, during discovery/adaptation -- see ``project_xml.py``'s module
docstring). So this manifest carries identity, status, location
(relative path + element_id), diagnostics, and reference edges -- nothing
else.

The manifest is analysis-only and never re-importable: ``output_contract``
declares this explicitly so downstream consumers cannot mistake the output
for a re-importable SimaticML project artifact.

Determinism: ``ProjectIndex.artifacts``/``edges``/``diagnostics`` are already
deterministically ordered by ``project_index.py``'s resolver. This module
preserves that order -- no re-sorting, no unordered ``dict``/``set`` in the
construction path -- so ``json.dumps(..., sort_keys=True)`` over the emitted
manifest is byte-identical for identical ``ProjectIndex`` values.
"""

from __future__ import annotations

import json
from pathlib import Path

from .project_model import (
    ArtifactRecord,
    ProjectDiagnostic,
    ProjectIndex,
    QualifiedIdentity,
    ReferenceEdge,
    SourceLocation,
)

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------- #
# JSON-native value builders                                                  #
# --------------------------------------------------------------------------- #


def _identity_to_dict(identity: QualifiedIdentity) -> dict[str, object]:
    return {
        "kind": identity.kind.value,
        "origin": identity.origin.value,
        "namespace": list(identity.namespace),
        "name": identity.name,
        "block_kind": identity.block_kind,
        "key": identity.key,
    }


def _location_to_dict(location: SourceLocation) -> dict[str, object]:
    return {
        "relative_path": location.relative_path.as_posix(),
        "element_id": location.element_id,
    }


def _diagnostic_to_dict(diagnostic: ProjectDiagnostic) -> dict[str, object]:
    return {
        "code": diagnostic.code.value,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "location": _location_to_dict(diagnostic.location),
    }


def _artifact_to_dict(record: ArtifactRecord) -> dict[str, object]:
    return {
        "identity": _identity_to_dict(record.identity),
        "status": record.status.value,
        "location": _location_to_dict(record.location),
        "diagnostics": [_diagnostic_to_dict(d) for d in record.diagnostics],
    }


def _edge_to_dict(edge: ReferenceEdge) -> dict[str, object]:
    return {
        "location": _location_to_dict(edge.location),
        "source": _identity_to_dict(edge.source),
        "target": _identity_to_dict(edge.target),
        "kind": edge.kind.value,
    }


# --------------------------------------------------------------------------- #
# Manifest emission                                                           #
# --------------------------------------------------------------------------- #


def emit_project_manifest(index: ProjectIndex) -> dict[str, object]:
    """Serialize a ``ProjectIndex`` into a JSON-native manifest dict.

    Never emits raw absolute paths, parser objects, or raw bytes: every
    value below is a plain ``str``/``int``/``bool``/``list``/``dict``/``None``.
    Iteration order over ``index.artifacts``/``index.edges``/
    ``index.diagnostics`` is preserved verbatim -- those tuples are already
    deterministically ordered by ``project_index.py``'s resolver.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "output_contract": {
            "fidelity": "analysis-only",
            "reimportable": False,
        },
        "artifacts": [_artifact_to_dict(record) for record in index.artifacts],
        "edges": [_edge_to_dict(edge) for edge in index.edges],
        "diagnostics": [_diagnostic_to_dict(d) for d in index.diagnostics],
    }


# --------------------------------------------------------------------------- #
# Atomic write                                                                #
# --------------------------------------------------------------------------- #


def write_project_manifest(index: ProjectIndex, destination: Path) -> Path:
    """Write the manifest for ``index`` to ``destination`` atomically.

    Writes the full payload to a ``.{name}.tmp`` sibling first, then
    ``Path.replace``s it onto ``destination`` -- a single filesystem rename,
    so a reader never observes a partially-written manifest and a failure
    partway through never leaves ``destination`` truncated or corrupted.

    A failure in ``temporary.replace(destination)`` propagates as a normal
    Python exception rather than being swallowed here: this function's own
    contract is only that ``destination`` is left untouched on failure (any
    previous complete manifest at that path survives unmodified), not that
    the exception is translated into a user-facing error -- that translation
    belongs to the CLI layer, not this module.
    """
    payload = (
        json.dumps(emit_project_manifest(index), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(destination)
    return destination
