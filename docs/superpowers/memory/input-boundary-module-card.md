---
type: module_card
title: Untrusted-input boundary (input_policy.py + windows_handles.py)
summary: How the CLI turns an untrusted path/directory into validated bytes without ever letting a discovered file be re-opened by name.
tags:
  - security
  - input-boundary
  - cli
owned_paths:
  - src/simaticml_decoder/input_policy.py
  - src/simaticml_decoder/windows_handles.py
related_docs:
  - docs/superpowers/memory/artifact-traversal-contract.md
  - docs/superpowers/memory/native-handle-traversal-decision.md
entrypoints:
  - src/simaticml_decoder/input_policy.py:discover_input_files
  - src/simaticml_decoder/input_policy.py:direct_input_artifact
  - src/simaticml_decoder/input_policy.py:read_xml
  - src/simaticml_decoder/windows_handles.py:NativeDirectory
last_verified_commit: cf680ad
status: active
---

## Responsibilities

- `input_policy.py` is the single boundary between "an untrusted path/directory the CLI was pointed at" and "validated bytes safe to hand to `parse.parse_document`." Nothing outside this module should touch `os.stat`/`os.open`/native handles directly for CLI input.
- Two independent entry paths exist and are validated differently:
  - **Direct single-file mode** (`simaticml-decode some.xml`): `direct_input_artifact(path)` / `read_xml(path, limits)`. Still fully path-based — opens by path once, pins the descriptor, re-checks `os.fstat` against the pre-open `lstat` to catch a swap (`input_changed`).
  - **Directory/bulk mode** (`simaticml-decode some_dir/`): `discover_input_files(root, recursive, limits)`. Handle/descriptor-anchored — see the contract doc for the invariant this must never violate.
- `windows_handles.py` is a Windows-only `ctypes`/NTAPI adapter (`NativeDirectory`, `NativeHandle`) used only by `input_policy.py`'s directory-mode Windows branch. It is never imported unconditionally at another module's top level (see Lessons).

## Invariants

- A discovered `InputArtifact` (from `discover_input_files`) is never converted back into a `Path`/string and reopened by name to read its content — see [[artifact-traversal-contract]].
- Every `InputViolation` code/message discovered-vs-direct paths raise for the *same* underlying problem must read identically (e.g. `symlink_not_allowed`, `file_too_large`, `xml_forbidden_declaration`) — diagnostics tests assert exact stderr text, not just "an error occurred."
- `.s7res` without a same-root `.s7dcl` sibling → `SD_RESOURCE_WITHOUT_DCL`, computed from data already gathered during the same directory listing (never a second filesystem touch) in directory mode; from a live sibling-file check in direct mode.
- All native handles/fds opened during a walk must be closed no later than the one read that consumes them (see `_make_handle_reader`, `cf680ad`) — do not rely solely on `__del__` to bound resource usage on large trees.

## Extension points

- A new discovered-file suffix: add to `_ARTIFACT_SUFFIXES` in `input_policy.py` and to `validate_artifact_format`; both the Windows and POSIX walk functions consume that same set, so no platform-specific duplication is needed.
- A new platform's descriptor-relative traversal: add a `_discover_<platform>` function mirroring `_discover_windows`/`_discover_posix`'s shape (walk one directory handle/fd at a time, build `InputArtifact`s with reader closures bound to already-open handles) and branch to it from `discover_input_files`. Never fall back to path-based traversal for directory mode — fail closed with `InputViolation("unsupported_platform", ...)` instead (see [[native-handle-traversal-decision]]).

## Common pitfalls

- Importing `windows_handles` unconditionally at another module's top level breaks pytest collection (and CI) on non-Windows — it raises `RuntimeError` at import time by design. Always guard with `if sys.platform == "win32":` at the point of import, including in test files (a `pytestmark = pytest.mark.skipif(...)` alone does NOT stop the module from being imported during collection).
- Adding a new "does X exist" check for a discovered artifact (like the `.s7res`/`.s7dcl` pairing) by re-touching the filesystem via a composed path reopens the exact TOCTOU window this module exists to close. Bake the answer into data already gathered from the same directory listing instead (see `has_declaration` on `InputArtifact`).
- `discover_xml`/`_discover`/`validate_input_file` (old path-based helpers) are still present and still tested directly, but are dead from the production CLI's perspective as of `a74792b` — `cli.py` no longer calls them. Known, not yet cleaned up (see review report `cf680ad` follow-up notes).
