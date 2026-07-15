"""Tests for the analysis-only, atomic project manifest emitter (project_emit.py).

Builds ``ProjectIndex`` fixtures directly out of model pieces (never via
``index_project_artifacts``) so every scenario here is isolated to
``emit_project_manifest``'s / ``write_project_manifest``'s own serialization
and atomic-write behavior, mirroring how ``tests/test_project_index.py``
isolates the resolver from real XML parsing.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from simaticml_decoder.project_emit import emit_project_manifest, write_project_manifest
from simaticml_decoder.project_model import (
    ArtifactKind,
    ArtifactOrigin,
    ArtifactRecord,
    ArtifactStatus,
    DiagnosticCode,
    ProjectDiagnostic,
    ProjectIndex,
    QualifiedIdentity,
    ReferenceEdge,
    SourceLocation,
)

# --------------------------------------------------------------------------- #
# Fixture builders                                                             #
# --------------------------------------------------------------------------- #


def _identity(
    kind: ArtifactKind,
    origin: ArtifactOrigin,
    name: str,
    block_kind: str | None = None,
    namespace: tuple[str, ...] = (),
) -> QualifiedIdentity:
    return QualifiedIdentity(
        kind=kind, origin=origin, namespace=namespace, name=name, block_kind=block_kind
    )


def _location(path: str, element_id: str | None = None) -> SourceLocation:
    return SourceLocation(PurePosixPath(path), element_id)


def _record(
    identity: QualifiedIdentity,
    path: str,
    status: ArtifactStatus = ArtifactStatus.COMPLETE,
    diagnostics: tuple[ProjectDiagnostic, ...] = (),
) -> ArtifactRecord:
    return ArtifactRecord(
        identity=identity, status=status, location=_location(path), diagnostics=diagnostics
    )


def _project_index() -> ProjectIndex:
    """A minimal single-artifact index, used by the brief's Step 1 test."""
    identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller", "FC")
    return ProjectIndex(artifacts=(_record(identity, "PLC_1/Caller.xml"),))


# --------------------------------------------------------------------------- #
# Given by the brief: output contract + no absolute paths                     #
# --------------------------------------------------------------------------- #


def test_manifest_has_no_absolute_paths_and_declares_output_contract(tmp_path):
    manifest = emit_project_manifest(_project_index())

    encoded = json.dumps(manifest, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert manifest["output_contract"] == {
        "fidelity": "analysis-only",
        "reimportable": False,
    }
    assert manifest["schema_version"] == 1


# --------------------------------------------------------------------------- #
# Artifact diagnostics serialize                                              #
# --------------------------------------------------------------------------- #


def test_artifact_with_diagnostics_serializes_status_and_diagnostics():
    identity = _identity(ArtifactKind.UDT, ArtifactOrigin.PROJECT_LIBRARY, "Broken")
    diagnostic = ProjectDiagnostic(
        code=DiagnosticCode.MALFORMED_XML,
        severity="error",
        message="could not parse UDT body",
        location=_location("Types/UDTs/Broken.xml"),
    )
    record = _record(
        identity,
        "Types/UDTs/Broken.xml",
        status=ArtifactStatus.FAILED,
        diagnostics=(diagnostic,),
    )
    index = ProjectIndex(artifacts=(record,))

    manifest = emit_project_manifest(index)

    assert len(manifest["artifacts"]) == 1
    artifact = manifest["artifacts"][0]
    assert artifact["status"] == "failed"
    assert artifact["identity"] == {
        "kind": "udt",
        "origin": "project-library",
        "namespace": [],
        "name": "Broken",
        "block_kind": None,
        "key": identity.key,
    }
    assert artifact["location"] == {
        "relative_path": "Types/UDTs/Broken.xml",
        "element_id": None,
    }
    assert artifact["diagnostics"] == [
        {
            "code": "malformed_xml",
            "severity": "error",
            "message": "could not parse UDT body",
            "location": {"relative_path": "Types/UDTs/Broken.xml", "element_id": None},
        }
    ]


# --------------------------------------------------------------------------- #
# Resolved edge serializes source/target identities                          #
# --------------------------------------------------------------------------- #


def test_resolved_edge_serializes_source_and_target_identities():
    source_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller", "FC")
    target_identity = _identity(
        ArtifactKind.BLOCK, ArtifactOrigin.PROJECT_LIBRARY, "Target", "FC"
    )
    edge = ReferenceEdge(
        location=_location("PLC_1/Caller.xml", "10"),
        source=source_identity,
        target=target_identity,
        kind=ArtifactKind.BLOCK,
    )
    index = ProjectIndex(
        artifacts=(
            _record(source_identity, "PLC_1/Caller.xml"),
            _record(target_identity, "Types/Blocks/Target.xml"),
        ),
        edges=(edge,),
    )

    manifest = emit_project_manifest(index)

    assert manifest["edges"] == [
        {
            "location": {"relative_path": "PLC_1/Caller.xml", "element_id": "10"},
            "source": {
                "kind": "block",
                "origin": "user",
                "namespace": [],
                "name": "Caller",
                "block_kind": "FC",
                "key": source_identity.key,
            },
            "target": {
                "kind": "block",
                "origin": "project-library",
                "namespace": [],
                "name": "Target",
                "block_kind": "FC",
                "key": target_identity.key,
            },
            "kind": "block",
        }
    ]


# --------------------------------------------------------------------------- #
# Determinism                                                                  #
# --------------------------------------------------------------------------- #


def test_emitting_the_same_index_twice_is_byte_identical():
    index = _project_index()

    first = json.dumps(emit_project_manifest(index), sort_keys=True)
    second = json.dumps(emit_project_manifest(index), sort_keys=True)

    assert first == second


def test_writing_the_manifest_twice_produces_byte_identical_files(tmp_path):
    destination = tmp_path / "manifest.json"
    index = _project_index()

    write_project_manifest(index, destination)
    first_bytes = destination.read_bytes()
    write_project_manifest(index, destination)
    second_bytes = destination.read_bytes()

    assert first_bytes == second_bytes


# --------------------------------------------------------------------------- #
# Atomic write                                                                 #
# --------------------------------------------------------------------------- #


def test_write_project_manifest_writes_destination_atomically(tmp_path):
    destination = tmp_path / "manifest.json"

    result = write_project_manifest(_project_index(), destination)

    assert result == destination
    assert destination.exists()
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert not (tmp_path / ".manifest.json.tmp").exists()


def test_write_project_manifest_leaves_no_destination_on_replace_failure(tmp_path, monkeypatch):
    destination = tmp_path / "manifest.json"

    def _boom(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", _boom)

    with pytest.raises(OSError):
        write_project_manifest(_project_index(), destination)

    assert not destination.exists()
    # write_text succeeded before replace raised -- the .tmp sibling must be
    # cleaned up rather than left orphaned on disk.
    assert not (tmp_path / ".manifest.json.tmp").exists()


def test_write_project_manifest_does_not_clobber_a_previous_manifest_on_replace_failure(
    tmp_path, monkeypatch
):
    destination = tmp_path / "manifest.json"
    destination.write_text('{"schema_version": 0}\n', encoding="utf-8")

    def _boom(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", _boom)

    with pytest.raises(OSError):
        write_project_manifest(_project_index(), destination)

    assert json.loads(destination.read_text(encoding="utf-8")) == {"schema_version": 0}
    assert not (tmp_path / ".manifest.json.tmp").exists()
