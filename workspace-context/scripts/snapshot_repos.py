#!/usr/bin/env python3
"""Generate a compact git repository snapshot for a multi-repo workspace."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
from pathlib import Path


SKIP_DIRS = {
    ".cache",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "bazel-bin",
    "bazel-out",
    "bazel-testlogs",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def find_repos(root: Path, max_depth: int) -> list[Path]:
    repos: list[Path] = []
    root = root.resolve()

    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        rel_parts = current_path.relative_to(root).parts
        depth = len(rel_parts)

        git_marker = current_path / ".git"
        if git_marker.exists():
            repos.append(current_path)
            dirs[:] = []
            continue

        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".cache")]

        if depth >= max_depth:
            dirs[:] = []

    return sorted(repos)


def repo_status(repo: Path, root: Path) -> dict[str, str]:
    status = run_git(repo, ["status", "--porcelain"])
    commit = run_git(repo, ["rev-parse", "HEAD"])
    branch = run_git(repo, ["branch", "--show-current"]) or "(detached)"
    subject = run_git(repo, ["log", "-1", "--pretty=%s"])
    author_date = run_git(repo, ["log", "-1", "--pretty=%aI"])

    try:
        rel_path = str(repo.resolve().relative_to(root.resolve()))
    except ValueError:
        rel_path = str(repo.resolve())

    return {
        "path": rel_path or ".",
        "branch": branch,
        "commit": commit,
        "short_commit": commit[:12] if commit else "",
        "dirty": "yes" if status else "no",
        "changed_lines": str(len(status.splitlines())) if status else "0",
        "author_date": author_date,
        "subject": subject,
    }


def render_snapshot(root: Path, repos: list[Path]) -> str:
    now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# Workspace Snapshot",
        "",
        f"Generated: {now}",
        f"Root: `{root.resolve()}`",
        f"Repositories found: {len(repos)}",
        "",
    ]

    for repo in repos:
        info = repo_status(repo, root)
        lines.extend(
            [
                f"## {info['path']}",
                "",
                f"- branch: `{info['branch']}`",
                f"- commit: `{info['short_commit']}`",
                f"- dirty: `{info['dirty']}` ({info['changed_lines']} changed status lines)",
                f"- latest commit date: `{info['author_date']}`",
                f"- latest commit subject: {info['subject']}",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Workspace root to scan")
    parser.add_argument("--output", help="Write markdown snapshot to this path")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum directory depth to scan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    repos = find_repos(root, args.max_depth)
    output = render_snapshot(root, repos)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
