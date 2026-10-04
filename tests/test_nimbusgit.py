from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from nimbusgit.commands import (
    cmd_add,
    cmd_branch,
    cmd_checkout,
    cmd_commit,
    cmd_diff,
    cmd_init,
    cmd_log,
    cmd_status,
    cmd_tag,
)
from nimbusgit.diff import myers_diff, unified_diff
from nimbusgit.hashing import hash_object
from nimbusgit.index import IndexEntry, read_index, write_index
from nimbusgit.objects import GitCommit, TreeEntry, parse_commit, parse_tree, serialize_commit, serialize_tree
from nimbusgit.refs import current_branch, read_head
from nimbusgit.repo import discover


class NimbusGitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.tmp.name) / "repo"
        self.repo_dir.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.repo_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def init_repo(self) -> None:
        cmd_init(str(self.repo_dir))


class HashingTests(NimbusGitTestCase):
    def test_blob_hash_matches_git_spec(self) -> None:
        data = b"hello\n"
        expected = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        self.assertEqual(hash_object("blob", data), expected)
        self.assertEqual(expected, "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValueError):
            hash_object("banana", b"x")


class ObjectTests(unittest.TestCase):
    def test_tree_roundtrip(self) -> None:
        entries = [
            TreeEntry("100644", "beta", "1" * 40),
            TreeEntry("40000", "alpha", "2" * 40),
        ]
        parsed = parse_tree(serialize_tree(entries))
        self.assertEqual([entry.name for entry in parsed], ["alpha", "beta"])

    def test_commit_roundtrip(self) -> None:
        commit = GitCommit(tree="3" * 40, parents=["4" * 40], message="subject\n\nbody")
        parsed = parse_commit(serialize_commit(commit))
        self.assertEqual(parsed.tree, commit.tree)
        self.assertEqual(parsed.parents, ["4" * 40])
        self.assertIn("subject", parsed.message)


class IndexTests(NimbusGitTestCase):
    def test_index_roundtrip(self) -> None:
        self.init_repo()
        repo = discover(self.repo_dir)
        entry = IndexEntry(1, 2, 3, 4, 5, 6, 0o100644, 7, 8, 3, "9" * 40, "dir/file.txt")
        write_index(repo, [entry])
        parsed = read_index(repo)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].path, "dir/file.txt")
        self.assertEqual(parsed[0].sha, "9" * 40)


class DiffTests(unittest.TestCase):
    def test_myers_replaces_line(self) -> None:
        self.assertEqual(myers_diff(["a"], ["b"]), [("delete", 0, None), ("insert", None, 0)])

    def test_myers_insertion(self) -> None:
        self.assertEqual(
            myers_diff(["a", "c"], ["a", "b", "c"]),
            [("equal", 0, 0), ("insert", None, 1), ("equal", 1, 2)],
        )

    def test_unified_diff_headers(self) -> None:
        output = unified_diff(["a"], ["b"], "a/x", "b/x")
        self.assertEqual(output[0], "--- a/x")
        self.assertEqual(output[1], "+++ b/x")
        self.assertIn("@@ -1 +1 @@", output[2])


class WorkflowTests(NimbusGitTestCase):
    def test_add_commit_status_log(self) -> None:
        self.init_repo()
        repo = discover(self.repo_dir)
        self.write("readme.md", "hello\n")
        cmd_add(repo, self.repo_dir, [])
        cmd_commit(repo, "initial commit")
        self.assertEqual(cmd_status(repo), "On branch main\nnothing to commit, working tree clean")
        self.assertIn("initial commit", cmd_log(repo))
        branch, sha = read_head(repo)
        self.assertEqual(branch, "refs/heads/main")
        self.assertEqual(len(sha), 40)

    def test_diff_after_edit(self) -> None:
        self.init_repo()
        repo = discover(self.repo_dir)
        self.write("file.txt", "one\ntwo\n")
        cmd_add(repo, self.repo_dir, [])
        cmd_commit(repo, "base")
        self.write("file.txt", "one\nTWO\nthree\n")
        diff = cmd_diff(repo)
        self.assertIn("-two", diff)
        self.assertIn("+TWO", diff)
        self.assertIn("+three", diff)

    def test_branch_checkout_switches_files(self) -> None:
        self.init_repo()
        repo = discover(self.repo_dir)
        self.write("tracked.txt", "main version\n")
        cmd_add(repo, self.repo_dir, [])
        cmd_commit(repo, "main commit")
        cmd_branch(repo, "feature")
        cmd_checkout(repo, "feature")
        self.write("tracked.txt", "feature version\n")
        cmd_add(repo, self.repo_dir, [])
        cmd_commit(repo, "feature commit")
        cmd_checkout(repo, "main")
        self.assertEqual((self.repo_dir / "tracked.txt").read_text(encoding="utf-8"), "main version\n")
        self.assertEqual(current_branch(repo), "main")

    def test_tags_are_created_and_resolved(self) -> None:
        self.init_repo()
        repo = discover(self.repo_dir)
        self.write("file.txt", "content\n")
        cmd_add(repo, self.repo_dir, [])
        cmd_commit(repo, "commit")
        cmd_tag(repo, "v1.0.0")
        self.assertIn("v1.0.0", cmd_tag(repo))


if __name__ == "__main__":
    unittest.main()
