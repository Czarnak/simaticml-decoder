# Native Windows Handle-Anchored Traversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Windows directory traversal from decoding files reached by a symlink, junction, reparse point, or pathname swap.

**Architecture:** Introduce a Windows-only `ctypes` adapter that opens a root directory once, enumerates it by handle, and opens every child relative to that root handle. Discovery yields immutable `InputArtifact` values whose readers consume existing native file handles; the CLI never converts a discovered artifact back into a filesystem pathname. Non-Windows directory discovery uses descriptor-relative APIs only when they are available and otherwise fails closed.

**Tech Stack:** Python 3.11–3.14 standard library, `ctypes`, `ntdll.dll`, `kernel32.dll`, pytest, pytest-cov, ruff. No runtime dependency added.

## Global Constraints

- Reject all final and intermediate reparse points, symlinks, junctions, and mount points; never pair SD files across roots.
- Keep `InputLimits`, artifacts, and native-entry values frozen. Handles must close deterministically via context managers.
- Preserve limits, deterministic lexical ordering, redacted diagnostic messages, and the 80% coverage gate.
- Preserve Phase 0 fixture labels: only `preserved-only` and `unsupported`.

---

### Task 1: Add the immutable artifact contract

**Files:**
- Create: `src/simaticml_decoder/windows_handles.py`
- Modify: `src/simaticml_decoder/input_policy.py:20-190`
- Test: `tests/test_input_policy.py`

**Interfaces:** `InputArtifact(relative_path: PurePath, suffix: str, _reader: Callable[[InputLimits], bytes])`, `direct_input_artifact(path: Path)`, and `discover_input_files(...) -> tuple[InputArtifact, ...]`.

- [x] **Step 1: Write failing tests**

```python
def test_discovered_artifact_is_relative(tmp_path):
    root = tmp_path / "root"
    source = root / "nested" / "block.xml"
    source.parent.mkdir(parents=True)
    source.write_text("<Document/>", encoding="utf-8")
    artifact = discover_input_files(root, recursive=True)[0]
    assert artifact.relative_path == PurePath("nested") / "block.xml"
    assert not artifact.relative_path.is_absolute()


def test_artifact_read_is_limited(tmp_path):
    source = tmp_path / "block.xml"
    source.write_bytes(b"x" * 11)
    with pytest.raises(InputViolation, match="file_too_large"):
        direct_input_artifact(source).read_bytes(InputLimits(max_file_bytes=10))
```

- [x] **Step 2: Verify red**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_input_policy.py -k artifact -q -p no:cacheprovider`

Expected: FAIL during collection because the artifact API does not exist.

- [x] **Step 3: Implement the contract**

```python
@dataclass(frozen=True)
class InputArtifact:
    relative_path: PurePath
    suffix: str
    _reader: Callable[[InputLimits], bytes] = field(repr=False, compare=False)

    def read_bytes(self, limits: InputLimits) -> bytes:
        return self._reader(limits)
```

Keep direct-file reads descriptor-pinned. Move format handling to `validate_artifact_format(artifact)` so `.xml`, `.s7dcl`, and `.s7res` get identical direct and directory diagnostics.

- [x] **Step 4: Verify green and commit**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_input_policy.py -k artifact -q -p no:cacheprovider`

Expected: PASS.

Commit: `git add src/simaticml_decoder/input_policy.py src/simaticml_decoder/windows_handles.py tests/test_input_policy.py && git commit -m "feat: add immutable input artifacts"`

### Task 2: Implement native Windows handles

**Files:**
- Create: `src/simaticml_decoder/windows_handles.py`
- Test: `tests/test_windows_handles.py`

**Interfaces:** `NativeDirectory.open_root(path)`, `NativeDirectory.entries() -> tuple[NativeEntry, ...]`, `NativeDirectory.open_child(name, directory)`, and `NativeHandle.read_limited(limit)`.

- [x] **Step 1: Write failing Windows integration tests**

```python
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows native handles")


def test_native_enumeration_rejects_junction(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "jump"), str(outside)], check=True)
    with pytest.raises(InputViolation, match="symlink_not_allowed"):
        NativeDirectory.open_root(root).entries()


def test_opened_child_survives_name_swap(tmp_path):
    (tmp_path / "block.xml").write_text("<Document/>", encoding="utf-8")
    with NativeDirectory.open_root(tmp_path) as root:
        child = root.open_child("block.xml", directory=False)
        os.replace(tmp_path / "block.xml", tmp_path / "moved.xml")
        assert child.read_limited(1024) == b"<Document/>"
```

- [x] **Step 2: Verify red**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_windows_handles.py -q -p no:cacheprovider`

Expected on Windows: FAIL during collection because `NativeDirectory` is absent. Expected elsewhere: tests skip with `Windows native handles`.

- [x] **Step 3: Implement FFI**

Define `UNICODE_STRING`, `OBJECT_ATTRIBUTES`, `IO_STATUS_BLOCK`, and `FILE_ID_BOTH_DIR_INFORMATION` using exact `ctypes` field widths. `NtCreateFile` opens root and children relative to `RootDirectory`; reject child names containing separators, `.` or `..`. Use `FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT` for directories and `FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT` for files. Request `SYNCHRONIZE | FILE_READ_ATTRIBUTES` plus `FILE_LIST_DIRECTORY` or `FILE_READ_DATA`; use read/write/delete sharing and `FILE_OPEN`. Enumerate only with `NtQueryDirectoryFile(FileIdBothDirectoryInformation)`, reject every `FILE_ATTRIBUTE_REPARSE_POINT`, sort names, and return a tuple. Read at most `limit + 1` bytes with `ReadFile`; map native failures to redacted `InputViolation` codes.

- [x] **Step 4: Verify green and commit**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_windows_handles.py -q -p no:cacheprovider`

Expected on Windows: PASS. Expected elsewhere: platform-only skips.

Commit: `git add src/simaticml_decoder/windows_handles.py tests/test_windows_handles.py && git commit -m "feat: anchor Windows traversal to native handles"`

### Task 3: Make directory CLI dispatch artifact-backed

**Files:**
- Modify: `src/simaticml_decoder/input_policy.py:91-190`
- Modify: `src/simaticml_decoder/cli.py:83-152`
- Test: `tests/test_input_policy.py`
- Test: `tests/test_cli.py`

**Interfaces:** Add `decode_artifact(artifact, out_dir, fmt)`. Keep `decode_file(path, out_dir, fmt)` as a direct-artifact wrapper. Build output paths from `artifact.relative_path.parent`.

- [x] **Step 1: Write failing end-to-end tests**

```python
def test_directory_reports_all_unpaired_resources(capsys):
    assert cli.main(["tests/fixtures/SimaticSD_s7res", "-q"]) == 1
    assert capsys.readouterr().err.count("SD_RESOURCE_WITHOUT_DCL") == 6


def test_directory_output_uses_artifact_relative_path(tmp_path):
    root = tmp_path / "in"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    shutil.copy(COMMITTED_FC_CARGADOR, nested / "block.xml")
    assert cli.main([str(root), "-o", str(tmp_path / "out"), "-q"]) == 0
    assert (tmp_path / "out" / "a" / "b" / "block.scl").is_file()
```

- [x] **Step 2: Verify red**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_cli.py tests/test_input_policy.py -k "artifact or unpaired" -q -p no:cacheprovider`

Expected: FAIL because directory mode still calls `decode_file` with re-resolved `Path` values.

- [x] **Step 3: Implement artifact dispatch**

```python
def decode_artifact(source: InputArtifact, out_dir: Path, fmt: str) -> FileOutcome:
    try:
        validate_artifact_format(source)
        doc = parse.parse_document(parse_xml_bytes(source.read_bytes(DEFAULT_LIMITS)))
    except InputViolation as exc:
        return FileOutcome(source.relative_path, "error", error=_input_error(source.relative_path, exc))
```

Retain the current fold/emit isolation. Hold the root native handle open through the full discovery/decode batch. Non-Windows uses `dir_fd` plus `O_NOFOLLOW`; if either is unavailable, return `INPUT_REJECTED` before decoding a directory.

- [x] **Step 4: Verify green and commit**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_cli.py tests/test_input_policy.py -k "artifact or unpaired" -q -p no:cacheprovider`

Expected: PASS; exactly six resource-only diagnostics and no cross-root file access.

Commit: `git add src/simaticml_decoder/input_policy.py src/simaticml_decoder/cli.py tests/test_input_policy.py tests/test_cli.py && git commit -m "fix: dispatch secure directory artifacts"`

### Task 4: Document, test in CI, and verify

**Files:**
- Modify: `README.md:68-92`
- Modify: `tests/test_fixture_corpus.py:100-130`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`

- [x] **Step 1: Add failing same-root and Windows-CI checks**

```python
def test_unpaired_resources_have_no_same_root_declaration():
    root = CORPUS_ROOT / "SimaticSD_s7res"
    for relative in _manifest()["unpaired_resources"]:
        resource = root / Path(relative).relative_to("SimaticSD_s7res")
        assert not resource.with_suffix(".s7dcl").exists()
```

Add `windows-lint-and-test` on `windows-latest`, Python 3.11, editable dev install, `ruff check .`, and `pytest -q --cov=simaticml_decoder --cov-fail-under=80`.

- [x] **Step 2: Verify red**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_fixture_corpus.py -k same_root -q -p no:cacheprovider`

Expected: FAIL until the assertion and Windows CI job exist.

- [x] **Step 3: Update public policy**

State that Windows directory discovery is handle-anchored and rejects all reparse points without re-resolving a discovered artifact. State that unsupported platforms reject directory input. Retain all byte, traversal, XML, SD, and redaction limits.

- [x] **Step 4: Verify and commit**

Run: `.venv\\Scripts\\python.exe -m ruff check src tests`

Expected: `All checks passed!`

Run: `.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider --cov=simaticml_decoder --cov-report=term-missing --cov-fail-under=80`

Expected: all tests pass and coverage is at least 80%.

Run: `.venv\\Scripts\\python.exe -m pip_audit`

Expected: `No known vulnerabilities found`.

Run: `graphify update .`

Expected: `Code graph updated.`

Commit: `git add README.md .github/workflows/ci.yml .github/workflows/release.yml tests/test_fixture_corpus.py graphify-out && git commit -m "ci: verify native secure traversal"`

## Plan Self-Review

- Native handles replace every unsafe directory-path boundary: root open, enumeration, child open, and file read.
- Each task starts red, has a concrete green command, and ends with an independently reviewable commit.
- The plan fails closed on platforms without secure descriptor-relative traversal and preserves Phase 0 corpus behavior.

## Completion Notes

All four tasks landed on `main`: `9bd14d3` (Task 1), `833deda` + `0824515` (Task 2, the latter fixing a cross-platform
test-collection break caught before merge), `a74792b` (Task 3), `3356d51` (Task 4). An independent code review over
`97fbf8d..3356d51` found no Critical issues and two Important ones (handles held open for the whole batch instead of
per-read; Windows `open_child` not re-checking a freshly-opened handle for a reparse point), both fixed in `cf680ad`.
Durable knowledge from this cycle is captured under `docs/superpowers/memory/` (module card, contract, decision, two
lessons) — see `docs/superpowers/memory/reports/2026-07-13-native-windows-handle-traversal.md`.

Two implementation details evolved beyond the plan's illustrative pseudocode: `parse_xml_bytes` was not introduced as a
separate function (the artifact reader closures already return fully-validated UTF-8 bytes, so `decode_artifact` decodes
and calls `parse.parse_document` directly); `InputArtifact` gained a fourth field, `has_declaration: bool`, so the
`.s7res`/`.s7dcl` same-root check reuses the directory listing already obtained during discovery instead of touching the
filesystem again.
