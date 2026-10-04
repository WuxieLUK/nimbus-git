"""High-level command implementations used by the ``nimbus`` CLI."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .diff import is_binary, unified_diff
from .errors import DirtyWorktreeError, NimbusGitError, RefNotFoundError
from .hashing import hash_object
from .index import IndexEntry, read_index, stat_to_index_entry, write_index
from .objects import GitCommit, GitTag, ObjectDB, serialize_commit, serialize_tag
from .refs import (
    branch_exists,
    current_branch,
    list_branches,
    list_tags,
    read_head,
    read_ref,
    resolve_revision,
    update_branch,
    write_ref,
)
from .repo import Repo, discover, init_repository, set_head_branch, set_head_detached
from .worktree import (
    build_tree,
    flatten_index,
    flatten_tree,
    hash_worktree_file,
    iter_worktree_files,
    relative_path,
    worktree_files,
)


def _identity(kind: str) -> str:
    """Build a Git identity line from environment variables with safe defaults."""
    suffix = kind.upper()
    name = os.environ.get(f"GIT_{suffix}_NAME", "Nimbus")
    email = os.environ.get(f"GIT_{suffix}_EMAIL", "nimbus@local")
    timestamp = int(time.time())
    return f"{name} <{email}> {timestamp} +0000"


def _commit_tree(repo: Repo, commit_sha: str) -> str:
    return repo.objects.read_commit(commit_sha).tree


def _ensure_repo() -> Repo:
    return discover()


def cmd_init(path: str | None, branch: str = "main") -> str:
    target = Path(path or ".").resolve()
    target.mkdir(parents=True, exist_ok=True)
    repo = init_repository(target, branch)
    return f"Initialized empty Git repository in {repo.gitdir}"


def _expand_add_paths(repo: Repo, cwd: Path, pathspecs: list[str]):
    if not pathspecs:
        yield from iter_worktree_files(repo.worktree)
        return
    for spec in pathspecs:
        path = Path(spec)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        try:
            path.relative_to(repo.worktree)
        except ValueError as exc:
            raise NimbusGitError(f"pathspec '{spec}' is outside the repository") from exc
        if path.is_dir():
            yield from iter_worktree_files(path)
        elif path.is_file():
            yield path
        else:
            raise NimbusGitError(f"pathspec '{spec}' did not match any files")


def cmd_add(repo: Repo, cwd: Path, pathspecs: list[str]) -> str:
    entries = {entry.path: entry for entry in read_index(repo)}
    staged: list[str] = []
    for file_path in _expand_add_paths(repo, cwd, pathspecs):
        rel = relative_path(repo.worktree, file_path)
        sha = hash_worktree_file(file_path)
        repo.objects.write("blob", file_path.read_bytes())
        entries[rel] = stat_to_index_entry(repo, file_path, rel, sha)
        staged.append(rel)
    write_index(repo, list(entries.values()))
    if not staged:
        return "nothing to add"
    return "staged " + ", ".join(staged)


def cmd_commit(repo: Repo, message: str, allow_empty: bool = False) -> str:
    entries = read_index(repo)
    if not entries and not allow_empty:
        raise NimbusGitError("nothing to commit (use 'nimbus add' to stage files)")
    if not message:
        raise NimbusGitError("commit message is required (-m)")

    tree_sha = build_tree(repo, entries)
    branch, parent = read_head(repo)
    commit = GitCommit(
        tree=tree_sha,
        parents=[parent] if parent else [],
        author=_identity("author"),
        committer=_identity("committer"),
        message=message,
    )
    commit_sha = repo.objects.write("commit", serialize_commit(commit))
    if branch and branch.startswith("refs/heads/"):
        write_ref(repo, branch, commit_sha)
    else:
        set_head_detached(repo, commit_sha)
    return f"[{branch or 'detached'} {commit_sha[:7]}] {message.splitlines()[0]}"


def _status(repo: Repo):
    branch, head_sha = read_head(repo)
    index_map = flatten_index(read_index(repo))
    head_map = flatten_tree(repo, _commit_tree(repo, head_sha)) if head_sha else {}
    working_map = worktree_files(repo.worktree)

    staged_added = sorted(set(index_map) - set(head_map))
    staged_deleted = sorted(set(head_map) - set(index_map))
    staged_modified = sorted(
        path for path in set(index_map) & set(head_map) if index_map[path] != head_map[path]
    )

    unstaged_modified: list[str] = []
    unstaged_deleted: list[str] = []
    for path, (_, sha) in index_map.items():
        if path not in working_map:
            unstaged_deleted.append(path)
        elif working_map[path] != sha:
            unstaged_modified.append(path)
    untracked = sorted(set(working_map) - set(index_map))
    return (
        branch,
        staged_added,
        staged_modified,
        staged_deleted,
        sorted(unstaged_modified),
        unstaged_deleted,
        untracked,
    )


def cmd_status(repo: Repo) -> str:
    (
        branch,
        staged_added,
        staged_modified,
        staged_deleted,
        unstaged_modified,
        unstaged_deleted,
        untracked,
    ) = _status(repo)
    if branch:
        output = [f"On branch {branch[len('refs/heads/'):] if branch.startswith('refs/heads/') else branch}"]
    else:
        output = ["HEAD detached"]

    staged = staged_added + staged_modified + staged_deleted
    changed = unstaged_modified + unstaged_deleted
    if not staged and not changed and not untracked:
        output.append("nothing to commit, working tree clean")
        return "\n".join(output)

    if staged:
        output.append("")
        output.append("Changes to be committed:")
        output.append('  (use "nimbus commit" to record a snapshot)')
        for path in staged_added:
            output.append(f"\tnew file:   {path}")
        for path in staged_modified:
            output.append(f"\tmodified:   {path}")
        for path in staged_deleted:
            output.append(f"\tdeleted:    {path}")
    if changed:
        output.append("")
        output.append("Changes not staged for commit:")
        output.append('  (use "nimbus add <file>" to stage changes)')
        for path in unstaged_modified:
            output.append(f"\tmodified:   {path}")
        for path in unstaged_deleted:
            output.append(f"\tdeleted:    {path}")
    if untracked:
        output.append("")
        output.append("Untracked files:")
        output.append('  (use "nimbus add <file>" to include in what will be committed)')
        for path in untracked:
            output.append(f"\t{path}")
    return "\n".join(output)


def cmd_log(repo: Repo, max_count: int | None = None) -> str:
    _, head_sha = read_head(repo)
    if not head_sha:
        raise NimbusGitError("your current branch does not have any commits yet")
    output: list[str] = []
    sha = head_sha
    count = 0
    while sha:
        commit = repo.objects.read_commit(sha)
        ref = current_branch(repo)
        label = f" (HEAD -> {ref})" if ref and sha == head_sha else ""
        output.append(f"commit {sha}{label}")
        output.append(f"Author: {commit.author}")
        output.append(f"Date:   {commit.committer}")
        output.append("")
        for line in commit.message.splitlines():
            output.append(f"    {line}")
        output.append("")
        count += 1
        if max_count is not None and count >= max_count:
            break
        if not commit.parents:
            break
        sha = commit.parents[0]
    return "\n".join(output).rstrip()


def _worktree_blob_map(repo: Repo) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in iter_worktree_files(repo.worktree):
        rel = relative_path(repo.worktree, path)
        sha = repo.objects.write("blob", path.read_bytes())
        result[rel] = ("100644", sha)
    return result


def _filter_paths(mapping: dict[str, tuple[str, str]], paths: list[str] | None) -> dict:
    if not paths:
        return mapping
    return {path: value for path, value in mapping.items() if path in paths}


def _render_diff_maps(
    repo: Repo, old_map: dict[str, tuple[str, str]], new_map: dict[str, tuple[str, str]], paths: list[str] | None
) -> str:
    old_map = _filter_paths(old_map, paths)
    new_map = _filter_paths(new_map, paths)
    output: list[str] = []
    for path in sorted(set(old_map) | set(new_map)):
        old = old_map.get(path)
        new = new_map.get(path)
        if old == new:
            continue
        old_sha = old[1] if old else None
        new_sha = new[1] if new else None
        if old_sha == new_sha:
            continue
        old_data = repo.objects.read_blob(old_sha) if old_sha else b""
        new_data = repo.objects.read_blob(new_sha) if new_sha else b""
        output.append(f"diff --git a/{path} b/{path}")
        if is_binary(old_data) or is_binary(new_data):
            output.append("Binary files differ")
            continue
        old_text = old_data.decode("utf-8", errors="replace")
        new_text = new_data.decode("utf-8", errors="replace")
        output.extend(unified_diff(old_text.splitlines(), new_text.splitlines(), f"a/{path}", f"b/{path}"))
    return "\n".join(output)


def cmd_diff(repo: Repo, cached: bool = False, revs: list[str] | None = None, paths: list[str] | None = None) -> str:
    revs = revs or []
    if cached:
        _, head_sha = read_head(repo)
        old_map = flatten_tree(repo, _commit_tree(repo, head_sha)) if head_sha else {}
        new_map = flatten_index(read_index(repo))
    elif len(revs) == 2:
        old_map = flatten_tree(repo, _commit_tree(repo, resolve_revision(repo, revs[0])))
        new_map = flatten_tree(repo, _commit_tree(repo, resolve_revision(repo, revs[1])))
    elif len(revs) == 1:
        old_map = flatten_tree(repo, _commit_tree(repo, resolve_revision(repo, revs[0])))
        new_map = _worktree_blob_map(repo)
    else:
        old_map = flatten_index(read_index(repo))
        new_map = _worktree_blob_map(repo)
    return _render_diff_maps(repo, old_map, new_map, paths)


def cmd_branch(repo: Repo, name: str | None = None, delete: bool = False, start_point: str | None = None) -> str:
    if delete:
        if not name:
            raise NimbusGitError("branch name is required with -d")
        if current_branch(repo) == name:
            raise NimbusGitError(f"cannot delete the branch '{name}' which you are currently on")
        if not branch_exists(repo, name):
            raise RefNotFoundError(f"branch '{name}' not found")
        (repo.heads_dir / name).unlink()
        return f"Deleted branch {name}"

    if not name:
        current = current_branch(repo)
        lines = []
        for branch in list_branches(repo):
            lines.append(f"* {branch}" if branch == current else f"  {branch}")
        return "\n".join(lines)

    if branch_exists(repo, name):
        raise NimbusGitError(f"a branch named '{name}' already exists")
    if start_point:
        target = resolve_revision(repo, start_point)
    else:
        _, target = read_head(repo)
        if not target:
            raise NimbusGitError("not a valid object name: 'HEAD'")
    update_branch(repo, name, target)
    return f"Created branch '{name}' at {target[:7]}"


def _is_dirty(repo: Repo) -> bool:
    (
        _,
        staged_added,
        staged_modified,
        staged_deleted,
        unstaged_modified,
        unstaged_deleted,
        untracked,
    ) = _status(repo)
    return bool(staged_added or staged_modified or staged_deleted or unstaged_modified or unstaged_deleted or untracked)


def cmd_checkout(repo: Repo, branch: str, force: bool = False) -> str:
    if not branch_exists(repo, branch):
        raise RefNotFoundError(f"pathspec '{branch}' did not match any branch known to nimbus")
    if _is_dirty(repo) and not force:
        raise DirtyWorktreeError(
            "local changes would be overwritten by checkout; commit or discard them first (or use -f)"
        )
    target_sha = read_ref(repo, f"refs/heads/{branch}")
    target_map = flatten_tree(repo, _commit_tree(repo, target_sha))

    current_map = flatten_index(read_index(repo))
    for path in sorted(current_map):
        if path not in target_map:
            try:
                (repo.worktree / path).unlink()
            except FileNotFoundError:
                pass

    entries: list[IndexEntry] = []
    for path in sorted(target_map):
        destination = repo.worktree / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(repo.objects.read_blob(target_map[path][1]))
        entries.append(stat_to_index_entry(repo, destination, path, target_map[path][1]))
    write_index(repo, entries)
    set_head_branch(repo, branch)
    return f"Switched to branch '{branch}'"


def cmd_tag(repo: Repo, name: str | None = None, delete: bool = False, rev: str | None = None) -> str:
    if delete:
        if not name:
            raise NimbusGitError("tag name is required with -d")
        tag_path = repo.tags_dir / name
        if not tag_path.is_file():
            raise RefNotFoundError(f"tag '{name}' not found")
        tag_path.unlink()
        return f"Deleted tag '{name}'"
    if not name:
        return "\n".join(list_tags(repo))
    target = resolve_revision(repo, rev) if rev else resolve_revision(repo, "HEAD")
    write_ref(repo, f"refs/tags/{name}", target)
    return f"Created tag '{name}' at {target[:7]}"


def cmd_cat_file(repo: Repo, sha: str, pretty: bool = False, type_only: bool = False, size_only: bool = False) -> str:
    full_sha = resolve_revision(repo, sha)
    obj_type, data = repo.objects.read(full_sha)
    if type_only:
        return obj_type
    if size_only:
        return str(len(data))
    if pretty:
        if obj_type == "tree":
            return "\n".join(f"{entry.mode} {entry.name}" for entry in repo.objects.read_tree(full_sha))
        return data.decode("utf-8", errors="replace").rstrip("\n")
    return data.decode("utf-8", errors="replace")


def cmd_ls_files(repo: Repo) -> str:
    return "\n".join(sorted(entry.path for entry in read_index(repo)))


def _walk_tree(repo: Repo, sha: str, prefix: str, output: list[str]) -> None:
    for entry in repo.objects.read_tree(sha):
        path = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.mode == "40000":
            _walk_tree(repo, entry.sha, path, output)
        else:
            obj_type = "blob"
            output.append(f"{entry.mode} {obj_type} {entry.sha}\t{path}")


def cmd_ls_tree(repo: Repo, rev: str) -> str:
    sha = resolve_revision(repo, rev)
    commit = repo.objects.read_commit(sha)
    output: list[str] = []
    _walk_tree(repo, commit.tree, "", output)
    return "\n".join(output)


def cmd_hash_object(repo: Repo, path: str, write: bool = False) -> str:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()
    data = file_path.read_bytes()
    sha = hash_object("blob", data)
    if write:
        repo.objects.write("blob", data)
    return sha


def cmd_rev_parse(repo: Repo, rev: str) -> str:
    return resolve_revision(repo, rev)
