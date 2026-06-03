"""Validate that a release tag matches the package versions."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def read_project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    return pyproject["project"]["version"]


def read_init_version(root: Path) -> str:
    init_path = root / "src" / "simaticml_decoder" / "__init__.py"
    match = INIT_VERSION_RE.search(init_path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{init_path} does not define __version__")
    return match.group(1)


def version_from_tag(tag: str) -> str:
    if not tag.startswith("v"):
        raise ValueError(f"release tag must start with 'v': {tag}")
    version = tag[1:]
    if not version:
        raise ValueError("release tag must include a version after 'v'")
    return version


def check_release_version(root: Path, tag: str) -> tuple[str, ...]:
    tag_version = version_from_tag(tag)
    project_version = read_project_version(root)
    init_version = read_init_version(root)

    errors: list[str] = []
    if tag_version != project_version:
        errors.append(
            f"tag version {tag_version!r} does not match pyproject.toml {project_version!r}"
        )
    if tag_version != init_version:
        errors.append(f"tag version {tag_version!r} does not match __version__ {init_version!r}")
    return tuple(errors)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    tag = args[0] if args else os.environ.get("GITHUB_REF_NAME", "")
    if not tag:
        print("release tag is required as an argument or GITHUB_REF_NAME", file=sys.stderr)
        return 2

    try:
        errors = check_release_version(ROOT, tag)
    except (OSError, KeyError, ValueError) as exc:
        print(f"release version check failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"release version check failed: {error}", file=sys.stderr)
        return 1

    print(f"release version check passed for {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
