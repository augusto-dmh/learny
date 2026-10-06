#!/usr/bin/env python3
"""Commit-message gate: every commit in a range follows Learny's commit contract.

The contract (stdlib only, so CI runs it without installing the backend):

- the header is a Conventional Commit with a type from the publishing skill's
  list: ``<type>(<kebab-scope>)!: <lowercase summary>``;
- the trailer block carries the line ``Assisted-by: Claude Code`` exactly — the
  attribution the owner chose for agent-assisted work;
- no ``Co-authored-by`` trailer names an AI agent, and no ``Made-with`` trailer
  appears at all.

Merge commits and commits authored by a ``[bot]`` account (Dependabot) are not
checked. Every failing commit is listed before the exit, so one run shows all of
them.

Usage:
    python3 backend/scripts/check_commits.py [RANGE]    # default: origin/main..HEAD

Exit codes: 0 every checked commit passes, 1 at least one fails, 2 git failed.
"""

from __future__ import annotations

import re
import subprocess
import sys

TYPES = (
    "feat",
    "fix",
    "docs",
    "refactor",
    "test",
    "chore",
    "build",
    "ci",
    "perf",
    "style",
    "revert",
)
HEADER_RE = re.compile(
    rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9]+(?:-[a-z0-9]+)*\))?!?: [a-z0-9][^\n]*$"
)
REQUIRED_TRAILER = "Assisted-by: Claude Code"
AGENT_NAMES = (
    "claude",
    "anthropic",
    "cursor",
    "copilot",
    "codex",
    "openai",
    "chatgpt",
    "gemini",
    "devin",
    "aider",
)
_TRAILER_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*: ")
_CO_AUTHOR = re.compile(r"^co-authored-by:(.*)$", re.IGNORECASE)
_MADE_WITH = re.compile(r"^made-with:", re.IGNORECASE)
_DEFAULT_RANGE = "origin/main..HEAD"


def _paragraphs(message: str) -> list[list[str]]:
    lines = [ln.rstrip() for ln in message.splitlines() if not ln.startswith("#")]
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])
    return [p for p in paragraphs if p]


def _trailer_block(paragraphs: list[list[str]]) -> list[str]:
    """The last paragraph, when it is not the header and every line is a trailer."""
    if len(paragraphs) < 2:
        return []
    last = paragraphs[-1]
    return last if all(_TRAILER_LINE.match(line) for line in last) else []


def check_message(message: str) -> list[str]:
    """Every rule the message breaks, as human-readable errors (empty when it passes)."""
    paragraphs = _paragraphs(message)
    if not paragraphs:
        return ["empty commit message"]
    errors: list[str] = []

    header = paragraphs[0][0]
    if not HEADER_RE.match(header):
        errors.append(
            f"header is not '<type>(<scope>): <lowercase summary>' with a type from "
            f"{', '.join(TYPES)}: {header!r}"
        )

    if REQUIRED_TRAILER not in _trailer_block(paragraphs):
        errors.append(f"missing the trailer line '{REQUIRED_TRAILER}' in the final trailer block")

    for line in (ln for p in paragraphs[1:] for ln in p):
        co_author = _CO_AUTHOR.match(line)
        if co_author and any(name in co_author.group(1).lower() for name in AGENT_NAMES):
            errors.append(f"Co-authored-by names an AI agent (use '{REQUIRED_TRAILER}'): {line!r}")
        if _MADE_WITH.match(line):
            errors.append(f"Made-with trailers are not allowed: {line!r}")
    return errors


def _commits(rng: str) -> list[tuple[str, str, str]]:
    """(sha, author name, full message) for each non-merge commit in the range."""
    out = subprocess.run(
        ["git", "log", "--no-merges", "--format=%H%x00%an%x00%B%x1e", rng],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if record:
            sha, author, body = record.split("\x00", 2)
            commits.append((sha, author, body))
    return commits


def main(argv: list[str]) -> int:
    rng = argv[1] if len(argv) > 1 else _DEFAULT_RANGE
    try:
        commits = _commits(rng)
    except subprocess.CalledProcessError as exc:
        print(f"check_commits: git log {rng} failed: {exc.stderr.strip()}", file=sys.stderr)
        return 2

    failed = checked = 0
    for sha, author, message in commits:
        if author.endswith("[bot]"):
            continue
        checked += 1
        errors = check_message(message)
        if errors:
            failed += 1
            for error in errors:
                print(f"FAIL {sha[:12]}: {error}")

    if failed:
        print(f"check_commits: {failed} of {checked} commit(s) in {rng} break the contract")
        return 1
    print(f"check_commits: {checked} commit(s) in {rng} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
