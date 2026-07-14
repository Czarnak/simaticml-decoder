# Project-Scale SimaticML Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, deterministic V21 SimaticML project-index command that inventories nested UDTs, user blocks, and project-library blocks, then resolves cross-artifact references without changing the legacy single-file or directory decoder.

**Architecture:** Keep `parse.py -> model.py -> fold.py -> ir.py -> emit.py` as the block-level pipeline. Put project-only, immutable records above it: a safe discovery stage, a V21 SimaticML adapter, a conservative reference resolver, and an analysis-only manifest writer. The adapter may preserve unknown/unsupported artifacts, but it must not invent a UDT grammar, library origin, or reference target.

**Discovery/read reuse (2026-07-14 amendment, architect + security review):** Project-mode discovery and the later per-artifact read must reuse `input_policy.py`'s existing handle-anchored walk (native NT handles on Windows, `dir_fd`+`O_NOFOLLOW` on POSIX) rather than introduce a second, path-based traversal. An earlier draft of Task 2 used `Path.rglob()` + `is_symlink()` + `resolve()`, with Task 3 later reopening each file by its stored path via `parse.parse_file(str(path))`. Independent architect and security review confirmed this reintroduces — with a *larger* window, since discovery fully walks the tree before any parsing starts — the exact TOCTOU race `docs/superpowers/memory/native-handle-traversal-decision.md` already closed for the existing CLI: an attacker with write access to the scanned tree can swap a discovered file for a symlink/junction between discovery and the later path-based reopen, redirecting the read outside the resolved project root. Tasks 2 and 3 below are corrected to route through `input_policy.py`'s existing machinery instead.

**Fixture corpus reuse (2026-07-14 amendment, confirmed with the project owner):** Task 3 and Task 7 originally called for a brand-new fixture tree at `tests/fixtures/corpus/v21/...`, on the assumption that no native V21 corpus existed yet. It already exists and is already committed: `tests/fixtures/SimaticML/` is a real exported TIA V21 PLC project (with sibling `SimaticSD*/` cross-format exports), indexed by the already-committed `tests/fixtures/manifest.json` (`provenance` + `cross_format_mapping` + `cases`), and already consumed by `tests/test_fixture_corpus.py`/`tests/conftest.py`. Within each export root, `Types/Blocks/` and `Types/UDTs/` are project-library-origin artifacts; `PLC_1/Program blocks/` and `PLC_1/PLC data types/` are user-origin. Confirmed real evidence already in this tree: a nested user block (`PLC_1/Program blocks/100_Inputs/Inputs_FB.xml`), UDT exports (`PLC_1/PLC data types/UDT_Settings.xml`, `Types/UDTs/UDT_Device.xml`), project-library blocks (`Types/Blocks/AnalogInput.xml`, `Types/Blocks/deviceState.xml`), and real user-to-library calls (`Inputs_FB.xml` calls `AnalogInput`; `PLC_1/Program blocks/999_MISC/MotorSoftstart.xml` calls `deviceState` and the sibling user block `TIME_COUNTER_FB`). Tasks 3 and 7 below are corrected to extend this existing tree and manifest in place rather than fork a duplicate `corpus/v21/` structure; any fixture this real corpus does not already exhibit (e.g. a missing-reference, ambiguous-reference, or non-V21/missing-version case, if inventory does not find one occurring naturally) must be added as a small, clearly-labeled synthetic addition (`"origin": "synthetic"` in `tests/fixtures/manifest.json`), never presented as a native export.

**Tech Stack:** Python 3.11+, standard-library `dataclasses`, `enum`, `hashlib`, `json`, `pathlib`, and `xml.etree.ElementTree`; pytest with coverage; Ruff; existing package entry point.

## Global Constraints

- Satisfies AC-001, AC-002, AC-003, AC-004 (SimaticML root), AC-010, AC-011, AC-012, AC-013, and AC-014 in `docs/ADVANCED_TRANSLATION_ACCEPTANCE_CRITERIA.md`.
- Support only TIA Portal V21 semantics. An explicit non-V21 version is preserved with `UNSUPPORTED_TIA_VERSION`; a missing version is preserved with `UNKNOWN_TIA_VERSION`. Neither is translated as V21.
- Keep input objects immutable: new project records use `@dataclass(frozen=True)` and tuples; do not expose mutable parser internals or mutable dictionaries as project state.
- The four artifact statuses are exactly `complete`, `partial`, `preserved`, and `failed`. A diagnostic is required for every status other than `complete`.
- Process only regular files physically contained by the resolved project root. Reject symlinks and paths escaping the root. Do not follow symlinked directories.
- Defaults are `max_files=10_000`, `max_file_bytes=16 MiB`, `max_total_bytes=512 MiB`, `max_relative_depth=32`, `max_xml_elements=500_000`, `max_xml_depth=128`, and `max_reference_edges=100_000`.
- Initial project ingestion is serial and deterministic. Concurrency, cancellation, streaming, and resume/checkpoints are deferred scale milestones, not hidden behavior in this release.
- Project output is analysis-only and non-re-importable. GRAPH, generation of TIA import files, and generic YAML parsing are out of scope.
- Use `tests/fixtures/manifest.json`'s `cross_format_mapping` array as the sole cross-format mapping oracle (2026-07-14 amendment: this already-committed manifest replaces the originally planned, nonexistent `tests/fixtures/corpus/v21/cross-format-map.json`). It may map zero, one, or many source artifacts across the separate SimaticML and SIMATIC SD roots; production code must not read it.

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `src/simaticml_decoder/project_model.py` | Immutable project identities, provenance, limits, diagnostics, statuses, records, and index types. |
| `src/simaticml_decoder/input_policy.py` | *(modified, not replaced)* Adds soft-diagnostic sibling walk functions (`_walk_windows_softdiag`/`_walk_posix_softdiag`) and `discover_project_artifacts()`, reusing the existing handle-anchored machinery; existing hard-fail directory-mode behavior (`discover_input_files`) is unchanged. |
| `src/simaticml_decoder/project_discovery.py` | Thin adapter over `input_policy.discover_project_artifacts()`: project-shaped limits/diagnostics and format classification. No path-based traversal of its own. |
| `src/simaticml_decoder/parse.py` | *(modified)* Adds `parse_bytes()` so a discovered artifact's already-read bytes can be parsed without reopening its path; `parse_file()` becomes a thin wrapper that reads once and delegates. |
| `src/simaticml_decoder/project_xml.py` | V21 SimaticML preflight, block adapter, observed-schema UDT adapter, and reference extraction — operates on bytes obtained from `DiscoveredFile.artifact.read_bytes()`, never a re-opened path. |
| `src/simaticml_decoder/project_index.py` | Deterministic identity construction, unique-only resolution, and call/type edges. |
| `src/simaticml_decoder/project_emit.py` | Canonical analysis-only project-manifest construction and atomic writing. |
| `src/simaticml_decoder/project.py` | Explicit SimaticML project-index orchestration. |
| `src/simaticml_decoder/cli.py` | New `--project` command path; legacy `PATH` mode remains unchanged. |
| `docs/PROJECT_INPUT_CONTRACT.md` | V21 input boundaries, layout selection, statuses, limits, diagnostics, and non-re-importability. |
| `tests/test_project_*.py` | Unit, integration, manifest, CLI, input-safety, and determinism coverage. |
| `tests/fixtures/SimaticML/`, `tests/fixtures/SimaticSD*/` | *(reused, not duplicated — 2026-07-14 amendment)* Already-committed native V21 project fixture root; see the Fixture corpus reuse note above for the user/library split. |
| `tests/fixtures/manifest.json` | *(extended, not replaced)* Already-committed provenance + `cross_format_mapping` oracle; project mode adds identity/origin/reference-case annotations here instead of a new file. |

---

### Task 1: Define immutable project contracts and diagnostic vocabulary

**Files:**

- Create: `src/simaticml_decoder/project_model.py`
- Create: `tests/test_project_model.py`
- Modify: `src/simaticml_decoder/__init__.py` only if the package exposes public project APIs

**Interfaces:**

- Consumes: none.
- Produces: `ProjectLimits`, `InputFormat`, `ArtifactKind`, `ArtifactOrigin`, `ArtifactStatus`, `DiagnosticCode`, `ProjectDiagnostic`, `SourceLocation`, `QualifiedIdentity`, `ArtifactRecord`, `ReferenceRequest`, `ReferenceEdge`, and `ProjectIndex` for every later task.

- [ ] **Step 1: Write the failing contract tests**

```python
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
```

- [ ] **Step 2: Run the contract tests and verify the import fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_model.py -v -p no:cacheprovider`

Expected: FAIL because `simaticml_decoder.project_model` does not exist.

- [ ] **Step 3: Implement the contracts with only immutable fields**

```python
class ArtifactStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PRESERVED = "preserved"
    FAILED = "failed"


@dataclass(frozen=True)
class ProjectLimits:
    max_files: int = 10_000
    max_file_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_relative_depth: int = 32
    max_xml_elements: int = 500_000
    max_xml_depth: int = 128
    max_reference_edges: int = 100_000
    follow_symlinks: bool = False


@dataclass(frozen=True)
class QualifiedIdentity:
    kind: ArtifactKind
    origin: ArtifactOrigin
    namespace: tuple[str, ...]
    name: str
    block_kind: str | None = None

    @property
    def key(self) -> str:
        namespace = "/".join(self.namespace) or "_"
        return ":".join((self.kind.value, self.origin.value, namespace, self.name, self.block_kind or "_"))
```

Define `DiagnosticCode` for `OUTSIDE_ROOT`, `SYMLINK_SKIPPED`, `FILE_COUNT_LIMIT`, `FILE_SIZE_LIMIT`, `TOTAL_SIZE_LIMIT`, `DEPTH_LIMIT`, `XML_ELEMENT_LIMIT`, `XML_DEPTH_LIMIT`, `REFERENCE_EDGE_LIMIT`, `MALFORMED_XML`, `UNSUPPORTED_ARTIFACT`, `UNSUPPORTED_TIA_VERSION`, `UNKNOWN_TIA_VERSION`, `DUPLICATE_IDENTITY`, `UNRESOLVED_REFERENCE`, and `AMBIGUOUS_REFERENCE`. Validate positive limits in `ProjectLimits.__post_init__`; fail fast with `ValueError` for a non-positive limit.

- [ ] **Step 4: Run focused tests and the existing unit suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_model.py tests/test_ir.py -v -p no:cacheprovider`

Expected: PASS, with no mutation of existing model or IR objects.

- [ ] **Step 5: Commit the contract boundary**

```bash
git add src/simaticml_decoder/project_model.py tests/test_project_model.py
git commit -m "feat: add immutable project index contracts"
```

### Task 2: Add safe, bounded, deterministic discovery on top of the existing hardened walk

**Files:**

- Modify: `src/simaticml_decoder/input_policy.py` (add soft-diagnostic walk siblings and `discover_project_artifacts()`)
- Create: `src/simaticml_decoder/project_discovery.py`
- Create: `tests/test_project_discovery.py`

**Interfaces:**

- Consumes: `InputFormat`, `ProjectDiagnostic`, `ProjectLimits`, and `SourceLocation` from `project_model.py`; `input_policy.InputArtifact`/`InputLimits`.
- Produces, split across two layers to keep the module boundary unambiguous:
  - `input_policy.py` adds `discover_project_artifacts(root, suffixes, limits) -> tuple[tuple[InputArtifact, ...], tuple[ProjectDiagnostic, ...]]` — the handle-anchored, soft-diagnostic walk itself. Nothing project-shaped beyond `ProjectDiagnostic` leaks into `input_policy.py`.
  - `project_discovery.py` adds `discover_project_files(root, suffixes, limits) -> DiscoveryResult` — the project-facing wrapper that calls `input_policy.discover_project_artifacts()` and composes each returned `InputArtifact` into a `DiscoveredFile`. This is the only `discover_project_files` name; callers (Task 3 onward) import it from `project_discovery`, never from `input_policy`.

**Security constraint:** must not reimplement path-based traversal (`rglob` + `is_symlink()` + `resolve()`). See the Architecture note above and `docs/superpowers/memory/native-handle-traversal-decision.md`. Every kept file's bytes must remain reachable only through a reader closure bound to a handle/fd opened *during this same walk* — never re-derived from a stored path later.

- [ ] **Step 1: Write failing root-containment and ordering tests**

```python
def test_discovery_is_relative_sorted_and_never_follows_a_symlink(tmp_path):
    root = tmp_path / "project"
    (root / "z").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "z" / "Second.xml").write_text("<Document />", encoding="utf-8")
    (root / "a" / "First.xml").write_text("<Document />", encoding="utf-8")
    (root / "outside.xml").write_text("<Document />", encoding="utf-8")
    (root / "link.xml").symlink_to(root / "outside.xml")

    result = discover_project_files(root, {".xml": InputFormat.SIMATICML_XML}, ProjectLimits())

    assert [item.location.relative_path.as_posix() for item in result.files] == [
        "a/First.xml", "outside.xml", "z/Second.xml"
    ]  # 2026-07-14 fix: outside.xml is a plain file physically inside root (only
       # link.xml is the symlink under test); the Global Constraints require
       # processing every regular file contained by the root, so it belongs in
       # the expected set. An earlier draft of this example omitted it, which
       # contradicted that constraint -- caught during Task 2's review.
    assert [item.code for item in result.diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]
    assert all(
        isinstance(item.artifact, input_policy.InputArtifact) for item in result.files
    )
```

- [ ] **Step 2: Run the discovery test and verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_discovery.py -v -p no:cacheprovider`

Expected: FAIL because the discovery module is absent.

- [ ] **Step 3: Add soft-diagnostic walk siblings in `input_policy.py`; never touch the existing hard-fail walkers**

`_walk_windows_directory`/`_walk_posix_directory` raise `InputViolation` immediately on any symlink/depth/count breach; that fail-the-whole-walk contract is load-bearing for the existing CLI's directory mode and must not change. Add new sibling functions instead, mirroring their shape but appending a `ProjectDiagnostic` and continuing instead of raising, and still opening every child relative to its parent's own already-open handle:

```python
def _walk_windows_softdiag(
    directory, relative_prefix, depth, limits, suffixes, artifacts, diagnostics
) -> None:
    """Mirrors _walk_windows_directory; records a diagnostic and continues
    past a reparse point / depth / file-count breach instead of raising.
    Still opens every child relative to its parent's own already-open
    handle -- the TOCTOU-closing invariant from native-handle-traversal-
    decision.md is unchanged, only the failure policy differs."""
    ...  # same entries()/open_child() shape as _walk_windows_directory


def _walk_posix_softdiag(
    dir_fd, relative_prefix, depth, limits, suffixes, artifacts, diagnostics
) -> None:
    ...  # same dir_fd/O_NOFOLLOW shape as _walk_posix_directory


def discover_project_artifacts(
    root: Path, suffixes: set[str], limits: "InputLimits"
) -> tuple[tuple[InputArtifact, ...], tuple["ProjectDiagnostic", ...]]:
    """Handle-anchored sibling of discover_input_files() for project mode:
    same TOCTOU-resistant traversal, soft per-item diagnostics instead of
    hard failure, delegating to _walk_windows_softdiag/_walk_posix_softdiag.
    Returns raw InputArtifacts; project_discovery.py wraps these into
    DiscoveredFile -- this function stays free of project-shaped types
    beyond the ProjectDiagnostic it already needs to report violations."""
    ...
```

`project_discovery.py` adapts this into project types without touching the filesystem itself: it builds an `InputLimits` from the relevant `ProjectLimits` fields, calls `input_policy.discover_project_artifacts()`, applies the project-only total-bytes budget and format classification, and wraps each result — this is the module's own `discover_project_files()`, the sole function of that name:

```python
@dataclass(frozen=True)
class DiscoveredFile:
    artifact: input_policy.InputArtifact  # bytes obtained only via artifact.read_bytes(limits)
    location: SourceLocation
    input_format: InputFormat
    size: int
```

Convert any `OUTSIDE_ROOT`-shaped failure from the underlying walk into a `ProjectDiagnostic` rather than letting it escape. Add independent tests for file count, file size, total size, relative depth, case-insensitive suffixes, and a root that does not exist.

- [ ] **Step 4: Run focused safety tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_discovery.py tests/test_input_policy.py -v -p no:cacheprovider`

Expected: PASS; each exceeded limit has its own diagnostic code, no path outside `root` occurs in `result.files`, existing `discover_input_files()`/CLI directory-mode tests are unaffected.

- [ ] **Step 5: Commit the discovery boundary**

```bash
git add src/simaticml_decoder/input_policy.py src/simaticml_decoder/project_discovery.py tests/test_project_discovery.py
git commit -m "feat: add bounded project file discovery on the hardened walk"
```

### Task 3: Adapt observed V21 XML artifacts without broadening the single-block parser

**Files:**

- Create: `src/simaticml_decoder/project_xml.py`
- Modify: `src/simaticml_decoder/parse.py` (add `parse_bytes()`; `parse_file()` becomes read-once-then-delegate)
- Create: `tests/test_project_xml.py`
- Modify: `tests/fixtures/manifest.json` (extend in place — see the Fixture corpus reuse amendment above; do not fork a new `corpus/v21/metadata.json`)

**Interfaces:**

- Consumes: `DiscoveredFile`, `ProjectLimits`, `ArtifactRecord`, and the new `parse.parse_bytes()`.
- Produces: `parse_simaticml_artifact(candidate, limits) -> ParsedArtifact`, `extract_block_references(document, source)`, and `extract_udt_references(document, source)`.

**Security constraint:** must read a discovered artifact's content exactly once, via `candidate.artifact.read_bytes(limits)` (the reader closure captured at discovery time in Task 2). Never call `parse.parse_file(str(candidate.path))` or otherwise reopen the file by a stored path — that reintroduces the TOCTOU race described in the Architecture note above.

- [ ] **Step 1: Establish the native corpus contract before parser changes**

Extend `tests/fixtures/manifest.json` in place (do not fork a new `metadata.json`) with entries identifying, per project-mode fixture, its known artifact kind/origin (`user` vs `project-library`, per the `Types/` vs `PLC_1/` split in the amendment above) and expected capability label; mark any added synthetic case with `"origin": "synthetic"` plus its test purpose. The real corpus already confirmed present: a nested user block, a UDT export, project-library blocks, and real user-to-library calls (see amendment above for exact paths). Before authoring anything synthetic, inventory the real call graph across `SimaticML/PLC_1/Program blocks/**` for a naturally-occurring missing-reference case (e.g. a call to an un-exported standard/system block) and an ambiguous-reference case; only add a minimal synthetic fixture for whichever of these — plus the non-V21/missing-version case, since real exports are consistently V21 — the real corpus does not already exhibit.

```python
def test_native_v21_project_corpus_is_complete(project_fixture_root):
    required = {
        "SimaticML/PLC_1/Program blocks/100_Inputs/Inputs_FB.xml",
        "SimaticML/PLC_1/PLC data types/UDT_Settings.xml",
        "SimaticML/Types/Blocks/AnalogInput.xml",
        "SimaticML/Types/UDTs/AnalogInputSettings.xml",
    }  # extend with whichever missing-ref/ambiguous-ref/non-V21 fixtures Step 1 finds or adds
    actual = {path.relative_to(project_fixture_root).as_posix() for path in project_fixture_root.rglob("*.xml")}
    assert required <= actual
```

- [ ] **Step 2: Run the corpus test and verify the already-real cases pass, only the not-yet-added cases fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_xml.py::test_native_v21_project_corpus_is_complete -v -p no:cacheprovider`

Expected: the real-data assertions PASS immediately (these fixtures are already committed); only assertions for a case Step 1 determined must be added synthetically FAIL until that fixture exists. Do not replace a failing case with `pytest.skip`.

- [ ] **Step 3: Implement bounded XML preflight and narrow block adaptation over already-read bytes**

```python
def parse_simaticml_artifact(
    candidate: DiscoveredFile, limits: ProjectLimits
) -> ParsedArtifact:
    raw = candidate.artifact.read_bytes(_as_input_limits(limits))  # single consuming read
    preflight_xml_bytes(raw, limits)
    document = parse.parse_bytes(raw)
    version = document.engineering_version
    if version and "V21" not in version:
        return _preserved_version(candidate, DiagnosticCode.UNSUPPORTED_TIA_VERSION, version)
    if not version:
        return _preserved_version(candidate, DiagnosticCode.UNKNOWN_TIA_VERSION, None)
    return _block_artifact(document, candidate)
```

`preflight_xml_bytes()` must use `ElementTree.iterparse` over `io.BytesIO(raw)` — the bytes already obtained from `read_bytes()`, never a reopened path — to count elements and nesting depth before calling the parser. It must return `MALFORMED_XML`, `XML_ELEMENT_LIMIT`, or `XML_DEPTH_LIMIT` as structured diagnostics. In `parse.py`, add `parse_bytes(raw: bytes) -> model.Document` sharing `_parse_block`'s internals with `parse_file()`, and refactor `parse_file()` into `parse_bytes(path.read_bytes())` so there is exactly one parsing entry point that doesn't require a filesystem path. Reuse the resulting parse only for recognized `SW.Blocks.*` exports. Preserve unrecognized XML as an artifact with `UNSUPPORTED_ARTIFACT`; do not modify `model.Document` into a broad XML union.

Implement a UDT adapter only from the supplied V21 UDT export. If the observed UDT shape cannot be parsed safely, create an `ArtifactKind.UDT` record with `PRESERVED` status, SHA-256, source location, and diagnostic; do not infer an XML schema.

- [ ] **Step 4: Extract references with exact provenance**

```python
def extract_block_references(
    document: model.Document, source: SourceLocation
) -> tuple[ReferenceRequest, ...]:
    requests: list[ReferenceRequest] = []
    for network in document.block.networks:
        if not isinstance(network.source, model.FlgNet):
            continue
        for call in network.source.calls.values():
            requests.append(ReferenceRequest(
                source=SourceLocation(source.relative_path, call.uid),
                requested_name=call.name,
                requested_block_kind=call.block_type,
                namespace=(),
                kind=ArtifactKind.BLOCK,
            ))
    return tuple(requests)
```

Use the native field names actually present in the fixture (`Name`, `BlockType`, and `UId` in the current block model). Add UDT-reference extraction from observed interface member datatype syntax only after a red test shows that source syntax. Never attach a source-line number that the parser cannot prove; relative path plus `UId` is the source location in this phase.

- [ ] **Step 5: Run adapter and reference tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_xml.py tests/test_parse.py -v -p no:cacheprovider`

Expected: PASS, including preservation of unsupported/non-V21 input and V21 user-to-library call provenance.

- [ ] **Step 6: Commit the V21 XML adapter**

```bash
git add src/simaticml_decoder/project_xml.py tests/test_project_xml.py tests/fixtures/manifest.json
git commit -m "feat: adapt V21 SimaticML project artifacts"
```

(Add any new synthetic fixture files created this task alongside `tests/fixtures/manifest.json` in the same commit.)

### Task 4: Build a conservative deterministic identity index and resolver

**Files:**

- Create: `src/simaticml_decoder/project_index.py`
- Create: `tests/test_project_index.py`

**Interfaces:**

- Consumes: `ParsedArtifact`, `QualifiedIdentity`, `ReferenceRequest`, `ProjectLimits`.
- Produces: `index_project_artifacts(artifacts, limits) -> ProjectIndex` and immutable `ReferenceEdge` records.

- [ ] **Step 1: Write failing resolver tests for unique, ambiguous, unresolved, duplicate, and cyclic references**

```python
def test_resolver_never_selects_the_first_of_two_matching_candidates():
    index = index_project_artifacts(_ambiguous_project_artifacts(), ProjectLimits())

    assert index.edges == ()
    assert [diagnostic.code for diagnostic in index.diagnostics] == [
        DiagnosticCode.AMBIGUOUS_REFERENCE
    ]


def test_cycle_records_edges_without_recursive_traversal():
    index = index_project_artifacts(_two_block_cycle(), ProjectLimits())

    assert [(edge.source.key, edge.target.key) for edge in index.edges] == [
        ("block:user:_:A:FC", "block:user:_:B:FC"),
        ("block:user:_:B:FC", "block:user:_:A:FC"),
    ]
```

- [ ] **Step 2: Run resolver tests and verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_index.py -v -p no:cacheprovider`

Expected: FAIL because the resolver module is absent.

- [ ] **Step 3: Implement unique-only resolution**

```python
def resolve_references(
    records: tuple[ArtifactRecord, ...], limits: ProjectLimits
) -> tuple[tuple[ReferenceEdge, ...], tuple[ProjectDiagnostic, ...]]:
    candidates = _candidate_map(records)
    edges: list[ReferenceEdge] = []
    diagnostics: list[ProjectDiagnostic] = []
    for request in _sorted_requests(records):
        matches = _matching_identities(candidates, request)
        if len(matches) == 1:
            edges.append(ReferenceEdge(request.source, request.source_identity, matches[0], request.kind))
        elif not matches:
            diagnostics.append(_reference_diagnostic(DiagnosticCode.UNRESOLVED_REFERENCE, request))
        else:
            diagnostics.append(_reference_diagnostic(DiagnosticCode.AMBIGUOUS_REFERENCE, request, matches))
        if len(edges) > limits.max_reference_edges:
            diagnostics.append(_limit_diagnostic(DiagnosticCode.REFERENCE_EDGE_LIMIT, request.source))
            break
    return tuple(_sorted_edges(edges)), tuple(_sorted_diagnostics(diagnostics))
```

Use no collision precedence and no first-match fallback. A call with no explicit origin resolves only when exactly one known candidate matches. An explicit `--library-root` layout selection or observed V21 metadata supplies `ArtifactOrigin.PROJECT_LIBRARY`; otherwise retain `UNKNOWN`. Cycles are valid graph edges, not recursive work.

- [ ] **Step 4: Run project index tests twice for byte-stable data**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_index.py -v -p no:cacheprovider`

Expected: PASS; repeat invocation yields equal immutable `ProjectIndex` values and the same diagnostic ordering.

- [ ] **Step 5: Commit the resolver**

```bash
git add src/simaticml_decoder/project_index.py tests/test_project_index.py
git commit -m "feat: resolve project block and UDT references"
```

### Task 5: Emit an analysis-only, atomic project manifest

**Files:**

- Create: `src/simaticml_decoder/project_emit.py`
- Create: `tests/test_project_emit.py`

**Interfaces:**

- Consumes: `ProjectIndex`.
- Produces: `emit_project_manifest(index) -> dict[str, object]` and `write_project_manifest(index, destination) -> Path`.

- [ ] **Step 1: Write failing manifest tests**

```python
def test_manifest_has_no_absolute_paths_and_declares_output_contract(tmp_path):
    manifest = emit_project_manifest(_project_index())

    encoded = json.dumps(manifest, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert manifest["output_contract"] == {
        "fidelity": "analysis-only",
        "reimportable": False,
    }
    assert manifest["schema_version"] == 1
```

- [ ] **Step 2: Run the emitter test and verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_emit.py -v -p no:cacheprovider`

Expected: FAIL because the manifest emitter is absent.

- [ ] **Step 3: Implement canonical JSON and atomic replacement**

```python
def write_project_manifest(index: ProjectIndex, destination: Path) -> Path:
    payload = json.dumps(
        emit_project_manifest(index), indent=2, ensure_ascii=False, sort_keys=True
    ) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(destination)
    return destination
```

Serialize only normalized relative POSIX paths, content hashes, byte sizes, identities, status, diagnostic codes/messages, and reference edges. Never serialize raw absolute paths, parser objects, or raw bytes. A failed write returns a CLI error while leaving any previous complete manifest untouched; test that behavior by monkeypatching `Path.replace`.

- [ ] **Step 4: Run deterministic and write-failure tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_emit.py -v -p no:cacheprovider`

Expected: PASS; JSON is byte-identical for identical indexes and a write failure does not create a partial destination file.

- [ ] **Step 5: Commit manifest emission**

```bash
git add src/simaticml_decoder/project_emit.py tests/test_project_emit.py
git commit -m "feat: emit deterministic project manifests"
```

### Task 6: Add an explicit project CLI mode without changing legacy batch behavior

**Files:**

- Create: `src/simaticml_decoder/project.py`
- Modify: `src/simaticml_decoder/cli.py`
- Create: `tests/test_project_cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**

- Consumes: discovery, XML adapter, index, emitter, and `ProjectLimits`.
- Produces: `index_simaticml_project(root, library_roots, limits) -> ProjectIndex` and `simaticml-decode --project ROOT`.

- [ ] **Step 1: Write failing CLI mode-separation tests**

```python
def test_project_mode_writes_one_manifest_and_keeps_legacy_directory_mode(tmp_path):
    project_output = tmp_path / "project-output"
    legacy_output = tmp_path / "legacy-output"

    assert cli.main(["--project", str(PROJECT_ROOT), "-o", str(project_output), "-q"]) == 0
    assert (project_output / "project-manifest.json").is_file()
    assert not list(project_output.rglob("*.scl"))

    assert cli.main([str(SINGLE_BLOCK_ROOT), "-o", str(legacy_output), "--format", "both", "-q"]) == 0
    assert list(legacy_output.rglob("*.scl"))
```

- [ ] **Step 2: Run the CLI test and verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_cli.py -v -p no:cacheprovider`

Expected: FAIL because `--project` is not yet a CLI option.

- [ ] **Step 3: Route the command explicitly**

```python
p.add_argument("input", metavar="PATH", nargs="?", help="legacy block or batch input")
p.add_argument("--project", metavar="ROOT", help="index a V21 project export; writes project-manifest.json")
p.add_argument("--library-root", action="append", default=[], metavar="RELATIVE_PATH")
p.add_argument("--max-files", type=int, default=ProjectLimits().max_files)
p.add_argument("--max-file-bytes", type=int, default=ProjectLimits().max_file_bytes)
p.add_argument("--max-total-bytes", type=int, default=ProjectLimits().max_total_bytes)
p.add_argument("--max-depth", type=int, default=ProjectLimits().max_relative_depth)
p.add_argument("--max-xml-elements", type=int, default=ProjectLimits().max_xml_elements)
p.add_argument("--max-xml-depth", type=int, default=ProjectLimits().max_xml_depth)
p.add_argument("--max-reference-edges", type=int, default=ProjectLimits().max_reference_edges)
```

Require exactly one of `input` and `--project`. `--library-root` paths must be normalized relative paths under `ROOT`; invalid selections produce `OUTSIDE_ROOT`. Project mode always writes `project-manifest.json`, returns nonzero if any artifact is `failed`, and preserves valid/partial/preserved artifacts in the manifest. It does not call `fold.fold_block()` or `emit.emit_scl()` implicitly.

- [ ] **Step 4: Run new and legacy CLI tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_cli.py tests/test_cli.py -v -p no:cacheprovider`

Expected: PASS; existing one-file and recursive-directory behavior is unchanged.

- [ ] **Step 5: Commit project CLI routing**

```bash
git add src/simaticml_decoder/project.py src/simaticml_decoder/cli.py tests/test_project_cli.py tests/test_cli.py
git commit -m "feat: add explicit project index command"
```

### Task 7: Make the corpus and public contract runnable in CI

**Files:**

- Modify: `tests/conftest.py`
- Create: `tests/test_project_corpus_integrity.py`
- Create: `tests/golden/v21_project_manifest.json`
- Create: `docs/PROJECT_INPUT_CONTRACT.md`
- Modify: `README.md`
- Modify: `.gitignore`

**Interfaces:**

- Consumes: committed V21 fixture corpus and manifest schema.
- Produces: non-skipping fixture helpers, public project input contract, and a golden manifest test.

- [ ] **Step 1: Write the failing fresh-clone integrity test**

```python
def test_committed_project_corpus_has_metadata_mapping_and_golden():
    assert (FIXTURES_ROOT / "manifest.json").is_file()
    assert (FIXTURES_ROOT / "SimaticML").is_dir()
    assert (GOLDEN_ROOT / "v21_project_manifest.json").is_file()
    assert not _fixture_helper_uses_pytest_skip_for_committed_v21_cases()
```

- [ ] **Step 2: Run the integrity test and verify it fails before corpus tracking changes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_corpus_integrity.py -v -p no:cacheprovider`

Expected: FAIL until fixture files and golden output are tracked.

- [ ] **Step 3: Make fixtures authoritative and document the contract**

Update `tests/conftest.py` so committed V21 fixtures fail loudly when absent rather than calling `pytest.skip`. Keep any optional developer-only fixture helpers separate and unused by supported-format tests. Whitelist only the specific corpus, goldens, contract, and plans in `.gitignore`; preserve private local samples.

`docs/PROJECT_INPUT_CONTRACT.md` must state the V21-only compatibility profile, canonical relative paths, library-root selection, symlink policy, every default budget, status vocabulary, diagnostic codes, partial-success exit behavior, deterministic ordering, source-location meaning, analysis-only output contract, GRAPH deferral, and no re-importability claim.

- [ ] **Step 4: Run corpus, project, and existing tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_corpus_integrity.py tests/test_project_*.py tests/test_cli.py -v -p no:cacheprovider`

Expected: PASS with zero fixture-related skips for project indexing.

- [ ] **Step 5: Commit the reproducible corpus contract**

```bash
git add tests/conftest.py tests/test_project_corpus_integrity.py tests/fixtures/manifest.json tests/golden docs/PROJECT_INPUT_CONTRACT.md README.md .gitignore
git commit -m "docs: define V21 project input contract"
```

### Task 8: Enforce the release-quality threshold

**Files:**

- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml` if its coverage or Python matrix conflicts with the supported package metadata
- Modify: `README.md`

**Interfaces:**

- Consumes: all project tests and the existing quality tooling.
- Produces: a documented and enforced 80% total-coverage gate for the supported immediate scope.

- [ ] **Step 1: Write a failing CI-configuration test or assert coverage configuration**

```python
def test_pytest_coverage_floor_is_80_percent():
    config = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "--cov-fail-under=80" in config
```

- [ ] **Step 2: Run it and verify the test fails against the current `pyproject.toml`**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_quality_configuration.py::test_pytest_coverage_floor_is_80_percent -v -p no:cacheprovider`

Expected: FAIL — `.github/workflows/ci.yml` already runs with `--cov-fail-under=80` (verified 2026-07-14), but `pyproject.toml` doesn't encode any coverage floor at all today. This step is not "raise 70% to 80%"; it closes the gap between an already-enforced CI floor and an undocumented `pyproject.toml`.

- [ ] **Step 3: Record the already-enforced floor in `pyproject.toml`**

Add the 80% floor to `pyproject.toml` (e.g. `[tool.pytest.ini_options] addopts = "--cov-fail-under=80"`, or an equivalent `[tool.coverage.report] fail_under = 80`) so `pyproject.toml` and the quality command documented in `README.md` match CI exactly, rather than CI being the only place this floor is defined. Align CI's Python versions with the package's stated support or narrow the stated support deliberately; do not advertise untested versions.

- [ ] **Step 4: Run the full quality gate**

Run: `./.venv/Scripts/python.exe -m pytest -v -p no:cacheprovider --cov=src/simaticml_decoder --cov-fail-under=80`

Expected: PASS with no fixture-related skips for project, FBD, or SIMATIC SD supported cases.

Run: `./.venv/Scripts/python.exe -m ruff check src tests`

Expected: PASS.

- [ ] **Step 5: Commit the quality gate**

```bash
git add pyproject.toml .github/workflows/ci.yml README.md tests/test_quality_configuration.py
git commit -m "ci: enforce supported-format coverage gate"
```

## Self-Review

- AC coverage: Tasks 1–6 implement deterministic V21 project ingestion, user/library/UDT inventory, references, budgets, status recovery, manifest output, and explicit CLI separation. Task 7 supplies the committed corpus and input policy. Task 8 enforces AC-013. All tasks preserve GRAPH and re-importability deferral.
- Evidence gates: the exact UDT syntax, V21 version field, and library-origin metadata are read from the supplied native exports before semantic parsing; the plan contains preservation behavior when that evidence is absent.
- Completeness scan: no generic parser, implicit library-path inference, or unsupported TIA import behavior is prescribed.
- Type consistency: every later task consumes immutable `ProjectIndex`/`ArtifactRecord`/`ProjectDiagnostic` contracts defined in Task 1; SIMATIC SD will extend the format registry rather than creating another project model.
- Security (2026-07-14 amendment): Tasks 2 and 3 were corrected after independent architect and security review confirmed the original path-based discovery + reopen-by-path design reintroduced a TOCTOU race already closed by `input_policy.py`'s handle-anchored walk (see the Architecture note and `docs/superpowers/memory/native-handle-traversal-decision.md`). Discovery now delegates to new soft-diagnostic siblings of the existing hard-fail walk functions, and artifact bytes flow through a single `read_bytes()`/`parse_bytes()` call — never a stored path reopened later.
- Fixture reuse (2026-07-14 amendment): Tasks 3 and 7 were corrected after confirming with the project owner that a native, already-committed V21 corpus already exists (`tests/fixtures/SimaticML/` + `tests/fixtures/manifest.json`) rather than needing to be supplied fresh. Both tasks now extend this existing tree/manifest in place; any evidence category it doesn't already exhibit gets a minimal, explicitly-labeled synthetic addition rather than a fabricated "native" export.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-project-scale-simaticml-ingestion.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task and review each boundary.
2. **Inline Execution** — execute the tasks in this session in small TDD batches with review checkpoints.
