"""Line-based Myers diff and unified-diff rendering."""

from __future__ import annotations

from collections.abc import Sequence


def myers_diff(a: Sequence[str], b: Sequence[str]) -> list[tuple[str, int | None, int | None]]:
    """Return an edit script of ``("equal"|"delete"|"insert", a_idx, b_idx)``.

    Indexes are zero-based; exactly one index is ``None`` for non-equal edits.
    The implementation is the classic O((N+M)D) greedy Myers algorithm.
    """
    n, m = len(a), len(b)
    max_d = n + m
    v = {1: 0}
    trace: list[dict[int, int]] = []

    for d in range(max_d + 1):
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v.get(k - 1, -10**9) < v.get(k + 1, -10**9)):
                x = v.get(k + 1, -10**9)
            else:
                x = v.get(k - 1, -10**9) + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v[k] = x
            if x >= n and y >= m:
                trace.append(v.copy())
                return _backtrack(trace, a, b)
        trace.append(v.copy())

    return _backtrack(trace, a, b)


def _backtrack(
    trace: list[dict[int, int]], a: Sequence[str], b: Sequence[str]
) -> list[tuple[str, int | None, int | None]]:
    x, y = len(a), len(b)
    edits: list[tuple[str, int | None, int | None]] = []
    for d in range(len(trace) - 1, 0, -1):
        v = trace[d]
        k = x - y
        if k == -d or (k != d and v.get(k - 1, -10**9) < v.get(k + 1, -10**9)):
            prev_k = k + 1
        else:
            prev_k = k - 1
        prev_x = v.get(prev_k, -10**9)
        prev_y = prev_x - prev_k

        while x > prev_x and y > prev_y:
            edits.append(("equal", x - 1, y - 1))
            x -= 1
            y -= 1

        if x == prev_x:
            edits.append(("insert", None, y - 1))
            y -= 1
        else:
            edits.append(("delete", x - 1, None))
            x -= 1

        x, y = prev_x, prev_y

    while x > 0 and y > 0:
        edits.append(("equal", x - 1, y - 1))
        x -= 1
        y -= 1
    edits.reverse()
    return edits


def is_binary(data: bytes) -> bool:
    return b"\x00" in data


def unified_diff(
    a: Sequence[str],
    b: Sequence[str],
    fromfile: str,
    tofile: str,
    context: int = 3,
) -> list[str]:
    """Render a unified diff as a list of lines (without trailing newlines)."""
    edits = myers_diff(a, b)
    items: list[tuple[str, int | None, int | None, str]] = []
    for op, a_idx, b_idx in edits:
        if op == "equal":
            items.append((" ", a_idx, b_idx, a[a_idx]))
        elif op == "delete":
            items.append(("-", a_idx, None, a[a_idx]))
        else:
            items.append(("+", None, b_idx, b[b_idx]))

    changed = [i for i, item in enumerate(items) if item[0] != " "]
    if not changed:
        return []

    groups: list[tuple[int, int]] = []
    group_start: int | None = None
    group_end: int | None = None
    for index in changed:
        start = max(0, index - context)
        end = min(len(items) - 1, index + context)
        if group_start is None:
            group_start, group_end = start, end
        elif start <= group_end + 1:
            group_end = max(group_end, end)
        else:
            groups.append((group_start, group_end))
            group_start, group_end = start, end
    assert group_start is not None and group_end is not None
    groups.append((group_start, group_end))

    output = [f"--- {fromfile}", f"+++ {tofile}"]
    for start, end in groups:
        block = items[start : end + 1]
        old_lines = [item for item in block if item[0] in (" ", "-")]
        new_lines = [item for item in block if item[0] in (" ", "+")]
        old_numbers = [item[1] + 1 for item in old_lines if item[1] is not None]
        new_numbers = [item[2] + 1 for item in new_lines if item[2] is not None]
        old_start = min(old_numbers) if old_numbers else 0
        new_start = min(new_numbers) if new_numbers else 0
        old_spec = f"{old_start},{len(old_lines)}" if len(old_lines) != 1 else str(old_start)
        new_spec = f"{new_start},{len(new_lines)}" if len(new_lines) != 1 else str(new_start)
        output.append(f"@@ -{old_spec} +{new_spec} @@")
        for item in block:
            output.append(item[0] + item[3])
    return output
