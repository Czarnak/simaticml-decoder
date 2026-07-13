# Project-Scale SimaticML Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, deterministic V21 SimaticML project-index command that inventories nested UDTs, user blocks, and project-library blocks, then resolves cross-artifact references without changing the legacy single-file or directory decoder.

**Architecture:** Keep `parse.py -> model.py -> fold.py -> ir.py -> emit.py` as the block-level pipeline. Put project-only, immutable records above it: a safe discovery stage, a V21 SimaticML adapter, a conservative reference resolver, and an analysis-only manifest writer. The adapter may preserve unknown/unsupported artifacts, but it must not invent a UDT grammar, library origin, or reference target.

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
- Use `tests/fixtures/corpus/v21/cross-format-map.json` as the sole cross-format mapping oracle. It may map zero, one, or many source artifacts across the separate SimaticML and SIMATIC SD roots; production code must not read it.

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `src/simaticml_decoder/project_model.py` | Immutable project identities, provenance, limits, diagnostics, statuses, records, and index types. |
| `src/simaticml_decoder/project_discovery.py` | Bounded, root-contained discovery and format classification without parsing semantics. |
| `src/simaticml_decoder/project_xml.py` | V21 SimaticML preflight, block adapter, observed-schema UDT adapter, and reference extraction. |
| `src/simaticml_decoder/project_index.py` | Deterministic identity construction, unique-only resolution, and call/type edges. |
| `src/simaticml_decoder/project_emit.py` | Canonical analysis-only project-manifest construction and atomic writing. |
| `src/simaticml_decoder/project.py` | Explicit SimaticML project-index orchestration. |
| `src/simaticml_decoder/cli.py` | New `--project` command path; legacy `PATH` mode remains unchanged. |
| `docs/PROJECT_INPUT_CONTRACT.md` | V21 input boundaries, layout selection, statuses, limits, diagnostics, and non-re-importability. |
| `tests/test_project_*.py` | Unit, integration, manifest, CLI, input-safety, and determinism coverage. |
| `tests/fixtures/corpus/v21/simaticml/project/` | Sanitized native V21 project fixture root, added only with provenance metadata and goldens. |
| `tests/fixtures/corpus/v21/cross-format-map.json` | Test-only relation between separate SimaticML and SIMATIC SD exports. |

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

### Task 2: Add safe, bounded, deterministic discovery

**Files:**

- Create: `src/simaticml_decoder/project_discovery.py`
- Create: `tests/test_project_discovery.py`

**Interfaces:**

- Consumes: `InputFormat`, `ProjectDiagnostic`, `ProjectLimits`, and `SourceLocation` from `project_model.py`.
- Produces: `DiscoveredFile` and `discover_project_files(root, suffixes, limits) -> DiscoveryResult` for the XML and later SIMATIC SD adapters.

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
        "a/First.xml", "z/Second.xml"
    ]
    assert [item.code for item in result.diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]
```

- [ ] **Step 2: Run the discovery test and verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_discovery.py -v -p no:cacheprovider`

Expected: FAIL because the discovery module is absent.

- [ ] **Step 3: Implement containment, classification, and every budget check**

```python
def discover_project_files(
    root: Path,
    suffixes: Mapping[str, InputFormat],
    limits: ProjectLimits,
) -> DiscoveryResult:
    resolved_root = root.resolve(strict=True)
    files: list[DiscoveredFile] = []
    diagnostics: list[ProjectDiagnostic] = []
    total_bytes = 0
    for candidate in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if candidate.is_symlink():
            diagnostics.append(_diagnostic(DiagnosticCode.SYMLINK_SKIPPED, candidate, root))
            continue
        if not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(resolved_root)
        if len(relative.parts) > limits.max_relative_depth:
            diagnostics.append(_diagnostic(DiagnosticCode.DEPTH_LIMIT, candidate, root))
            continue
        size = resolved.stat().st_size
        if size > limits.max_file_bytes:
            diagnostics.append(_diagnostic(DiagnosticCode.FILE_SIZE_LIMIT, candidate, root))
            continue
        if total_bytes + size > limits.max_total_bytes:
            diagnostics.append(_diagnostic(DiagnosticCode.TOTAL_SIZE_LIMIT, candidate, root))
            continue
        input_format = suffixes.get(resolved.suffix.casefold())
        if input_format is None:
            continue
        if len(files) == limits.max_files:
            diagnostics.append(_diagnostic(DiagnosticCode.FILE_COUNT_LIMIT, candidate, root))
            break
        total_bytes += size
        files.append(DiscoveredFile(resolved, SourceLocation(PurePosixPath(relative.as_posix())), input_format, size))
    return DiscoveryResult(tuple(files), tuple(_sorted_diagnostics(diagnostics)))
```

Convert `ValueError` from `relative_to` into an `OUTSIDE_ROOT` diagnostic rather than letting it escape. Add independent tests for file count, file size, total size, relative depth, case-insensitive suffixes, and a root that does not exist.

- [ ] **Step 4: Run focused safety tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_discovery.py -v -p no:cacheprovider`

Expected: PASS; each exceeded limit has its own diagnostic code and no path outside `root` occurs in `result.files`.

- [ ] **Step 5: Commit the discovery boundary**

```bash
git add src/simaticml_decoder/project_discovery.py tests/test_project_discovery.py
git commit -m "feat: add bounded project file discovery"
```

### Task 3: Adapt observed V21 XML artifacts without broadening the single-block parser

**Files:**

- Create: `src/simaticml_decoder/project_xml.py`
- Create: `tests/test_project_xml.py`
- Modify: `tests/fixtures/corpus/v21/metadata.json`
- Create: `tests/fixtures/corpus/v21/simaticml/project/` native sanitized exports after the user supplies them

**Interfaces:**

- Consumes: `DiscoveredFile`, `ProjectLimits`, `ArtifactRecord`, and existing `parse.parse_file()`.
- Produces: `parse_simaticml_artifact(candidate, root, limits) -> ParsedArtifact`, `extract_block_references(document, source)`, and `extract_udt_references(document, source)`.

- [ ] **Step 1: Establish the native corpus contract before parser changes**

Add `metadata.json` entries that identify the V21 export method, redaction/license status, each source path, known artifact kind/origin, and expected capability label. Include a nested user block, a nested project-library block, at least one UDT export, an independent valid block, a user-to-library call, a missing-reference case, an ambiguous-reference case, and an explicit non-V21 or missing-version preservation case.

```python
def test_native_v21_project_corpus_is_complete(project_fixture_root):
    expected = {
        "types/DriveType.xml", "user/Motion/Axis.xml", "library/Motion/AxisSupport.xml",
        "negative/MissingCall.xml", "negative/AmbiguousCall.xml", "valid/Independent.xml",
    }
    actual = {path.relative_to(project_fixture_root).as_posix() for path in project_fixture_root.rglob("*.xml")}
    assert expected <= actual
```

- [ ] **Step 2: Run the corpus test and verify it fails until the committed fixture arrives**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_project_xml.py::test_native_v21_project_corpus_is_complete -v -p no:cacheprovider`

Expected: FAIL for an absent or incomplete committed native corpus. Do not replace this with `pytest.skip`.

- [ ] **Step 3: Implement bounded XML preflight and narrow block adaptation**

```python
def parse_simaticml_artifact(
    candidate: DiscoveredFile, root: Path, limits: ProjectLimits
) -> ParsedArtifact:
    preflight_xml(candidate.path, limits)
    document = parse.parse_file(str(candidate.path))
    version = document.engineering_version
    if version and "V21" not in version:
        return _preserved_version(candidate, DiagnosticCode.UNSUPPORTED_TIA_VERSION, version)
    if not version:
        return _preserved_version(candidate, DiagnosticCode.UNKNOWN_TIA_VERSION, None)
    return _block_artifact(document, candidate)
```

`preflight_xml()` must use `ElementTree.iterparse` to count elements and nesting depth before calling the existing parser. It must return `MALFORMED_XML`, `XML_ELEMENT_LIMIT`, or `XML_DEPTH_LIMIT` as structured diagnostics. Reuse `parse.parse_file()` only for recognized `SW.Blocks.*` exports. Preserve unrecognized XML as an artifact with `UNSUPPORTED_ARTIFACT`; do not modify `model.Document` into a broad XML union.

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
git add src/simaticml_decoder/project_xml.py tests/test_project_xml.py tests/fixtures/corpus/v21
git commit -m "feat: adapt V21 SimaticML project artifacts"
```

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
    assert (CORPUS_ROOT / "metadata.json").is_file()
    assert (CORPUS_ROOT / "cross-format-map.json").is_file()
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
git add tests/conftest.py tests/test_project_corpus_integrity.py tests/fixtures/corpus tests/golden docs/PROJECT_INPUT_CONTRACT.md README.md .gitignore
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

- [ ] **Step 2: Run it and verify the current 70% floor fails the test**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_quality_configuration.py::test_pytest_coverage_floor_is_80_percent -v -p no:cacheprovider`

Expected: FAIL while the repository still specifies `--cov-fail-under=70`.

- [ ] **Step 3: Raise and document the enforced floor**

Set the pytest coverage threshold to 80. Align CI's Python versions with the package's stated support or narrow the stated support deliberately; do not advertise untested versions. Keep the quality command in `README.md` identical to CI.

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

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-project-scale-simaticml-ingestion.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task and review each boundary.
2. **Inline Execution** — execute the tasks in this session in small TDD batches with review checkpoints.
