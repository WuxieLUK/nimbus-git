"""Repository discovery and layout helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import NotARepositoryError
from .objects import ObjectDB


@dataclass(frozen=True)
class Repo:
    worktree: Path
    gitdir: Path

    @property
    def objects_dir(self) -> Path:
        return self.gitdir / "objects"

    @property
    def refs_dir(self) -> Path:
        return self.gitdir / "refs"

    @property
    def heads_dir(self) -> Path:
        return self.refs_dir / "heads"

    @property
    def tags_dir(self) -> Path:
        return self.refs_dir / "tags"

    @property
    def index_path(self) -> Path:
        return self.gitdir / "index"

    @property
    def head_path(self) -> Path:
        return self.gitdir / "HEAD"

    @property
    def objects(self) -> ObjectDB:
        return ObjectDB(self.objects_dir)


def discover(start: Path | str | None = None) -> Repo:
    """Walk upward from ``start`` to find the nearest Git repository."""
    current = Path(start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        gitdir = directory / ".git"
        if gitdir.is_dir():
            return Repo(worktree=directory, gitdir=gitdir)
        if gitdir.is_file():
            # Support ``gitdir:`` pointer files created by worktrees.
            text = gitdir.read_text(encoding="utf-8").strip()
            prefix = "gitdir:"
            if text.startswith(prefix):
                target = (directory / text[len(prefix) :].strip()).resolve()
                if target.is_dir():
                    return Repo(worktree=directory, gitdir=target)
    raise NotARepositoryError("not a git repository (or any of the parent directories)")


def init_repository(path: Path | str, default_branch: str = "main") -> Repo:
    """Create a new repository layout without depending on the git binary."""
    worktree = Path(path).resolve()
    gitdir = worktree / ".git"
    if gitdir.exists():
        raise FileExistsError(f"repository already exists: {worktree}")
    (gitdir / "objects" / "info").mkdir(parents=True, exist_ok=True)
    (gitdir / "objects" / "pack").mkdir(parents=True, exist_ok=True)
    (gitdir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (gitdir / "refs" / "tags").mkdir(parents=True, exist_ok=True)
    (gitdir / "info").mkdir(parents=True, exist_ok=True)
    (gitdir / "hooks").mkdir(parents=True, exist_ok=True)
    (gitdir / "info" / "exclude").write_text(
        "# git ls-files --others --exclude-from=.git/info/exclude\n"
        "# Lines that start with '#' are comments.\n",
        encoding="utf-8",
    )
    (gitdir / "description").write_text(
        "Unnamed repository; edit this file 'description' to name the repository.\n",
        encoding="utf-8",
    )
    (gitdir / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tfilemode = false\n"
        "\tbare = false\n"
        "\tlogallrefupdates = true\n",
        encoding="utf-8",
    )
    repo = Repo(worktree=worktree, gitdir=gitdir)
    set_head_branch(repo, default_branch)
    return repo


def set_head_branch(repo: Repo, branch: str) -> None:
    repo.head_path.write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")


def set_head_detached(repo: Repo, sha: str) -> None:
    repo.head_path.write_text(f"{sha}\n", encoding="utf-8")
