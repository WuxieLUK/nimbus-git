"""Command-line interface for nimbus-git."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .commands import (
    cmd_add,
    cmd_branch,
    cmd_cat_file,
    cmd_checkout,
    cmd_commit,
    cmd_diff,
    cmd_hash_object,
    cmd_init,
    cmd_log,
    cmd_ls_files,
    cmd_ls_tree,
    cmd_rev_parse,
    cmd_status,
    cmd_tag,
)
from .errors import NimbusGitError
from .repo import discover


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nimbus",
        description="A from-scratch Git implementation with zero runtime dependencies.",
    )
    parser.add_argument("--version", action="version", version=f"nimbus-git {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create an empty repository").add_argument("path", nargs="?")

    add_parser = sub.add_parser("add", help="Stage files in the index")
    add_parser.add_argument("pathspec", nargs="*")

    commit_parser = sub.add_parser("commit", help="Record a snapshot")
    commit_parser.add_argument("-m", "--message", required=True)
    commit_parser.add_argument("--allow-empty", action="store_true")

    sub.add_parser("status", help="Show working-tree status")

    log_parser = sub.add_parser("log", help="Show commit history")
    log_parser.add_argument("-n", "--max-count", type=int)

    diff_parser = sub.add_parser("diff", help="Show changes")
    diff_parser.add_argument("--cached", action="store_true")
    diff_parser.add_argument("revs", nargs="*")
    diff_parser.add_argument("--", dest="paths", nargs="*")

    branch_parser = sub.add_parser("branch", help="List or create branches")
    branch_parser.add_argument("-d", "--delete", action="store_true")
    branch_parser.add_argument("name", nargs="?")
    branch_parser.add_argument("start_point", nargs="?")

    checkout_parser = sub.add_parser("checkout", help="Switch branches")
    checkout_parser.add_argument("-f", "--force", action="store_true")
    checkout_parser.add_argument("branch")

    switch_parser = sub.add_parser("switch", help="Switch branches")
    switch_parser.add_argument("-f", "--force", action="store_true")
    switch_parser.add_argument("branch")

    tag_parser = sub.add_parser("tag", help="List or create lightweight tags")
    tag_parser.add_argument("-d", "--delete", action="store_true")
    tag_parser.add_argument("name", nargs="?")
    tag_parser.add_argument("rev", nargs="?")

    cat_parser = sub.add_parser("cat-file", help="Inspect objects")
    cat_parser.add_argument("-t", "--type", action="store_true", dest="type_only")
    cat_parser.add_argument("-s", "--size", action="store_true", dest="size_only")
    cat_parser.add_argument("-p", "--pretty", action="store_true")
    cat_parser.add_argument("sha")

    sub.add_parser("ls-files", help="List staged files")

    ls_tree_parser = sub.add_parser("ls-tree", help="List tree contents")
    ls_tree_parser.add_argument("rev")

    hash_parser = sub.add_parser("hash-object", help="Hash a file")
    hash_parser.add_argument("-w", "--write", action="store_true")
    hash_parser.add_argument("path")

    rev_parse_parser = sub.add_parser("rev-parse", help="Resolve a revision")
    rev_parse_parser.add_argument("rev")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    try:
        if args.command == "init":
            print(cmd_init(args.path))
            return 0

        repo = discover(cwd)
        if args.command == "add":
            print(cmd_add(repo, cwd, args.pathspec))
        elif args.command == "commit":
            print(cmd_commit(repo, args.message, args.allow_empty))
        elif args.command == "status":
            print(cmd_status(repo))
        elif args.command == "log":
            print(cmd_log(repo, args.max_count))
        elif args.command == "diff":
            paths = args.paths if getattr(args, "paths", None) else None
            print(cmd_diff(repo, args.cached, args.revs, paths))
        elif args.command == "branch":
            print(cmd_branch(repo, args.name, args.delete, args.start_point))
        elif args.command in ("checkout", "switch"):
            print(cmd_checkout(repo, args.branch, args.force))
        elif args.command == "tag":
            print(cmd_tag(repo, args.name, args.delete, args.rev))
        elif args.command == "cat-file":
            print(cmd_cat_file(repo, args.sha, args.pretty, args.type_only, args.size_only))
        elif args.command == "ls-files":
            print(cmd_ls_files(repo))
        elif args.command == "ls-tree":
            print(cmd_ls_tree(repo, args.rev))
        elif args.command == "hash-object":
            print(cmd_hash_object(repo, args.path, args.write))
        elif args.command == "rev-parse":
            print(cmd_rev_parse(repo, args.rev))
        else:
            parser.print_help()
            return 1
        return 0
    except NimbusGitError as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
