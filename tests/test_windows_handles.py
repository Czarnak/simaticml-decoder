"""Windows-only native handle traversal tests."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from simaticml_decoder.input_policy import InputViolation
from simaticml_decoder.windows_handles import NativeDirectory

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows native handles")


def test_native_enumeration_rejects_junction(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "jump"), str(outside)], check=True)
    with pytest.raises(InputViolation, match="symlink_not_allowed"):
        NativeDirectory.open_root(root).entries()


def test_opened_child_survives_name_swap(tmp_path):
    (tmp_path / "block.xml").write_text("<Document/>", encoding="utf-8")
    with NativeDirectory.open_root(tmp_path) as root:
        child = root.open_child("block.xml", directory=False)
        os.replace(tmp_path / "block.xml", tmp_path / "moved.xml")
        assert child.read_limited(1024) == b"<Document/>"


def test_open_child_rejects_unsafe_names(tmp_path):
    (tmp_path / "block.xml").write_text("data", encoding="utf-8")
    with NativeDirectory.open_root(tmp_path) as root:
        with pytest.raises(InputViolation, match="invalid_entry_name"):
            root.open_child("..", directory=True)
        with pytest.raises(InputViolation, match="invalid_entry_name"):
            root.open_child(".", directory=True)
        with pytest.raises(InputViolation, match="invalid_entry_name"):
            root.open_child("sub\\dir", directory=True)
        with pytest.raises(InputViolation, match="invalid_entry_name"):
            root.open_child("sub/dir", directory=True)


def test_entries_lists_files_and_directories_sorted(tmp_path):
    (tmp_path / "b.xml").write_text("b", encoding="utf-8")
    (tmp_path / "a.xml").write_text("a", encoding="utf-8")
    (tmp_path / "z_dir").mkdir()
    (tmp_path / "m_dir").mkdir()
    with NativeDirectory.open_root(tmp_path) as root:
        found = root.entries()
    names = [(entry.name, entry.is_directory) for entry in found]
    assert names == sorted(names, key=lambda item: item[0])
    assert ("a.xml", False) in names
    assert ("b.xml", False) in names
    assert ("m_dir", True) in names
    assert ("z_dir", True) in names


def test_read_limited_reveals_oversized_file_with_extra_byte(tmp_path):
    (tmp_path / "exact.xml").write_bytes(b"x" * 10)
    (tmp_path / "over.xml").write_bytes(b"x" * 11)
    with NativeDirectory.open_root(tmp_path) as root:
        exact_handle = root.open_child("exact.xml", directory=False)
        over_handle = root.open_child("over.xml", directory=False)
        assert exact_handle.read_limited(10) == b"x" * 10
        assert over_handle.read_limited(10) == b"x" * 11


def test_open_root_missing_path_raises_input_violation(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(InputViolation):
        NativeDirectory.open_root(missing)
