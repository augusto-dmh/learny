#!/usr/bin/env python3
"""Render a Learny pull request body while omitting unused optional sections."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-file", required=True, type=Path)
    parser.add_argument("--changes-file", required=True, type=Path)
    parser.add_argument("--verification-file", required=True, type=Path)
    parser.add_argument("--screenshots-file", type=Path)
    parser.add_argument("--related-issues-file", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def read_required(path: Path, label: str) -> str:
    content = path.read_text(encoding="utf-8").strip()

    if not content:
        raise ValueError(f"{label} file must not be empty: {path}")

    return content


def read_optional(path: Path | None) -> str | None:
    if path is None:
        return None

    content = path.read_text(encoding="utf-8").strip()
    return content or None


def render_section(title: str, content: str) -> str:
    return f"## {title}\n\n{content}"


def main() -> int:
    args = parse_args()
    sections = [
        render_section("Summary", read_required(args.summary_file, "Summary")),
        render_section("Changes", read_required(args.changes_file, "Changes")),
        render_section("Verification", read_required(args.verification_file, "Verification")),
    ]

    screenshots = read_optional(args.screenshots_file)
    if screenshots is not None:
        sections.append(render_section("Screenshots", screenshots))

    related_issues = read_optional(args.related_issues_file)
    if related_issues is not None:
        sections.append(render_section("Related Issues", related_issues))

    body = "\n\n".join(sections) + "\n"

    if args.output is None:
        print(body, end="")
    else:
        args.output.write_text(body, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
