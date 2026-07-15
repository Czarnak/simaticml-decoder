# Contributing to SimaticML Decoder

Thank you for your interest in contributing to SimaticML Decoder. This document covers development setup, code organization, submission guidelines, and the fixture policy.

## Development Setup

### Install editable mode with dev extras

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode along with lint, test, coverage, build, and validation tools.

### Run local checks before committing

Before opening a pull request, run these two commands locally and ensure both pass:

```bash
ruff check .
pytest -q --cov=simaticml_decoder --cov-report=term-missing --cov-fail-under=80
```

- **`ruff check .`** — Lints and checks code style (100 character line length)
- **`pytest --cov=...`** — Runs all tests and enforces 80% code coverage

The 80% coverage floor is enforced both in CI and locally in `pyproject.toml` (`[tool.coverage.report] fail_under = 80`), so it is not a CI-only gate. Coverage must pass on your machine before you push.

#### Coverage exclusions

`src/simaticml_decoder/windows_handles.py` is intentionally omitted from coverage reporting. It contains Windows-only ctypes and NTAPI glue code that is only called from `input_policy.py` behind a `_use_windows_native_discovery()` guard. On Linux CI it never executes and would drag aggregate coverage below the 80% floor for platform-specific reasons unrelated to any regression. It has its own platform-gated test suite (`tests/test_windows_handles.py`, skipif'd to run only on Windows) that verifies it directly.

## Code Organization

The decoder consists of three cleanly separated, independently testable phases:

### Phase 1: Parse → Model
- **`parse.py`** — XML parser and validation
- **`model.py`** — Faithful syntactic mirror of the parsed XML

### Phase 2: Fold → IR
- **`fold.py`** — Folding logic: series→AND, `O`→OR, fan-out, negation, latches
- **`ir.py`** — Intermediate representation: boolean trees and assignments

### Phase 3: Emit
- **`emit.py`** — Code generation: IR to SCL text and JSON sidecar

### Supporting Modules
- **`instructions.py`** — Part catalog (data, not logic)
- **`operand.py`** — Access → display string conversion
- **`scl_reconstruct.py`** — SCL network reconstruction from tokenised AST
- **`input_policy.py`** — Untrusted-input boundary enforcement

### Project-Mode Modules
- **`project.py`** — Top-level project coordinator
- **`project_discovery.py`** — Handle-anchored, symlink-rejecting file discovery
- **`project_xml.py`** — XML classification and resource loading
- **`project_model.py`** — Block and UDT model contracts
- **`project_index.py`** — Cross-project reference resolution
- **`project_emit.py`** — Project manifest generation

### CLI and Initialization
- **`cli.py`** — Command-line interface

## Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <description>

<optional body>
```

### Commit types

- **`feat:`** — New feature
- **`fix:`** — Bug fix
- **`docs:`** — Documentation changes
- **`test:`** — Test additions or changes
- **`refactor:`** — Code refactoring (no feature or bug-fix change)
- **`chore:`** — Dependency or tooling updates
- **`perf:`** — Performance improvements
- **`ci:`** — CI/CD workflow changes

### Examples from this repository

```
feat: add explicit project index command
fix: handle manifest-write failures and invalid --library-root input cleanly
docs: define V21 project input contract
test: cover UDT-reference resolution in project index
ci: enforce supported-format coverage gate
```

## Fixture and Test-Data Policy

Any new test fixture, golden output file, or diagnostic example must meet these criteria:

1. **Clear license** — The source must have a declared license (MIT, Apache-2.0, BSD, etc.) or explicit permission for redistribution.
2. **Sanitized and redistributable** — Remove or redact any proprietary, sensitive, or identifying information.
3. **CI regression test** — A non-skipping test must exercise the fixture and validate the output against golden or expected values.

Until all three conditions are met, a format is not claimed as "validated". We do not use unlicensed fixtures as a template for adding more.

The repository currently includes temporary compatibility probes from [felipebojorquem/sorting-cell-s7-1200](https://github.com/felipebojorquem/sorting-cell-s7-1200), which has no declared license. These probes are used only for local decoder evaluation; they are not a distributable fixture corpus and do not validate feature support. A replacement corpus from a suitably licensed, redaction-reviewed project is pending.

## Pull Request Checklist

Before submitting a pull request:

- [ ] **Code is lint-clean** — `ruff check .` passes
- [ ] **Tests pass and coverage is sufficient** — `pytest --cov=...` passes with 80%+ coverage
- [ ] **Commit messages follow convention** — Conventional Commits format (`feat:`, `fix:`, etc.)
- [ ] **Documentation is updated** — If you changed CLI flags, behavior, or interfaces, update `README.md` or relevant docs
- [ ] **Fixtures are licensed** — If you added test data, it has a clear license and redistribution rights
- [ ] **No hardcoded secrets** — No API keys, passwords, or internal URLs in code or tests

## License

By contributing to this project, you agree that your contributions will be licensed under the same MIT License as the project (see `LICENSE`).

---

For questions, open a GitHub issue. For security concerns, see `SECURITY.md`.
