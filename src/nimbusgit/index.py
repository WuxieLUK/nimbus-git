"""Read and write the Git index (dircache) file."""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import IndexError
from .objects import hex_to_bytes, is_full_sha
from .repo import Repo


INDEX_SIGNATURE = b"DIRC"
INDEX_VERSION = 2
ENTRY_FIXED_LEN = 62
NAME_LEN_CAP = 0x0FFF
REGULAR_MODE = 0o100644
EXECUTABLE_MODE = 0o100755


@dataclass
class IndexEntry:
    ctime_s: int
    ctime_ns: int
    mtime_s: int
    mtime_ns: int
    dev: int
    ino: int
    mode: int
    uid: int
    gid: int
    size: int
    sha: str
    path: str
    stage: int = 0


def read_index(repo: Repo) -> list[IndexEntry]:
    """Read the index, returning an empty list for a fresh repository."""
    if not repo.index_path.is_file():
        return []
    data = repo.index_path.read_bytes()
    if len(data) < 12 + 20:
        raise IndexError("index file is too short")
    signature, version, count = struct.unpack_from(">4sII", data, 0)
    if signature != INDEX_SIGNATURE:
        raise IndexError("index signature mismatch (not a Git index?)")
    if version not in (2, 3):
        raise IndexError(f"unsupported index version: {version}")

    expected_checksum = data[-20:]
    if hashlib.sha1(data[:-20]).digest() != expected_checksum:
        raise IndexError("index checksum mismatch")

    entries: list[IndexEntry] = []
    offset = 12
    for _ in range(count):
        if offset + ENTRY_FIXED_LEN > len(data):
            raise IndexError("index entry runs past end of file")
        (
            ctime_s,
            ctime_ns,
            mtime_s,
            mtime_ns,
            dev,
            ino,
            mode,
            uid,
            gid,
            size,
            sha_raw,
            flags,
        ) = struct.unpack_from(">10I20sH", data, offset)
        name_len = flags & NAME_LEN_CAP
        stage = (flags >> 12) & 0x3
        path_start = offset + ENTRY_FIXED_LEN
        nul = data.find(b"\x00", path_start)
        if nul == -1:
            raise IndexError("index entry has no path terminator")
        path = data[path_start:nul].decode("utf-8", errors="replace")
        if name_len < NAME_LEN_CAP and len(data[path_start:nul]) != name_len:
            raise IndexError("index entry path length mismatch")
        consumed = ENTRY_FIXED_LEN + (nul - path_start) + 1
        pad = (8 - (consumed % 8)) % 8
        offset += consumed + pad
        entries.append(
            IndexEntry(
                ctime_s=ctime_s,
                ctime_ns=ctime_ns,
                mtime_s=mtime_s,
                mtime_ns=mtime_ns,
                dev=dev,
                ino=ino,
                mode=mode,
                uid=uid,
                gid=gid,
                size=size,
                sha=sha_raw.hex(),
                path=path,
                stage=stage,
            )
        )
    return entries


def write_index(repo: Repo, entries: list[IndexEntry]) -> None:
    """Write a version-2 index with no extensions."""
    ordered = sorted(entries, key=lambda entry: entry.path)
    chunks = [struct.pack(">4sII", INDEX_SIGNATURE, INDEX_VERSION, len(ordered))]
    for entry in ordered:
        name = entry.path.encode("utf-8")
        if not is_full_sha(entry.sha):
            raise ValueError(f"invalid object id in index entry: {entry.sha}")
        name_len = min(len(name), NAME_LEN_CAP)
        flags = ((entry.stage & 0x3) << 12) | name_len
        fixed = struct.pack(
            ">10I20sH",
            entry.ctime_s,
            entry.ctime_ns,
            entry.mtime_s,
            entry.mtime_ns,
            entry.dev,
            entry.ino,
            entry.mode,
            entry.uid,
            entry.gid,
            entry.size,
            hex_to_bytes(entry.sha),
            flags,
        )
        body = fixed + name + b"\x00"
        pad = (8 - (len(body) % 8)) % 8
        chunks.append(body + b"\x00" * pad)
    content = b"".join(chunks)
    checksum = hashlib.sha1(content).digest()
    repo.index_path.parent.mkdir(parents=True, exist_ok=True)
    repo.index_path.write_bytes(content + checksum)


def stat_to_index_entry(repo: Repo, absolute_path: Path, relative_path: str, sha: str) -> IndexEntry:
    """Build an index entry from a file on disk."""
    st = absolute_path.stat()
    # Windows has no meaningful POSIX inode/uid/gid; keep them deterministic.
    dev = getattr(st, "st_dev", 0)
    ino = getattr(st, "st_ino", 0)
    uid = getattr(st, "st_uid", 0)
    gid = getattr(st, "st_gid", 0)
    mode = REGULAR_MODE
    if os.name != "nt" and st.st_mode & 0o111:
        mode = EXECUTABLE_MODE
    def _u32(value: int) -> int:
        return int(value) & 0xFFFFFFFF

    return IndexEntry(
        ctime_s=_u32(st.st_ctime),
        ctime_ns=_u32(getattr(st, "st_ctime_ns", 0) % 1_000_000_000),
        mtime_s=_u32(st.st_mtime),
        mtime_ns=_u32(getattr(st, "st_mtime_ns", 0) % 1_000_000_000),
        dev=_u32(dev),
        ino=_u32(ino),
        mode=mode,
        uid=_u32(uid),
        gid=_u32(gid),
        size=_u32(st.st_size),
        sha=sha,
        path=relative_path,
    )
