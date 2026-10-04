"""Hashing and loose-object serialization primitives.

Git addresses every object by the SHA-1 of ``<type> <size>\\0<data>``.
This module keeps that format in one place so the rest of the codebase
never hashes a partially formatted payload by hand.
"""

from __future__ import annotations

import hashlib
import zlib


OBJECT_TYPES = ("blob", "tree", "commit", "tag")


def sha1_bytes(data: bytes) -> str:
    """Return the 40-character lowercase hex SHA-1 of ``data``."""
    return hashlib.sha1(data).hexdigest()


def object_header(obj_type: str, data: bytes) -> bytes:
    """Build the ``<type> <size>\\0`` prefix for an object body."""
    return f"{obj_type} {len(data)}".encode("ascii") + b"\x00"


def hash_object(obj_type: str, data: bytes) -> str:
    """Hash an object body and return its hex SHA-1."""
    if obj_type not in OBJECT_TYPES:
        raise ValueError(f"unknown object type: {obj_type}")
    return sha1_bytes(object_header(obj_type, data) + data)


def compress_object(obj_type: str, data: bytes) -> bytes:
    """Return the full compressed loose-object file payload."""
    return zlib.compress(object_header(obj_type, data) + data)


def decompress_object(raw: bytes) -> tuple[str, bytes]:
    """Decompress a loose object and return ``(obj_type, body)``."""
    payload = zlib.decompress(raw)
    header, _, body = payload.partition(b"\x00")
    if not _:
        raise ValueError("corrupt loose object: missing header terminator")
    obj_type, _, size_raw = header.partition(b" ")
    obj_type = obj_type.decode("ascii", errors="replace")
    if obj_type not in OBJECT_TYPES:
        raise ValueError(f"unknown object type: {obj_type}")
    try:
        expected_size = int(size_raw)
    except ValueError as exc:
        raise ValueError("corrupt loose object: invalid size") from exc
    if len(body) != expected_size:
        raise ValueError(
            f"corrupt loose object: expected {expected_size} bytes, got {len(body)}"
        )
    return obj_type, body
