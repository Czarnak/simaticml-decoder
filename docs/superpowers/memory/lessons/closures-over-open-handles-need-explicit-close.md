---
type: lesson
title: closures-over-open-handles-need-explicit-close
summary: A resource wrapper's __del__ safety net is not a resource-management strategy — a reader closure that captures an open handle/fd must close it explicitly right after use, or it survives for the whole batch by accident.
tags:
  - resource-management
  - python
  - security
last_verified_commit: a74792b98156a1100bdaada255e68c7f2f84b4ba
status: active
---

## Situation

Implementing directory-mode file discovery (`input_policy._walk_windows_directory` / `_walk_posix_directory`), each matched file's native handle/fd was opened eagerly during the discovery walk and captured inside that file's `InputArtifact` reader closure (`_make_handle_reader`), so `read_bytes()` could later read through the already-open handle without ever reopening a path. Both `windows_handles.NativeHandle` and the POSIX `_PosixFileHandle` wrapper classes already implement `close()` plus a `__del__` safety net (added specifically so a forgotten `close()` wouldn't leak an OS handle forever).

The first implementation (commit `a74792b`) never called `.close()` anywhere in the reader closure or in `cli.decode_artifact`. It passed every test and the security invariant (no path re-resolution) held — but an independent code review caught that, in practice, every matched file's handle stayed open for the entire directory-mode run: `cli.main()` keeps the full `artifacts`/`outcomes` collections alive until the whole batch finishes, so nothing dropped the reference to any handle early, and Python's `__del__`-based cleanup only ran once the entire run ended. With the default `max_files = 10_000`, a large input tree would hold up to 10,000 native handles/fds open simultaneously for the full run's duration, not for the brief window each one is actually needed.

## Why It Mattered

This was not a security defect (the invariant under review — no re-opened path — held regardless), but it was a real resource-scaling defect that all tests missed, because no test exercised anywhere near 10,000 discovered files, and `__del__`-based cleanup means "everything is technically fine" right up until it silently isn't at scale (OS handle-count limits, or just wasted resources for the run's whole lifetime).

## Rule

If a wrapper class provides `__del__` as a *safety net*, that is a signal the caller is expected to call `close()` explicitly and promptly at the actual point of last use — not a signal that deferring cleanup to garbage collection is an acceptable primary strategy. When a resource (handle/fd/connection) is captured inside a closure that is only ever invoked once, wrap the body in `try/finally: resource.close()` so the resource is released the instant it's no longer needed, regardless of success or failure.

## When to Apply

Any time code captures an open OS-level resource (file handle, socket, descriptor) inside a closure or object whose invocation count is known/bounded (e.g. "called exactly once per item, later, from a collection built during a batch operation"). Especially relevant when the resource is opened *eagerly ahead of time* (during a discovery/enumeration phase) rather than opened lazily right before use — eager-open naturally creates a longer window between "open" and "actually needed" that must be explicitly closed at the "needed" end, since the interpreter has no way to know the closure is done with it until GC.

## When NOT to Apply

Does not apply when a resource is intentionally meant to outlive a single call — e.g. a connection pool entry, or a directory handle that legitimately anchors multiple subsequent child opens within the same walk (those are correctly closed once, after all children are processed, which the same codebase already does correctly for `NativeDirectory`/directory `dir_fd`s via `with ... as child_dir:` / `try/finally: os.close(child_fd)` around the recursive call). The lesson is specifically about *terminal* resources (a file, read exactly once) captured in a closure, not about resources that are legitimately shared across multiple subsequent operations.
