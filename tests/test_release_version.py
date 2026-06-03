from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_release_version.py"
SPEC = importlib.util.spec_from_file_location("check_release_version", SCRIPT_PATH)
assert SPEC is not None
release_version = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_version)


def _write_project(root: Path, project_version: str, init_version: str) -> Path:
    package_dir = root / "src" / "simaticml_decoder"
    package_dir.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "simaticml-decoder"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text(
        f'__version__ = "{init_version}"\n',
        encoding="utf-8",
    )
    return root


def test_check_release_version_accepts_matching_v_tag(tmp_path: Path) -> None:
    root = _write_project(tmp_path, "1.2.3", "1.2.3")

    assert release_version.check_release_version(root, "v1.2.3") == ()


def test_check_release_version_reports_pyproject_mismatch(tmp_path: Path) -> None:
    root = _write_project(tmp_path, "1.2.4", "1.2.3")

    errors = release_version.check_release_version(root, "v1.2.3")

    assert errors == ("tag version '1.2.3' does not match pyproject.toml '1.2.4'",)


def test_check_release_version_reports_init_mismatch(tmp_path: Path) -> None:
    root = _write_project(tmp_path, "1.2.3", "1.2.4")

    errors = release_version.check_release_version(root, "v1.2.3")

    assert errors == ("tag version '1.2.3' does not match __version__ '1.2.4'",)


def test_check_release_version_rejects_non_v_tag(tmp_path: Path) -> None:
    root = _write_project(tmp_path, "1.2.3", "1.2.3")

    try:
        release_version.check_release_version(root, "1.2.3")
    except ValueError as exc:
        assert str(exc) == "release tag must start with 'v': 1.2.3"
    else:
        raise AssertionError("expected non-v release tag to fail")
