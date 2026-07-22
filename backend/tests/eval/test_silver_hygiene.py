"""Gitignore hygiene for the local silver eval tier (DEEP-05).

The silver tier holds copyrighted real-book cases, snippets, and result lines;
none of it may ever become tracked. These tests ask ``git`` itself — via
``git check-ignore`` — whether the silver paths are ignored, so the guarantee is
the real ignore resolution the maintainer's ``git add`` would see, not a reparse
of ``.gitignore``. The golden tier (``evals/results/``) must stay tracked, so a
too-broad rule that swallowed it would fail here too.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _is_ignored(relpath: str) -> bool:
    """True when ``git`` reports ``relpath`` (repo-root-relative) as ignored.

    ``git check-ignore`` exits 0 when the path is ignored and 1 when it is not;
    any other code is a real error (bad repo, bad invocation) and is surfaced.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=_REPO_ROOT,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"git check-ignore failed for {relpath!r}: "
            f"exit {result.returncode}, {result.stderr.decode(errors='replace')}"
        )
    return result.returncode == 0


def test_silver_cases_file_is_ignored() -> None:
    assert _is_ignored("evals/silver/cases.yaml")


def test_silver_results_are_ignored() -> None:
    assert _is_ignored("evals/silver/results/2026-07-21-abcdef0.jsonl")


def test_arbitrary_silver_data_is_ignored() -> None:
    # Any derived data the runner might drop under the tree is covered by the
    # whole-directory rule, not just the two known filenames.
    assert _is_ignored("evals/silver/derived/anything.txt")


def test_golden_results_stay_tracked() -> None:
    # The silver rule must be scoped to evals/silver/ — the committed golden-tier
    # results directory is not ignored.
    assert not _is_ignored("evals/results/2026-07-21-abcdef0.jsonl")
