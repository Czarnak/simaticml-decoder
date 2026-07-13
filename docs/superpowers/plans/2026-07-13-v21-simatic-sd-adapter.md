# V21 SIMATIC SD Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, evidence-led V21 SIMATIC SD adapter that accepts code-only `.s7dcl` exports and optional `.s7res` resources, preserves original source/trivia/unknown content, and emits normalized analysis JSON without making a generic-YAML or re-importability claim.

**Architecture:** Reuse the project-ingestion plan's immutable discovery, identity, status, diagnostic, and manifest contracts. Add a separate `simatic_sd.py` front end: first classify and retain bounded raw source, then recognize the exact V21 dialect from committed native fixtures, then apply only an observed resource-association rule and a lossless parser. The project index receives normalized records and source provenance; it does not assume `.s7dcl` and `.s7res` naming or layout equivalence with SimaticML.

**Tech Stack:** Python 3.11+, standard-library `dataclasses`, `hashlib`, `json`, `pathlib`, and byte/text handling; pytest/golden JSON fixtures; Ruff. No PyYAML or other YAML parser dependency is introduced.

## Global Constraints

- Satisfies AC-004 (SIMATIC SD root), AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, and AC-014 in `docs/ADVANCED_TRANSLATION_ACCEPTANCE_CRITERIA.md`.
- TIA Portal V21 is the only compatibility profile. A candidate with no proven V21 dialect remains `preserved`; a proven incompatible dialect is `preserved` with `UNSUPPORTED_SD_DIALECT`.
- `.s7dcl` is valid without `.s7res`. `.s7res` is optional and may never be inferred from a sibling name, extension, or folder. An unpaired resource is preserved and receives `UNPAIRED_RESOURCE`.
- Preserve source as raw bytes plus SHA-256, relative path, byte spans, and line spans. Normalized JSON must retain comments/resource associations and unknown-field payloads without evaluating unknown content as code.
- Do not parse SIMATIC SD as generic YAML. Until the observed V21 grammar is implemented, retain it as a candidate/preserved source. If anchors, aliases, tags, or any YAML-like features appear, preserve their raw spans; do not expand them.
- Apply project limits plus SIMATIC SD limits: `max_sd_tokens=500_000`, `max_sd_nesting=128`, and `max_sd_scalar_bytes=1 MiB`. Any breach yields a structured diagnostic and no unbounded parser work.
- Inputs are immutable. The index stores normalized records and hashes, while raw bytes remain in an immutable `SourceArtifact` used only by the adapter/preservation writer.
- Output contract is `preservation-plus-analysis`, `reimportable: false`. Copying the supplied original bytes into an output preservation area is a provenance facility, not a generated TIA import artifact.
- GRAPH remains a deferred future JSON state-machine direction. This adapter must not act as a GRAPH parser or re-import generator.

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `src/simaticml_decoder/simatic_sd.py` | Candidate classification, bounded raw retention, dialect recognition, observed resource pairing, lossless V21 parsing, and normalized records. |
| `src/simaticml_decoder/project_model.py` | Adds SIMATIC SD input format and SD-specific diagnostic codes/limits to the shared immutable model. |
| `src/simaticml_decoder/project_discovery.py` | Registers `.s7dcl` and `.s7res` as candidate formats only; no semantic claim. |
| `src/simaticml_decoder/project.py` | Adds SD adapter orchestration beside the V21 SimaticML adapter. |
| `src/simaticml_decoder/project_emit.py` | Emits SD source provenance, normalized analysis records, and optional original-byte preservation area. |
| `src/simaticml_decoder/cli.py` | Extends `--project` mode with SD budgets and clear support output. |
| `tests/fixtures/corpus/v21/simatic_sd/code_only/` | Native V21 code-only `.s7dcl` exports. |
| `tests/fixtures/corpus/v21/simatic_sd/resource_backed/` | Native V21 `.s7dcl` plus optional `.s7res` case. |
| `tests/fixtures/corpus/v21/simatic_sd/unpaired_resource/` | Preserved unpaired `.s7res` diagnostic case. |
| `tests/fixtures/corpus/v21/cross-format-map.json` | Single test-only mapping between the separate SimaticML and SD roots. |
| `tests/golden/simatic_sd/v21/*.json` | Canonical normalized analysis goldens, including source-span and unknown-field expectations. |
| `tests/test_simatic_sd_*.py` | Intake, dialect, pairing, lossless parsing, integration, CLI, corpus, and safety tests. |

---

### Task 1: Commit the separate V21 SIMATIC SD corpus and mapping contract

**Files:**

- Create: `tests/fixtures/corpus/v21/simatic_sd/code_only/`
- Create: `tests/fixtures/corpus/v21/simatic_sd/resource_backed/`
- Create: `tests/fixtures/corpus/v21/simatic_sd/unpaired_resource/`
- Modify: `tests/fixtures/corpus/v21/metadata.json`
- Create: `tests/fixtures/corpus/v21/cross-format-map.json`
- Create: `tests/test_simatic_sd_corpus_integrity.py`

**Interfaces:**

- Consumes: the user-supplied small V21 project exported separately as SimaticML and SIMATIC SD.
- Produces: source-controlled native examples, one authoritative cross-format map, and fixture metadata used by parser and golden tests.

- [ ] **Step 1: Write a failing corpus-integrity test**

```python
def test_simatic_sd_corpus_contains_code_only_resource_backed_and_unpaired_cases():
    assert list((SD_ROOT / "code_only").glob("*.s7dcl"))
    assert list((SD_ROOT / "resource_backed").glob("*.s7dcl"))
    assert list((SD_ROOT / "resource_backed").glob("*.s7res"))
    assert list((SD_ROOT / "unpaired_resource").glob("*.s7res"))

    metadata = json.loads((CORPUS_ROOT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["profiles"] == ["tia-v21"]
    mapping = json.loads((CORPUS_ROOT / "cross-format-map.json").read_text(encoding="utf-8"))
    assert mapping["schema_version"] == 1
    assert mapping["production_dependency"] is False
```

- [ ] **Step 2: Run it and verify it fails until both separate exports are committed**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_corpus_integrity.py -v -p no:cacheprovider`

Expected: FAIL if the native SD root, the code-only case, resource-backed case, unpaired-resource case, or cross-format map is absent.

- [ ] **Step 3: Record non-ambiguous corpus metadata**

For each SD file, metadata must contain its relative path, SHA-256, byte size, TIA profile, export method, redaction/license status, capability label, expected dialect identifier, and expected artifact identities. For the resource-backed case, record an observed association evidence object; for the unpaired case, record `UNPAIRED_RESOURCE`. Do not encode an association using a filename stem unless native V21 content proves that relation.

`cross-format-map.json` must list canonical identities and, independently, zero-or-more SimaticML and SD source paths. It must permit an identity to exist in only one format and must not require matching directory layouts.

- [ ] **Step 4: Run corpus validation**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_corpus_integrity.py -v -p no:cacheprovider`

Expected: PASS with native data only and no fixture-related skip.

- [ ] **Step 5: Commit the cross-format corpus boundary**

```bash
git add tests/fixtures/corpus/v21 tests/test_simatic_sd_corpus_integrity.py
git commit -m "test: add V21 SIMATIC SD corpus contract"
```

### Task 2: Add bounded candidate intake and byte-preserving source artifacts

**Files:**

- Modify: `src/simaticml_decoder/project_model.py`
- Modify: `src/simaticml_decoder/project_discovery.py`
- Create: `src/simaticml_decoder/simatic_sd.py`
- Create: `tests/test_simatic_sd_intake.py`

**Interfaces:**

- Consumes: project discovery and shared `ProjectLimits`.
- Produces: `SourceArtifact`, `SimaticSDCandidate`, `classify_simatic_sd(path)`, and `read_simatic_sd_source(candidate, limits)`.

- [ ] **Step 1: Write failing candidate-intake tests**

```python
def test_code_only_s7dcl_is_a_preserved_candidate_with_stable_hash(tmp_path):
    source = tmp_path / "Code.S7DCL"
    raw = b"document: opaque-v21-sample\n"
    source.write_bytes(raw)

    candidate = classify_simatic_sd(source)
    artifact = read_simatic_sd_source(candidate, ProjectLimits())

    assert candidate.input_format is InputFormat.SIMATIC_SD_CODE
    assert artifact.status is ArtifactStatus.PRESERVED
    assert artifact.sha256 == hashlib.sha256(raw).hexdigest()
    assert artifact.content == raw


def test_resource_without_code_is_preserved_with_a_later_pairing_diagnostic(tmp_path):
    resource = tmp_path / "Comments.s7res"
    resource.write_bytes(b"resource: opaque\n")

    assert classify_simatic_sd(resource).input_format is InputFormat.SIMATIC_SD_RESOURCE
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_intake.py -v -p no:cacheprovider`

Expected: FAIL because the SIMATIC SD adapter does not exist.

- [ ] **Step 3: Implement classification and bounded raw retention without grammar inference**

```python
@dataclass(frozen=True)
class SourceArtifact:
    location: SourceLocation
    input_format: InputFormat
    content: bytes = field(repr=False, compare=False)
    sha256: str
    byte_size: int
    status: ArtifactStatus
    diagnostics: tuple[ProjectDiagnostic, ...] = ()


def classify_simatic_sd(path: Path) -> SimaticSDCandidate:
    formats = {
        ".s7dcl": InputFormat.SIMATIC_SD_CODE,
        ".s7res": InputFormat.SIMATIC_SD_RESOURCE,
    }
    return SimaticSDCandidate(path=path, input_format=formats[path.suffix.casefold()])


def read_simatic_sd_source(candidate: SimaticSDCandidate, limits: ProjectLimits) -> SourceArtifact:
    byte_size = candidate.path.stat().st_size
    if byte_size > limits.max_file_bytes:
        return _preserved_limit_artifact(candidate, DiagnosticCode.FILE_SIZE_LIMIT, byte_size)
    content = candidate.path.read_bytes()
    return SourceArtifact(
        location=candidate.location,
        input_format=candidate.input_format,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=byte_size,
        status=ArtifactStatus.PRESERVED,
    )
```

Register both suffixes in format-neutral discovery. A `.s7dcl` extension makes a source a candidate only; it does not prove YAML validity, V21 dialect, or semantic support. Add diagnostic codes `UNSUPPORTED_SD_DIALECT`, `UNPAIRED_RESOURCE`, `SD_TOKEN_LIMIT`, `SD_NESTING_LIMIT`, `SD_SCALAR_LIMIT`, and `SD_MALFORMED_SOURCE`.

- [ ] **Step 4: Run intake and common discovery safety tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_intake.py tests/test_project_discovery.py -v -p no:cacheprovider`

Expected: PASS; extension case is normalized, bytes/hash are stable, and all shared file limits still apply.

- [ ] **Step 5: Commit safe candidate intake**

```bash
git add src/simaticml_decoder/project_model.py src/simaticml_decoder/project_discovery.py src/simaticml_decoder/simatic_sd.py tests/test_simatic_sd_intake.py
git commit -m "feat: preserve SIMATIC SD input candidates"
```

### Task 3: Recognize only the observed V21 dialect and pair resources by content evidence

**Files:**

- Modify: `src/simaticml_decoder/simatic_sd.py`
- Create: `tests/test_simatic_sd_dialect.py`
- Create: `tests/test_simatic_sd_pairing.py`

**Interfaces:**

- Consumes: immutable `SourceArtifact` instances from Task 2 and native fixture metadata.
- Produces: `recognized_v21_dialect(source) -> RecognizedDialect | None` and `bundle_simatic_sd_sources(sources, dialect) -> tuple[SimaticSDBundle, ...]`.

- [ ] **Step 1: Write failing dialect and pairing tests against native data**

```python
def test_native_code_only_export_recognizes_v21_and_needs_no_resource():
    source = _read_native("code_only")
    dialect = recognize_v21_dialect(source)
    bundles = bundle_simatic_sd_sources((source,), dialect)

    assert dialect.identifier == _metadata("code_only")["expected_dialect"]
    assert bundles[0].code is source
    assert bundles[0].resource is None
    assert bundles[0].diagnostics == ()


def test_resource_pairing_uses_observed_content_identity_not_file_names():
    code, resource = _read_native_pair("resource_backed")
    renamed = replace(resource, location=SourceLocation(PurePosixPath("different/name.s7res")))

    bundles = bundle_simatic_sd_sources((code, renamed), recognize_v21_dialect(code))

    assert bundles[0].resource == renamed
```

- [ ] **Step 2: Run it and verify it fails before an observed dialect adapter exists**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_dialect.py tests/test_simatic_sd_pairing.py -v -p no:cacheprovider`

Expected: FAIL because preserving a candidate is not yet V21 recognition or content-evidenced pairing.

- [ ] **Step 3: Implement a dialect object whose matching rules are tied to native evidence**

```python
@dataclass(frozen=True)
class RecognizedDialect:
    identifier: str
    code_identity: str
    resource_identity: str | None


def bundle_simatic_sd_sources(
    sources: tuple[SourceArtifact, ...], dialect: RecognizedDialect
) -> tuple[SimaticSDBundle, ...]:
    code_sources = tuple(item for item in sources if item.input_format is InputFormat.SIMATIC_SD_CODE)
    resource_by_identity = _resource_identity_map(sources, dialect)
    return tuple(
        SimaticSDBundle(
            code=code,
            resource=resource_by_identity.get(_code_resource_identity(code, dialect)),
            diagnostics=(),
        )
        for code in code_sources
    ) + _unpaired_resource_bundles(sources, dialect)
```

`recognize_v21_dialect()` must validate the exact required V21 markers, document properties, and encoding found in the committed source. It returns `None` for any missing/mismatched marker and causes `UNSUPPORTED_SD_DIALECT`; it does not pick a "closest" version. `_code_resource_identity()` and `_resource_identity_map()` use only parsed/documented content identity. The unpaired-resource fixture must yield one `PRESERVED` bundle and `UNPAIRED_RESOURCE`, not an error that invalidates the code-only bundle.

- [ ] **Step 4: Run dialect, pairing, and non-V21 tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_dialect.py tests/test_simatic_sd_pairing.py -v -p no:cacheprovider`

Expected: PASS; code-only is valid, native resource pairing survives a renamed path, unpaired resource is preserved, and an unsupported dialect is never parsed as V21.

- [ ] **Step 5: Commit exact dialect support**

```bash
git add src/simaticml_decoder/simatic_sd.py tests/test_simatic_sd_dialect.py tests/test_simatic_sd_pairing.py
git commit -m "feat: recognize and pair V21 SIMATIC SD sources"
```

### Task 4: Parse the V21 subset losslessly and preserve comments, spans, and unknown fields

**Files:**

- Modify: `src/simaticml_decoder/simatic_sd.py`
- Create: `tests/test_simatic_sd_parser.py`
- Create: `tests/golden/simatic_sd/v21/`

**Interfaces:**

- Consumes: `SimaticSDBundle` with a recognized V21 dialect.
- Produces: `parse_v21_s7dcl(bundle, limits) -> NormalizedSDArtifact` and canonical analysis JSON.

- [ ] **Step 1: Write failing lossless-parser tests**

```python
def test_normalized_sd_analysis_retains_comment_span_and_unknown_payload():
    artifact = parse_v21_s7dcl(_resource_backed_bundle(), _sd_limits())

    assert artifact.status is ArtifactStatus.PARTIAL
    assert artifact.comments[0].source_span.start_line == _metadata("resource_backed")["comment_line"]
    assert artifact.unknown_fields[0].raw_payload == _metadata("resource_backed")["unknown_payload"]
    assert artifact.unknown_fields[0].source_span.end_byte > artifact.unknown_fields[0].source_span.start_byte
```

- [ ] **Step 2: Run it and verify it fails before V21 grammar is implemented**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_parser.py -v -p no:cacheprovider`

Expected: FAIL because candidate preservation does not yet expose structured V21 fields or raw source spans.

- [ ] **Step 3: Implement a bounded lossless scanner before semantic normalization**

```python
@dataclass(frozen=True)
class SourceSpan:
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class UnknownField:
    key: str | None
    raw_payload: str
    source_span: SourceSpan


def parse_v21_s7dcl(bundle: SimaticSDBundle, limits: ProjectLimits) -> NormalizedSDArtifact:
    tokens = tuple(_scan_v21_tokens(bundle.code.content, limits))
    document = _parse_v21_document(tokens, bundle.resource)
    return _normalize_v21_document(document, bundle.code, bundle.resource)
```

The scanner must track raw byte offsets before decoding text, reject a scalar larger than `max_sd_scalar_bytes`, reject nesting greater than `max_sd_nesting`, and stop with `SD_TOKEN_LIMIT` after `max_sd_tokens`. Use a lossless UTF-8 decode with `surrogateescape`; serialize non-text payloads using base64 plus the original byte span. Retain comments, key ordering, formatting/trivia spans, and unknown nodes as data. Never expand aliases or execute tag-like syntax.

- [ ] **Step 4: Emit and compare canonical normalized JSON goldens**

```python
def test_resource_backed_sd_analysis_matches_golden():
    actual = emit_normalized_sd_analysis(parse_v21_s7dcl(_resource_backed_bundle(), _sd_limits()))
    expected = json.loads((GOLDEN_ROOT / "resource_backed.analysis.json").read_text(encoding="utf-8"))
    assert actual == expected
```

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_parser.py -v -p no:cacheprovider`

Expected: PASS; unknown fields and comments are represented as data with source spans, not as executable content.

- [ ] **Step 5: Commit lossless normalization**

```bash
git add src/simaticml_decoder/simatic_sd.py tests/test_simatic_sd_parser.py tests/golden/simatic_sd/v21
git commit -m "feat: normalize V21 SIMATIC SD with source preservation"
```

### Task 5: Integrate SD records into the project index and cross-format comparison

**Files:**

- Modify: `src/simaticml_decoder/project.py`
- Modify: `src/simaticml_decoder/project_index.py`
- Modify: `src/simaticml_decoder/project_emit.py`
- Create: `tests/test_simatic_sd_project.py`

**Interfaces:**

- Consumes: normalized SD artifacts, the project model, and test-only cross-format mapping manifest.
- Produces: a project index where SD UDT/block/library identities are first-class artifacts with deterministic statuses and provenance.

- [ ] **Step 1: Write failing cross-format integration tests**

```python
def test_separate_simaticml_and_sd_roots_match_only_the_test_mapping_contract(tmp_path):
    xml_index = index_project(XML_ROOT, limits=ProjectLimits())
    sd_index = index_project(SD_ROOT, limits=ProjectLimits())
    mapping = load_cross_format_mapping(CORPUS_ROOT / "cross-format-map.json")

    assert mapped_identities(xml_index, sd_index, mapping) == set(mapping["identities"])
    assert XML_ROOT != SD_ROOT
```

- [ ] **Step 2: Run it and verify it fails before project orchestration registers SD**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_project.py -v -p no:cacheprovider`

Expected: FAIL because the project command currently accepts only XML artifacts.

- [ ] **Step 3: Register the adapter without weakening XML behavior**

```python
def index_project(root: Path, *, limits: ProjectLimits = DEFAULT_PROJECT_LIMITS) -> ProjectIndex:
    discovery = discover_project_files(root, {
        ".xml": InputFormat.SIMATICML_XML,
        ".s7dcl": InputFormat.SIMATIC_SD_CODE,
        ".s7res": InputFormat.SIMATIC_SD_RESOURCE,
    }, limits)
    parsed = tuple(_parse_candidate(item, limits) for item in discovery.files)
    return index_project_artifacts(_records(parsed, discovery.diagnostics), limits)
```

`_parse_candidate()` routes XML to the V21 SimaticML adapter and SD candidates to the preservation/dialect/parser pipeline. The mapping manifest stays under `tests/` and is never imported by package code. Missing SD semantics produce `PRESERVED`/`PARTIAL` records with diagnostics rather than causing XML artifacts to disappear.

- [ ] **Step 4: Extend project emission with source provenance and optional raw-input preservation**

`project_emit.py` must emit a source object containing `relative_path`, `format`, `sha256`, `byte_size`, and byte/line spans. When `--preserve-input-source` is selected, atomically copy the supplied bytes beneath `output/original-input/` using the same relative path; write `preserved_from_input: true` and `reimportable: false` in the manifest. This feature never alters content or claims it can be re-imported.

- [ ] **Step 5: Run integration and project regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_project.py tests/test_project_*.py -v -p no:cacheprovider`

Expected: PASS; each root is independently indexed, mapping comparisons are test-only, and existing SimaticML output remains stable.

- [ ] **Step 6: Commit project integration**

```bash
git add src/simaticml_decoder/project.py src/simaticml_decoder/project_index.py src/simaticml_decoder/project_emit.py tests/test_simatic_sd_project.py
git commit -m "feat: index V21 SIMATIC SD project artifacts"
```

### Task 6: Expose SD behavior through the CLI with explicit safety and fidelity metadata

**Files:**

- Modify: `src/simaticml_decoder/cli.py`
- Create: `tests/test_simatic_sd_cli.py`
- Modify: `README.md`
- Modify: `docs/PROJECT_INPUT_CONTRACT.md`

**Interfaces:**

- Consumes: project indexing and `ProjectLimits` with SD limits.
- Produces: clear CLI flags, nonzero exits for failed artifacts, and public V21-only support documentation.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_project_cli_accepts_code_only_sd_and_marks_it_non_reimportable(tmp_path):
    code_only_root = SD_ROOT / "code_only"
    assert cli.main(["--project", str(code_only_root), "-o", str(tmp_path), "-q"]) == 0

    manifest = json.loads((tmp_path / "project-manifest.json").read_text(encoding="utf-8"))
    assert manifest["output_contract"]["fidelity"] == "preservation-plus-analysis"
    assert manifest["output_contract"]["reimportable"] is False


def test_project_cli_reports_sd_nesting_limit_without_leaving_root(tmp_path):
    exit_code = cli.main(["--project", str(SD_ROOT), "--max-sd-nesting", "1", "-o", str(tmp_path), "-q"])
    assert exit_code != 0
    manifest = json.loads((tmp_path / "project-manifest.json").read_text(encoding="utf-8"))
    assert any(item["code"] == "sd-nesting-limit" for item in manifest["diagnostics"])
```

- [ ] **Step 2: Run the tests and verify the missing flags/contracts fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_cli.py -v -p no:cacheprovider`

Expected: FAIL until project mode accepts SD and exposes the documented budget.

- [ ] **Step 3: Add exact CLI arguments and status behavior**

```python
p.add_argument("--max-sd-tokens", type=int, default=ProjectLimits().max_sd_tokens)
p.add_argument("--max-sd-nesting", type=int, default=ProjectLimits().max_sd_nesting)
p.add_argument("--max-sd-scalar-bytes", type=int, default=ProjectLimits().max_sd_scalar_bytes)
p.add_argument("--preserve-input-source", action="store_true")
```

`--project` accepts a root containing either or both supported V21 input formats. It writes a deterministic manifest even when an SD artifact is failed/preserved, returns nonzero for a failed artifact or limit breach, and never processes a source outside the project root. Legacy `PATH` block/batch mode stays XML-only.

- [ ] **Step 4: Update public docs to match actual capability**

Document code-only `.s7dcl` support, optional `.s7res`, the observed pairing rule by identifier, all SD limits, source-preservation behavior, preservation-only fallback, and non-re-importability. State explicitly that "YAML-like" describes the Siemens format here; generic YAML files are unsupported.

- [ ] **Step 5: Run CLI and existing regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_cli.py tests/test_project_cli.py tests/test_cli.py -v -p no:cacheprovider`

Expected: PASS; code-only SD succeeds, unpaired resource is diagnosable, and legacy XML CLI behavior is unchanged.

- [ ] **Step 6: Commit the CLI contract**

```bash
git add src/simaticml_decoder/cli.py tests/test_simatic_sd_cli.py README.md docs/PROJECT_INPUT_CONTRACT.md
git commit -m "docs: expose V21 SIMATIC SD input contract"
```

### Task 7: Complete security and quality verification for the adapter

**Files:**

- Create: `tests/test_simatic_sd_limits.py`
- Modify: `pyproject.toml` or `.github/workflows/ci.yml` only if the shared 80% gate is not yet active.

**Interfaces:**

- Consumes: adapter, project limits, native corpus, and quality tooling.
- Produces: reproducible safety and coverage evidence for AC-010 through AC-013.

- [ ] **Step 1: Write independent parser-budget tests**

```python
@pytest.mark.parametrize(
    ("source_bytes", "limits", "expected_code"),
    [
        (b"x" * 1025, replace(_sd_limits(), max_sd_scalar_bytes=1024), "sd-scalar-limit"),
        (_nested_source(3), replace(_sd_limits(), max_sd_nesting=2), "sd-nesting-limit"),
        (_many_tokens_source(5), replace(_sd_limits(), max_sd_tokens=4), "sd-token-limit"),
    ],
)
def test_sd_limits_stop_before_unbounded_normalization(source_bytes, limits, expected_code):
    result = parse_v21_s7dcl(_bundle_from_bytes(source_bytes), limits)
    assert result.diagnostics[0].code.value == expected_code
```

- [ ] **Step 2: Run parser limits and all SD tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_simatic_sd_limits.py tests/test_simatic_sd_*.py -v -p no:cacheprovider`

Expected: PASS; every independent breach returns the named diagnostic without a crash or a fixture skip.

- [ ] **Step 3: Run the immediate-scope repository quality gate**

Run: `./.venv/Scripts/python.exe -m pytest -v -p no:cacheprovider --cov=src/simaticml_decoder --cov-fail-under=80`

Expected: PASS.

Run: `./.venv/Scripts/python.exe -m ruff check src tests`

Expected: PASS.

- [ ] **Step 4: Commit verification changes when present**

```bash
git add tests/test_simatic_sd_limits.py pyproject.toml .github/workflows/ci.yml
git commit -m "test: verify SIMATIC SD parser limits"
```

## Self-Review

- AC coverage: Task 1 establishes two separate export roots and a test-only mapping. Tasks 2–4 cover code-only intake, optional resources, dialect proof, source preservation, unknown fields, and parser budgets. Tasks 5–6 integrate the project and CLI. Task 7 proves security/quality behavior.
- Pairing safety: no task uses basename or directory adjacency as association evidence; code-only succeeds; unpaired resource remains visible.
- Fidelity: the plan retains raw source/trivia and normalized analysis, but never calls output re-importable or invokes a generic YAML parser.
- Type consistency: all project-level state comes from the project-ingestion plan's immutable types; raw bytes are encapsulated in `SourceArtifact`, not injected into the index manifest.
- Scope: GRAPH, generated TIA import files, and unsupported/unknown SIMATIC SD dialects remain out of the immediate support claim.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-v21-simatic-sd-adapter.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task and review raw-source handling before semantic parsing.
2. **Inline Execution** — execute the tasks in this session in small TDD batches with review checkpoints.
