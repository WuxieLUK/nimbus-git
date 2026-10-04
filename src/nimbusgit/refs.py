"""Branch, tag, and HEAD resolution."""

from __future__ import annotations

from pathlib import Path

from .errors import RefNotFoundError
from .objects import is_full_sha
from .repo import Repo


def _read_head_raw(repo: Repo) -> str:
    try:
        return repo.head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RefNotFoundError("HEAD does not exist") from exc


def read_head(repo: Repo) -> tuple[str | None, str | None]:
    """Return ``(branch_name, commit_sha)`` for HEAD.

    ``branch_name`` is None on a detached HEAD; ``commit_sha`` is None on an
    unborn branch.
    """
    raw = _read_head_raw(repo)
    if raw.startswith("ref: "):
        ref = raw[5:]
        try:
            sha = (repo.gitdir / ref).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ref, None
        return ref, (sha or None)
    return None, (raw or None)


def current_branch(repo: Repo) -> str | None:
    branch, _ = read_head(repo)
    if branch and branch.startswith("refs/heads/"):
        return branch[len("refs/heads/") :]
    return None


def read_ref(repo: Repo, ref: str) -> str:
    """Read the value of a fully qualified ref such as ``refs/heads/main``."""
    path = repo.gitdir / ref
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RefNotFoundError(f"reference not found: {ref}") from exc
    if not value:
        raise RefNotFoundError(f"reference is empty: {ref}")
    return value


def write_ref(repo: Repo, ref: str, sha: str) -> None:
    if not is_full_sha(sha):
        raise ValueError(f"invalid object id: {sha}")
    path = repo.gitdir / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sha + "\n", encoding="utf-8")


def update_branch(repo: Repo, branch: str, sha: str) -> None:
    write_ref(repo, f"refs/heads/{branch}", sha)


def list_branches(repo: Repo) -> list[str]:
    if not repo.heads_dir.is_dir():
        return []
    return sorted(path.name for path in repo.heads_dir.iterdir() if path.is_file())


def list_tags(repo: Repo) -> list[str]:
    if not repo.tags_dir.is_dir():
        return []
    return sorted(path.name for path in repo.tags_dir.iterdir() if path.is_file())


def resolve_revision(repo: Repo, revision: str) -> str:
    """Resolve a branch name, short sha, full sha, tag, or HEAD to a commit id."""
    if revision in ("HEAD", "@"):
        _, sha = read_head(repo)
        if sha:
            return sha
        raise RefNotFoundError("HEAD does not point at a commit")
    if is_full_sha(revision):
        return revision

    candidates = [
        f"refs/heads/{revision}",
        f"refs/tags/{revision}",
        revision,
    ]
    for ref in candidates:
        try:
            return read_ref(repo, ref)
        except RefNotFoundError:
            continue

    # Resolve a unique short object id prefix.
    matches = _matching_objects(repo, revision)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RefNotFoundError(f"ambiguous revision: {revision}")
    raise RefNotFoundError(f"unknown revision: {revision}")


def _matching_objects(repo: Repo, prefix: str) -> list[str]:
    if not repo.objects_dir.is_dir():
        return []
    matches: list[str] = []
    for first_dir in repo.objects_dir.iterdir():
        if not first_dir.is_dir() or len(first_dir.name) != 2:
            continue
        for obj_file in first_dir.iterdir():
            full = first_dir.name + obj_file.name
            if full.startswith(prefix):
                matches.append(full)
    return matches


def branch_exists(repo: Repo, branch: str) -> bool:
    return (repo.heads_dir / branch).is_file()
