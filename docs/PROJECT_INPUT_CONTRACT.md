# Project-mode input contract (V21)

This is the public contract for `simaticml-decode --project ROOT` --
project-scale ingestion of a whole exported SimaticML project tree, as
opposed to the legacy single-block/directory mode described in the main
[README](../README.md). It documents what project mode accepts, how it
classifies and bounds input, what it emits, and what it explicitly does
**not** promise. Nothing here changes or supersedes the main README's
"Fixture provenance and compatibility" or "Untrusted-input policy" sections;
project mode reuses the same untrusted-input walk and the same fixture
corpus, with the same provenance caveats.

## Compatibility profile: V21 only

Project mode translates **TIA Portal V21** SimaticML exports only. Every
discovered `.xml` artifact is adapted independently:

- A recognized `SW.Blocks.*` export (FC/FB/DB/OB) or `SW.Types.PlcStruct`
  (UDT) export whose `Engineering` version string contains `V21` is
  translated normally (`ArtifactStatus.COMPLETE`, or `PARTIAL`/`PRESERVED`
  per the usual per-file decode outcome).
- The **same** recognized export with an engineering version that does
  **not** contain `V21` is preserved, not translated: it is recorded with
  `ArtifactStatus.PRESERVED` and a `DiagnosticCode.UNSUPPORTED_TIA_VERSION`
  diagnostic (severity `warning`) naming the version found.
- A recognized export with **no** engineering version at all -- so V21
  cannot even be confirmed -- is likewise preserved, with
  `DiagnosticCode.UNKNOWN_TIA_VERSION` instead.

In both non-V21 cases the artifact is still discovered, identified, and
carries a diagnostic -- it is never silently dropped, and it is never
force-translated on the assumption that non-V21 exports share V21's schema.

Artifacts that are not a `SW.Blocks.*`/`SW.Types.PlcStruct` export at all
(for example a `SW.Tags.PlcTagTable` tag-table export) are preserved with
`DiagnosticCode.UNSUPPORTED_ARTIFACT` regardless of version, following the
same "preserve with diagnostic, never drop" rule.

## Canonical relative-path meaning

Every `SourceLocation.relative_path` is a `PurePosixPath`: forward-slash
separated, POSIX-normalized, and **root-relative** -- relative to the
`ROOT` directory passed to `--project`, never to the current working
directory, the output directory, or any absolute filesystem path. This
holds uniformly on Windows and POSIX hosts: a Windows path such as
`PLC_1\Program blocks\Main.xml` is normalized to
`PLC_1/Program blocks/Main.xml` before it ever reaches a `SourceLocation`.
The manifest never contains an absolute path, a drive letter, or a raw
`os.sep`-joined string.

## `--library-root` selection semantics

By default, an artifact's `ArtifactOrigin` follows a path convention:
anything under a `Types/` subtree is `PROJECT_LIBRARY`, anything under a
`PLC_1/` (or other station) subtree is `USER`, and anything matching
neither is `UNKNOWN`.

`--library-root RELATIVE_PATH` (repeatable) overrides that convention:
every artifact whose `relative_path` falls under one of the given roots is
reclassified as `ArtifactOrigin.PROJECT_LIBRARY`, regardless of what the
path-convention default would have produced. Explicit CLI intent always
wins over the convention.

Each `--library-root` value must be a **normalized relative path under the
project root**:

- An absolute path (e.g. `/etc/passwd`, `C:\...`) is rejected.
- A path containing a `..` segment (e.g. `../escape`) is rejected.

A rejected value never raises, never aborts the run, and never silently
disappears: it produces a `DiagnosticCode.OUTSIDE_ROOT` diagnostic (severity
`error`) and is simply excluded from the set of roots applied -- every other
artifact is still classified normally. When no `--library-root` is given
at all, origin classification is exactly the Task 3 path-convention
default; this is a strict no-op for the common case.

## Symlink and traversal policy

Project-mode discovery reuses the same handle-anchored, TOCTOU-resistant
walk documented in the README's "Untrusted-input policy" section:

- Every export is treated as untrusted.
- Directory scans are handle-anchored per platform: on Windows the root is
  opened once via native NT handles and every child is enumerated/opened
  relative to its parent's own handle, never by re-resolving a path string;
  on POSIX, file descriptors and `O_NOFOLLOW` ensure traversal never
  follows a symlink.
- Every reparse point (junction, symlink, mount point) encountered during
  enumeration is rejected, and symlinked *directories* are never followed
  regardless of depth. `ProjectLimits.follow_symlinks` defaults to `False`;
  project mode's discovery has no supported way to opt back into following
  symlinks.
- A direct or discovered symlink is rejected with
  `DiagnosticCode.SYMLINK_SKIPPED`.
- Platforms without descriptor-relative filesystem support
  (`os.supports_dir_fd/os.supports_follow_symlinks` unavailable) reject
  directory input outright rather than silently falling back to
  path-based traversal.
- A directory that changes while being scanned aborts before any
  discovered file already found is decoded, rather than producing a
  partial-but-unflagged result.

## Default budgets (`ProjectLimits`)

Every numeric budget below is enforced during discovery/adaptation/
resolution and defaults to the value `project_model.ProjectLimits` ships
with; each is independently overridable on the CLI (`--max-files`,
`--max-file-bytes`, `--max-total-bytes`, `--max-depth`,
`--max-xml-elements`, `--max-xml-depth`, `--max-reference-edges`):

| Limit | Default | Exceeding it produces |
|---|---|---|
| `max_files` | `10_000` | `DiagnosticCode.FILE_COUNT_LIMIT` |
| `max_file_bytes` | `16 * 1024 * 1024` (16 MiB) | `DiagnosticCode.FILE_SIZE_LIMIT` |
| `max_total_bytes` | `512 * 1024 * 1024` (512 MiB) | `DiagnosticCode.TOTAL_SIZE_LIMIT` |
| `max_relative_depth` | `32` | `DiagnosticCode.DEPTH_LIMIT` |
| `max_xml_elements` | `500_000` | `DiagnosticCode.XML_ELEMENT_LIMIT` |
| `max_xml_depth` | `128` | `DiagnosticCode.XML_DEPTH_LIMIT` |
| `max_reference_edges` | `100_000` | `DiagnosticCode.REFERENCE_EDGE_LIMIT` |

(`ProjectLimits` also carries a non-numeric `follow_symlinks: bool = False`
flag, covered above.) Inputs that exceed a limit are rejected -- never
truncated -- and the corresponding diagnostic is attached at the point the
limit was reached.

## Status vocabulary

Every `ArtifactRecord.status` is exactly one of four values:

- `complete` -- fully translated with no loss.
- `partial` -- translated, but some content within the artifact could not
  be rendered/resolved.
- `preserved` -- discovered and identified, but not translated at all (a
  non-V21/unknown-version export, a recognized-but-unsupported artifact
  kind, or similar).
- `failed` -- discovery/adaptation could not produce a usable record at
  all (e.g. malformed XML).

**Any status other than `complete` always carries at least one
`ProjectDiagnostic`** explaining why. `complete` may have zero diagnostics
attached to the artifact itself, but the project's overall
`ProjectIndex.diagnostics` can still be non-empty independently (e.g.
unresolved references originating from a different artifact).

## Diagnostic codes

`DiagnosticCode` is a closed, 16-value enum. There is no catch-all/"other"
code -- every diagnostic project mode emits carries one of these exact
values:

| Code | Meaning |
|---|---|
| `outside_root` | An `--library-root` value was absolute or escaped the project root via `..` and was ignored. |
| `symlink_skipped` | A symlink or other reparse point was rejected during discovery. |
| `file_count_limit` | `max_files` was reached; remaining files were not discovered. |
| `file_size_limit` | A single file exceeded `max_file_bytes` and was rejected. |
| `total_size_limit` | The combined size of discovered files exceeded `max_total_bytes`. |
| `depth_limit` | A path exceeded `max_relative_depth` directory levels under `ROOT`. |
| `xml_element_limit` | An artifact's XML exceeded `max_xml_elements` elements. |
| `xml_depth_limit` | An artifact's XML exceeded `max_xml_depth` nesting levels. |
| `reference_edge_limit` | `max_reference_edges` was reached; remaining references were not resolved. |
| `malformed_xml` | An artifact's XML failed to parse. |
| `unsupported_artifact` | The XML parsed but its root element(s) are not a recognized SimaticML block or UDT export. |
| `unsupported_tia_version` | A recognized export's engineering version does not contain `V21`. |
| `unknown_tia_version` | A recognized export has no engineering version at all. |
| `duplicate_identity` | Two or more artifacts share the same `QualifiedIdentity` key; none of them is used as a reference-resolution candidate. |
| `unresolved_reference` | A block-call or UDT-member reference names no matching artifact. |
| `ambiguous_reference` | A reference matches two or more candidate artifacts; resolution never guesses via a first-match or origin-based tie-break. |

## Partial-success exit behavior

`--project` mode's process exit code is independent of the legacy
single-file/directory mode's exit code, but follows the same shape:

- **`0`** -- the run completed and **no** artifact has
  `ArtifactStatus.FAILED` (artifacts that are `partial`/`preserved` do not
  by themselves make the run fail -- they still produced a usable record).
- **`1`** -- at least one artifact has `ArtifactStatus.FAILED`.
- **`2`** -- CLI usage error: neither `PATH` nor `--project` was given, or
  both were given in the same invocation (`cli.py`'s
  exactly-one-of-PATH-or-`--project` enforcement). This is a pure
  argument-parsing failure, raised before any discovery/indexing happens,
  and is unrelated to artifact status.

## Deterministic ordering

Repeated runs of `--project` over the same input tree, with the same
limits and the same `--library-root` values, produce a **byte-identical**
`project-manifest.json`. Discovery, adaptation, origin override, and
resolution are all single-threaded, synchronous, comprehension-based
transformations over already-produced tuples -- no threads, no
multiprocessing, no unordered `dict`/`set` iteration ever reaches an
output field. Where order could otherwise depend on incidental filesystem
enumeration order (diagnostics, resolved reference edges), the index
explicitly sorts by a stable key (location, then code/identity, then
message) before returning. `tests/test_project_corpus_integrity.py`'s
golden-manifest test is the regression guard for this property: it asserts
the committed V21 fixture corpus reproduces the committed golden manifest
byte-for-byte.

## Source-location meaning

A `SourceLocation` is always **file + optional element**, never a line or
column number:

- `relative_path` -- the root-relative POSIX path of the artifact's file
  (see above).
- `element_id` -- an optional stable identifier for a specific element
  inside that file (e.g. an network/UID-scoped identifier), or `None` when
  the location refers to the whole file. Project mode never reports a line
  number, because SimaticML's XML representation of a `FlgNet` network or
  UDT member has no meaningful "line" in the way a text-based language
  would -- an element identifier is the only stable, structure-native
  handle available.

## Analysis-only, non-re-importable output contract

`emit_project_manifest()`'s output always includes an explicit
`output_contract` field:

```json
"output_contract": {
  "fidelity": "analysis-only",
  "reimportable": false
}
```

This is not a placeholder: **the manifest cannot regenerate a TIA
project.** It carries identity, status, location, diagnostics, and
resolved reference edges -- never a content hash, never enough structural
detail to reconstruct the original SimaticML XML, and never a write path
back into a TIA Portal project. Any downstream consumer must treat
`project-manifest.json` purely as a read-only analysis artifact.

## GRAPH deferral

Project mode never folds or renders a block's networks at all -- it never
calls `fold.fold_block()` or `emit.emit_scl()`/`emit.emit_sidecar()` (see
`cli.py`'s `_main_project()`). It only performs structural
identification: parsing enough of an artifact's XML to derive its
identity, status, location, diagnostics, and outgoing references. GRAPH
(SFC) networks -- like STL networks -- are therefore out of scope for
project mode in this release in exactly the same sense the main README
already documents for legacy single-block mode: parsed losslessly where a
block is otherwise recognized as V21 and translatable, but never folded or
rendered. GRAPH/SFC support is not implemented for either mode.

## No re-importability claim

To restate unambiguously: nothing produced by `--project` mode -- the
`project-manifest.json` file, any diagnostic, any resolved reference edge
-- can be fed back into TIA Portal, Openness, or any other tool to
regenerate or modify the original SimaticML project. Project mode is a
one-way, read-only analysis pipeline over an already-exported project
tree.
