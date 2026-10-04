"""Git object model: blobs, trees, commits, and tags."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import InvalidObjectError
from .hashing import compress_object, decompress_object, hash_object


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    name: str
    sha: str


@dataclass
class GitCommit:
    tree: str
    parents: list[str] = field(default_factory=list)
    author: str = "Nimbus <nimbus@local> 0 +0000"
    committer: str = "Nimbus <nimbus@local> 0 +0000"
    message: str = ""


@dataclass
class GitTag:
    object: str
    obj_type: str
    tag: str
    tagger: str
    message: str = ""


def hex_to_bytes(sha: str) -> bytes:
    return bytes.fromhex(sha)


def bytes_to_hex(raw: bytes) -> str:
    return raw.hex()


def is_full_sha(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value.lower())


def parse_tree(data: bytes) -> list[TreeEntry]:
    """Parse the binary contents of a Git tree object."""
    entries: list[TreeEntry] = []
    i = 0
    while i < len(data):
        space = data.find(b" ", i)
        if space == -1:
            raise InvalidObjectError("corrupt tree: missing mode separator")
        mode = data[i:space].decode("ascii")
        nul = data.find(b"\x00", space + 1)
        if nul == -1:
            raise InvalidObjectError("corrupt tree: missing path terminator")
        name = data[space + 1 : nul].decode("utf-8", errors="replace")
        i = nul + 1
        if i + 20 > len(data):
            raise InvalidObjectError("corrupt tree: truncated object id")
        sha = bytes_to_hex(data[i : i + 20])
        i += 20
        entries.append(TreeEntry(mode=mode, name=name, sha=sha))
    return entries


def serialize_tree(entries: list[TreeEntry]) -> bytes:
    """Serialize tree entries in the canonical (sorted) Git order."""
    ordered = sorted(entries, key=_tree_sort_key)
    chunks: list[bytes] = []
    for entry in ordered:
        name = entry.name.encode("utf-8")
        chunks.append(entry.mode.encode("ascii") + b" " + name + b"\x00" + hex_to_bytes(entry.sha))
    return b"".join(chunks)


def _tree_sort_key(entry: TreeEntry) -> bytes:
    # Directories sort as if their name ended with '/'.
    name = entry.name.encode("utf-8")
    return name + b"/" if entry.mode == "40000" else name


def parse_commit(data: bytes) -> GitCommit:
    """Parse a commit object body."""
    text = data.decode("utf-8", errors="replace")
    header_lines: list[str] = []
    message_lines: list[str] = []
    saw_blank = False
    for line in text.splitlines():
        if saw_blank:
            message_lines.append(line)
        elif line == "":
            saw_blank = True
        else:
            header_lines.append(line)
    if not header_lines:
        raise InvalidObjectError("corrupt commit: empty header")

    tree: str | None = None
    parents: list[str] = []
    author = "Nimbus <nimbus@local> 0 +0000"
    committer = "Nimbus <nimbus@local> 0 +0000"
    for line in header_lines:
        if line.startswith("tree ") and len(line) >= 45:
            tree = line[5:45]
        elif line.startswith("parent ") and len(line) >= 47:
            parents.append(line[7:47])
        elif line.startswith("author "):
            author = line[7:]
        elif line.startswith("committer "):
            committer = line[10:]
    if tree is None or not is_full_sha(tree):
        raise InvalidObjectError("corrupt commit: missing tree")
    return GitCommit(
        tree=tree,
        parents=parents,
        author=author,
        committer=committer,
        message="\n".join(message_lines),
    )


def serialize_commit(commit: GitCommit) -> bytes:
    lines = [f"tree {commit.tree}"]
    for parent in commit.parents:
        lines.append(f"parent {parent}")
    lines.append(f"author {commit.author}")
    lines.append(f"committer {commit.committer}")
    lines.append("")
    message = commit.message
    if not message.endswith("\n"):
        message += "\n"
    return ("\n".join(lines) + "\n" + message).encode("utf-8")


def parse_tag(data: bytes) -> GitTag:
    text = data.decode("utf-8", errors="replace")
    header_lines: list[str] = []
    message_lines: list[str] = []
    saw_blank = False
    for line in text.splitlines():
        if saw_blank:
            message_lines.append(line)
        elif line == "":
            saw_blank = True
        else:
            header_lines.append(line)
    obj = obj_type = tag = tagger = ""
    for line in header_lines:
        if line.startswith("object "):
            obj = line[7:47]
        elif line.startswith("type "):
            obj_type = line[5:]
        elif line.startswith("tag "):
            tag = line[4:]
        elif line.startswith("tagger "):
            tagger = line[7:]
    if not is_full_sha(obj):
        raise InvalidObjectError("corrupt tag: missing object")
    return GitTag(obj, obj_type, tag, tagger, "\n".join(message_lines))


def serialize_tag(tag: GitTag) -> bytes:
    lines = [f"object {tag.object}", f"type {tag.obj_type}", f"tag {tag.tag}", f"tagger {tag.tagger}", ""]
    message = tag.message if tag.message.endswith("\n") else tag.message + "\n"
    return ("\n".join(lines) + "\n" + message).encode("utf-8")


class ObjectDB:
    """Read and write loose objects under ``.git/objects``."""

    def __init__(self, objects_dir: Path) -> None:
        self.objects_dir = Path(objects_dir)

    def object_path(self, sha: str) -> Path:
        if not is_full_sha(sha):
            raise InvalidObjectError(f"invalid object id: {sha}")
        return self.objects_dir / sha[:2] / sha[2:]

    def exists(self, sha: str) -> bool:
        return self.object_path(sha).is_file()

    def read(self, sha: str) -> tuple[str, bytes]:
        """Return ``(obj_type, body)`` for an object id."""
        path = self.object_path(sha)
        if not path.is_file():
            raise InvalidObjectError(f"object not found: {sha}")
        try:
            return decompress_object(path.read_bytes())
        except (OSError, ValueError, EOFError) as exc:
            raise InvalidObjectError(f"corrupt object {sha}: {exc}") from exc

    def write(self, obj_type: str, data: bytes) -> str:
        """Persist an object and return its id."""
        sha = hash_object(obj_type, data)
        path = self.object_path(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(compress_object(obj_type, data))
        return sha

    def read_commit(self, sha: str) -> GitCommit:
        obj_type, data = self.read(sha)
        if obj_type != "commit":
            raise InvalidObjectError(f"object {sha} is a {obj_type}, not a commit")
        return parse_commit(data)

    def read_tree(self, sha: str) -> list[TreeEntry]:
        obj_type, data = self.read(sha)
        if obj_type != "tree":
            raise InvalidObjectError(f"object {sha} is a {obj_type}, not a tree")
        return parse_tree(data)

    def read_blob(self, sha: str) -> bytes:
        obj_type, data = self.read(sha)
        if obj_type != "blob":
            raise InvalidObjectError(f"object {sha} is a {obj_type}, not a blob")
        return data
