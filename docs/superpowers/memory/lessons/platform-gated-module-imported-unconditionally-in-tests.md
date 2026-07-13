---
type: lesson
title: platform-gated-module-imported-unconditionally-in-tests
summary: A pytest.mark.skipif on a test module does not stop that module's top-level imports from running during collection — a platform-gated module that raises at import time will crash CI collection, not skip cleanly.
tags:
  - testing
  - ci
  - cross-platform
last_verified_commit: 0824515c9c213bf47e728f439c759e3e64a23239
status: active
---

## Situation

Building `src/simaticml_decoder/windows_handles.py`, a Windows-only `ctypes`/NTAPI module that deliberately raises `RuntimeError` at import time on any non-`win32` platform (so misuse elsewhere in the codebase fails loudly instead of silently no-opping). Its test file, `tests/test_windows_handles.py`, was written with the obvious-looking pattern:

```python
from simaticml_decoder.windows_handles import NativeDirectory

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows native handles")
```

This passed every test on the Windows dev machine used to build it. But the project's CI (`.github/workflows/ci.yml`) runs its primary `lint-and-test` job on `ubuntu-latest` — a platform where this import raises immediately. `pytestmark` only marks *tests* to be skipped at run time; it does nothing to stop the *module* from being imported during pytest's collection phase, which happens before any skip logic is evaluated. The result would have been a full collection-phase crash on the very next push to `main`, breaking the entire test suite (not just the Windows-only tests) on the platform where CI actually runs by default.

This was only caught because the orchestrating agent explicitly reasoned through "what happens when this file is collected on Linux CI" rather than trusting that local Windows test runs (all green) meant CI would also pass.

## Why It Mattered

Local tests were 100% green throughout — this bug was invisible until reasoned through by inspection, since the dev environment for this feature happened to be Windows (the same platform the gated module targets). It would have been caught by CI, but only *after* landing on `main` and breaking every other test in the suite on the Linux job, for everyone, unrelated to this change.

## Rule

When a module raises/errors at import time on unsupported platforms, any file that imports it — production code or tests — must guard the import itself (e.g. `if sys.platform == "win32": from . import windows_handles`), not just mark the consuming tests as skipped. A `skipif`/`xfail` marker controls whether a test *runs*; it does not control whether the module containing that test gets *imported*.

## When to Apply

Any time a module is intentionally platform-gated (raises, or is simply absent, on some platforms) and something else — especially a test file collected by a test runner that scans all files regardless of markers — imports it at module scope. Also applies to optional-dependency-gated modules with the same import-time-raise pattern.

## When NOT to Apply

Does not apply when the gated module itself is designed to degrade gracefully at import time (e.g. returns a stub/no-op instead of raising) — in that case an unconditional import is safe and this extra guarding is unnecessary ceremony. Also does not apply to modules only ever imported lazily inside a function body that itself checks the platform first (e.g. `input_policy._discover_windows`'s `from . import windows_handles` inside the function, only ever called after `_use_windows_native_discovery()` has already confirmed `win32`) — that pattern was already correct in production code from the start; the bug was specific to the test file's top-level import.
