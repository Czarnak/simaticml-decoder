---
type: decision
title: Native NT handles (ctypes/NTAPI) for Windows directory traversal, dir_fd for POSIX, fail-closed elsewhere
summary: Why directory-mode discovery is handle/descriptor-anchored per platform instead of path-based with post-hoc symlink checks.
tags:
  - security
  - windows
  - ctypes
owned_paths:
  - src/simaticml_decoder/windows_handles.py
  - src/simaticml_decoder/input_policy.py
related_docs:
  - docs/superpowers/memory/artifact-traversal-contract.md
  - docs/superpowers/memory/input-boundary-module-card.md
last_verified_commit: cf680ad
status: accepted
---

## Context

The CLI's directory/bulk mode recursively scans an untrusted input tree. The prior implementation (`_discover`, path-based `os.lstat`/`Path.iterdir()`) rejected symlinks/reparse points at discovery time, but between discovering a file and later reading it by its `Path`, an attacker could swap a directory in the chain for a junction/symlink and redirect the eventual read outside the intended root (TOCTOU). Windows reparse points (junctions, symlinks, mount points) are the primary concrete threat on this project's primary target platform.

## Decision

- **Windows**: open the root directory exactly once via `ctypes` bindings to `NtCreateFile`/`NtQueryDirectoryFile` (`windows_handles.NativeDirectory`). Enumerate and open every child *relative to its parent's own already-open handle* — never by composing/re-resolving a path string. Every open passes `FILE_OPEN_REPARSE_POINT` so the OS never transparently follows a reparse point; any reparse point found (at enumeration, and — after `cf680ad` — re-checked immediately after each `open_child`) is rejected with `InputViolation("symlink_not_allowed", ...)`.
- **POSIX**: `dir_fd` + `O_NOFOLLOW` opens, chained the same way (open each child relative to its parent's fd). `O_NOFOLLOW` makes symlink rejection kernel-atomic at the open syscall (`ELOOP`), so POSIX doesn't need the Windows branch's post-open re-check — the race can't happen there in the first place.
- **Everywhere else** (no `os.supports_dir_fd`/`os.supports_follow_symlinks`/`O_NOFOLLOW`): directory mode fails closed with `InputViolation("unsupported_platform", ...)`. Direct single-file mode is unaffected.
- Each matched file's handle/fd is opened **eagerly during discovery** and captured in that artifact's reader closure (not re-opened lazily at read time by walking from a kept-open root). Directory handles/fds are closed as soon as their children are fully processed; file handles/fds are closed immediately after their one `read_bytes()` call (`cf680ad`).

## Alternatives considered

- **Path-based discovery + re-validate-by-path at read time** (i.e., keep the old `_discover`, just add a re-`lstat` check right before each read): rejected — still has a race between the re-check and the actual open; doesn't close the window, just narrows it.
- **Third-party library for Windows reparse-point-safe traversal**: none found that exposes handle-relative (`RootDirectory`-anchored) opens at the level of granularity needed; the project also keeps zero runtime dependencies (`pyproject.toml`: stdlib-only) by design, so a new dependency here would be a bigger change than the ctypes adapter.
- **Lazy re-walk-from-root at read time** (keep only the root handle alive, re-derive each file's handle by walking down through cached path segments when `read_bytes()` is finally called) instead of eager-open-per-file: not chosen — eager-open is simpler to reason about and matches "readers consume existing native file handles" literally; the trade-off (many simultaneously open handles on very large trees) was flagged in review and mitigated by closing each handle right after its one read (`cf680ad`), rather than switching strategies.

## Trade-offs

- `ctypes`/NTAPI code (`UNICODE_STRING`, `OBJECT_ATTRIBUTES`, `IO_STATUS_BLOCK`, `FILE_ID_BOTH_DIR_INFORMATION`, `BY_HANDLE_FILE_INFORMATION` structs) is inherently fiddly — a wrong field width silently corrupts memory or misreads an attribute bit rather than raising cleanly. Mitigated with exact-width struct definitions checked against real Win32/NTAPI layouts and real-junction integration tests (not mocks) on Windows CI.
- The POSIX `dir_fd` branch cannot be exercised end-to-end on a Windows dev machine; it's covered by a monkeypatched fake-filesystem harness plus a real fail-closed test, but genuine POSIX execution only happens in Windows... no — only happens once Linux CI actually runs it. This is a known, explicitly-flagged gap, not a silent one.
- Directory mode on an unsupported platform is now a hard failure (`INPUT_REJECTED`) instead of "works, but less safely." Accepted as correct: a security-hardening feature that silently degrades to the unsafe behavior it was built to remove would defeat its own purpose.

## Revisit signals

- If Linux CI (`windows-lint-and-test`'s sibling, the pre-existing `lint-and-test` job) starts running against a filesystem/kernel combination where `os.supports_dir_fd`/`follow_symlinks` are unexpectedly unavailable, the `unsupported_platform` fail-closed path will start firing in CI — investigate rather than loosening it.
- If a future macOS-specific quirk in `dir_fd` semantics surfaces, revisit whether `_dir_fd_available()`'s capability check needs a platform-specific carve-out (e.g. `O_DIRECTORY` isn't checked by `_dir_fd_available()` today — see `input-boundary-module-card.md` pitfalls).
