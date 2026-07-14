"""Fresh-clone reproducibility contract for the committed V21 project corpus.

Three guarantees, none of which may depend on anything outside a fresh
``git clone``:

1. The committed corpus (``tests/fixtures/manifest.json`` and
   ``tests/fixtures/SimaticML``) and its golden project manifest
   (``tests/golden/v21_project_manifest.json``) are tracked files, not
   locally-generated or environment-dependent artifacts.
2. ``tests/conftest.py``'s committed-V21-corpus fixture helper fails loudly
   (``AssertionError``) when the corpus is missing rather than silently
   skipping dependent tests via ``pytest.skip`` -- a missing fixture is a
   broken environment, not a reason to report false-green test runs.
3. Running the real project-indexing pipeline
   (``index_simaticml_project`` -> ``emit_project_manifest``) over the
   committed corpus is deterministic and produces byte-identical output to
   the committed golden manifest, serialized exactly as
   ``project_emit.write_project_manifest`` serializes it on disk. This is
   the regression guard: any future change to discovery, the V21 adapter,
   the reference resolver, or the emitter that changes the real corpus's
   manifest output fails this test.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from simaticml_decoder.project import index_simaticml_project
from simaticml_decoder.project_emit import emit_project_manifest
from simaticml_decoder.project_model import ProjectLimits

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"
GOLDEN_ROOT = Path(__file__).resolve().parent / "golden"
CONFTEST_PATH = Path(__file__).resolve().parent / "conftest.py"

# The conftest.py fixture that is the single source of truth for "is the
# committed V21 project-mode corpus present" -- see conftest.py itself.
_CORPUS_FIXTURE_NAME = "project_fixture_root"


def _fixture_helper_uses_pytest_skip_for_committed_v21_cases() -> bool:
    """``True`` iff ``conftest.py``'s committed-V21-corpus fixture helper
    (``project_fixture_root``) contains a ``pytest.skip(`` call.

    Scoped to that one function's own source text (via the AST, not a
    whole-file substring search) so this check can never be tripped by the
    legitimate, unrelated ``pytest.skip`` calls in ``test_input_policy.py``/
    ``test_project_discovery.py`` -- those guard genuine environment-
    capability gaps (symlink/junction creation unavailable on the host), not
    missing fixtures, and are correct as-is.
    """
    source = CONFTEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CONFTEST_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == _CORPUS_FIXTURE_NAME:
            segment = ast.get_source_segment(source, node) or ""
            return "pytest.skip(" in segment
    raise AssertionError(
        f"conftest.py has no {_CORPUS_FIXTURE_NAME!r} fixture to check -- "
        "update _CORPUS_FIXTURE_NAME if it was renamed"
    )


def test_committed_project_corpus_has_metadata_mapping_and_golden():
    assert (FIXTURES_ROOT / "manifest.json").is_file()
    assert (FIXTURES_ROOT / "SimaticML").is_dir()
    assert (GOLDEN_ROOT / "v21_project_manifest.json").is_file()
    assert not _fixture_helper_uses_pytest_skip_for_committed_v21_cases()


def test_committed_v21_corpus_manifest_matches_golden_byte_for_byte():
    """Golden-manifest regression test.

    Serializes exactly as ``project_emit.write_project_manifest`` does
    internally (same ``json.dumps`` call, same trailing newline) so this
    assertion is a faithful stand-in for "the file ``write_project_manifest``
    would have written is unchanged".
    """
    index = index_simaticml_project(FIXTURES_ROOT / "SimaticML", (), ProjectLimits())
    actual = (
        json.dumps(emit_project_manifest(index), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
    )
    expected = (GOLDEN_ROOT / "v21_project_manifest.json").read_text(encoding="utf-8")
    assert actual == expected
