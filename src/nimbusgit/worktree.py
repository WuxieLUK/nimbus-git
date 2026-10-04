"""Working-tree snapshots, tree building, and checkout helpers."""

from __future__ import annotations

import os
from pathlib import Path

from .hashing import hash_object
from .index import IndexEntry
from .objects import TreeEntry, serialize_tree
from .repo import Repo


def to_posix(path: str | Path) -> str:
    return str(path).replace(os.sep, "/")


def iter_worktree_files(root: Path):
    """Yield regular files in ``root``, skipping ``.git`` metadata."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for filename in filenames:
            yield Path(dirpath) / filename


def relative_path(root: Path, file_path: Path) -> str:
    return to_posix(Path(file_path).resolve().relative_to(Path(root).resolve()))


def hash_worktree_file(path: Path) -> str:
    return hash_object("blob", Path(path).read_bytes())


def build_tree(repo: Repo, entries: list[IndexEntry]) -> str:
    """Create a tree object from staged index entries."""
    root: dict = {"type": "tree", "children": {}}
    for entry in entries:
        node = root
        parts = entry.path.split("/")
        for part in parts[:-1]:
            node = node["children"].setdefault(part, {"type": "tree", "children": {}})
        node["children"][parts[-1]] = {"type": "blob", "mode": entry.mode, "sha": entry.sha}
    return _write_subtree(repo, root)


def _write_subtree(repo: Repo, node: dict) -> str:
    children: list[TreeEntry] = []
    for name, child in node["children"].items():
        if child["type"] == "tree":
            sha = _write_subtree(repo, child)
            children.append(TreeEntry(mode="40000", name=name, sha=sha))
        else:
            children.append(TreeEntry(mode=f"{child['mode']:o}", name=name, sha=child["sha"]))
    data = serialize_tree(children)
    return repo.objects.write("tree", data)


def flatten_tree(repo: Repo, tree_sha: str, prefix: str = "") -> dict[str, tuple[str, str]]:
    """Return ``{path: (mode, sha)}`` for every leaf under ``tree_sha``."""
    result: dict[str, tuple[str, str]] = {}
    for entry in repo.objects.read_tree(tree_sha):
        path = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.mode == "40000":
            result.update(flatten_tree(repo, entry.sha, path))
        else:
            result[path] = (entry.mode, entry.sha)
    return result


def flatten_index(entries: list[IndexEntry]) -> dict[str, tuple[str, str]]:
    return {entry.path: (f"{entry.mode:o}", entry.sha) for entry in entries if entry.stage == 0}


def worktree_files(root: Path) -> dict[str, str]:
    """Return ``{relative_path: sha}`` for every file in the working tree."""
    return {
        relative_path(root, path): hash_worktree_file(path)
        for path in iter_worktree_files(root)
    }
