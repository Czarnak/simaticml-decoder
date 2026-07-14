from pathlib import PurePosixPath

from simaticml_decoder.project_model import (
    ArtifactKind, ArtifactOrigin, ArtifactStatus, DiagnosticCode,
    ProjectDiagnostic, QualifiedIdentity, SourceLocation,
)


def test_qualified_identity_key_is_stable_and_origin_aware():
    user = QualifiedIdentity(
        kind=ArtifactKind.BLOCK,
        origin=ArtifactOrigin.USER,
        namespace=("Motion",),
        name="Axis",
        block_kind="FB",
    )
    library = QualifiedIdentity(
        kind=ArtifactKind.BLOCK,
        origin=ArtifactOrigin.PROJECT_LIBRARY,
        namespace=("Motion",),
        name="Axis",
        block_kind="FB",
    )
    assert user.key == "block:user:Motion:Axis:FB"
    assert library.key == "block:project-library:Motion:Axis:FB"
    assert user != library


def test_non_complete_status_requires_a_diagnostic():
    source = SourceLocation(PurePosixPath("blocks/Axis.xml"))
    diagnostic = ProjectDiagnostic(
        code=DiagnosticCode.UNKNOWN_TIA_VERSION,
        severity="warning",
        message="TIA engineering version is absent",
        location=source,
    )
    assert diagnostic.location.relative_path.as_posix() == "blocks/Axis.xml"
