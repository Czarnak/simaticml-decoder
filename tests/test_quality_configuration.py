"""Configuration tests for the release-quality gate.

These guard against the ways the gate can silently drift apart:
``pyproject.toml`` not encoding the coverage floor CI already enforces, a
workflow's Python matrix testing fewer versions than the package claims to
support (via trove classifiers), and README's documented pre-commit command
falling out of sync with what CI actually runs. Both ``ci.yml`` (runs on
every push/PR) and ``release.yml`` (gates the actual PyPI publish) carry
their own copy of the matrix and quality command, so both are checked --
release.yml is the one that matters most for "release quality" specifically.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT_PATH = _ROOT / "pyproject.toml"
_CI_WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "ci.yml"
_RELEASE_WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "release.yml"
_README_PATH = _ROOT / "README.md"

_CI_LINT_COMMAND = "ruff check ."
_CI_TEST_COMMAND = "pytest -q --cov=simaticml_decoder --cov-report=term-missing --cov-fail-under=80"

_VERSION_CLASSIFIER = re.compile(r"Programming Language :: Python :: (3\.\d+)")


def _load_pyproject() -> dict:
    return tomllib.loads(_PYPROJECT_PATH.read_text(encoding="utf-8"))


def _classifier_versions(config: dict) -> set[str]:
    classifiers = config["project"]["classifiers"]
    versions = {m.group(1) for c in classifiers if (m := _VERSION_CLASSIFIER.fullmatch(c))}
    assert versions, "expected at least one specific-version Python classifier"
    return versions


def _matrix_versions(job_text: str) -> set[str]:
    match = re.search(r"python-version:\s*\[(.*?)\]", job_text)
    assert match is not None, "could not find a python-version matrix in the given CI job text"
    return {version.strip().strip('"') for version in match.group(1).split(",")}


def test_pytest_coverage_floor_is_80_percent() -> None:
    """pyproject.toml must record the same 80% floor CI already enforces,
    rather than CI being the only place this gate is defined."""
    config = _load_pyproject()

    fail_under = config["tool"]["coverage"]["report"]["fail_under"]

    assert fail_under == 80


def test_declared_python_classifiers_match_ci_matrix() -> None:
    """The specific Python versions pyproject.toml claims to support (via
    trove classifiers) must be exactly the versions the primary (ubuntu)
    CI matrix tests -- the package must not advertise untested versions."""
    classifier_versions = _classifier_versions(_load_pyproject())

    workflow_text = _CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    ubuntu_job_text, _, windows_job_text = workflow_text.partition("windows-lint-and-test:")
    ubuntu_versions = _matrix_versions(ubuntu_job_text)

    assert ubuntu_versions == classifier_versions

    # The Windows job is a narrower platform smoke test, not the primary
    # support matrix -- it may test fewer versions, but never an
    # unadvertised one.
    windows_versions = _matrix_versions(windows_job_text)
    assert windows_versions <= classifier_versions


def test_declared_python_classifiers_match_release_workflow_matrix() -> None:
    """release.yml's ``checks`` job independently gates the actual PyPI
    publish (``build``/``publish`` both ``need: [checks, windows-checks]``),
    so it must not silently diverge from ci.yml/classifiers and validate a
    narrower set of Python versions than the release claims to support."""
    classifier_versions = _classifier_versions(_load_pyproject())

    workflow_text = _RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    checks_job_text, _, windows_job_text = workflow_text.partition("windows-checks:")
    checks_versions = _matrix_versions(checks_job_text)

    assert checks_versions == classifier_versions


def test_readme_documents_the_exact_ci_quality_command() -> None:
    """README's documented pre-commit quality command must match what CI
    runs verbatim, so following the README reproduces CI's gate exactly."""
    readme = _README_PATH.read_text(encoding="utf-8")

    assert _CI_LINT_COMMAND in readme
    assert _CI_TEST_COMMAND in readme

    for workflow_path in (_CI_WORKFLOW_PATH, _RELEASE_WORKFLOW_PATH):
        workflow_text = workflow_path.read_text(encoding="utf-8")
        assert _CI_LINT_COMMAND in workflow_text
        assert _CI_TEST_COMMAND in workflow_text
