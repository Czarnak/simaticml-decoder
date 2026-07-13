---
type: contract
title: InputArtifact discovery-to-read contract
summary: The non-negotiable rule that makes directory-mode discovery TOCTOU-resistant — never re-resolve a discovered artifact to a path.
tags:
  - security
  - input-boundary
owned_paths:
  - src/simaticml_decoder/input_policy.py
  - src/simaticml_decoder/cli.py
related_docs:
  - docs/superpowers/memory/input-boundary-module-card.md
  - docs/superpowers/memory/native-handle-traversal-decision.md
entrypoints:
  - src/simaticml_decoder/input_policy.py:InputArtifact
  - src/simaticml_decoder/cli.py:decode_artifact
last_verified_commit: cf680ad
status: active
---

## Scope

Applies to every `InputArtifact` produced by `discover_input_files()` (directory/bulk CLI mode). Does not apply to `direct_input_artifact()` (single-file CLI mode), which is intentionally still path-based and re-validates against a live `os.fstat` on each call.

## Producers and consumers

- Producer: `input_policy.discover_input_files()` — platform-branches to `_discover_windows` (native NT handles via `windows_handles.NativeDirectory`) or `_discover_posix` (`dir_fd` + `O_NOFOLLOW`).
- Consumer: `cli.decode_artifact(source: InputArtifact, out_dir, fmt)` — the only place directory-mode artifacts are read and turned into output files.

## The rule

`InputArtifact.relative_path` may be read for:
- building the output directory (`cli._dest_dir`: `out_root / relative_path.parent`)
- diagnostic/report text (`safe_text(...)`)

`InputArtifact.relative_path` must never be:
- passed to `Path()`, `open()`, or `os.open()` to re-read the artifact's content.

The only way to get the artifact's bytes is `artifact.read_bytes(limits)`, which calls a reader closure captured **at discovery time**, bound to a handle/descriptor that was already opened during the same walk that discovered the file (`_make_handle_reader`, closing over a `windows_handles.NativeHandle` or POSIX `_PosixFileHandle`). No code path between discovery and read may reconstruct a filesystem path for that file.

## Invariants

- A rename/junction-swap that happens *after* discovery but *before* `read_bytes()` is called cannot redirect the read: the handle/fd already anchors the original file-system object (Windows: proven by `test_opened_child_survives_name_swap`; POSIX: `O_NOFOLLOW` is kernel-atomic at open time).
- Every reader-closure handle/fd is closed no later than the single `read_bytes()` call that consumes it (fixed in `cf680ad` — previously handles survived until batch end via `__del__` only).
- `has_declaration` (the `.s7res`/`.s7dcl` same-root pairing flag) is computed from the same directory listing that discovered the artifact — never a second filesystem stat.
- Platforms without descriptor-relative traversal support fail closed (`InputViolation("unsupported_platform", ...)`) rather than silently falling back to path-based (TOCTOU-vulnerable) discovery.

## Compatibility notes

- `discover_input_files()`'s return type changed from `list[Path]` to `tuple[InputArtifact, ...]` in `9bd14d3`/`a74792b`. This is a breaking change to a public-ish function, accepted because the package is pre-1.0 alpha (`pyproject.toml` classifiers) with no external consumers depending on the old signature yet.
- `discover_xml()` (a narrower, `.xml`-only, still-`Path`-returning sibling function) was deliberately left unchanged — it isn't on the CLI's directory-mode call path and has its own direct tests.
