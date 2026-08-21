from __future__ import annotations

from mango_cli.path_setup import _split_path, bin_directory, repo_root


def test_split_path_dedupes() -> None:
    merged = _split_path(r"C:\a;C:\b;C:\a")
    assert merged == [r"C:\a", r"C:\b"]


def test_bin_directory_under_repo() -> None:
    root = repo_root()
    assert bin_directory(root).name == "bin"
    assert bin_directory(root).parent == root
