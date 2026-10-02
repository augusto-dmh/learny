"""The commit-message gate CI runs over every pull-request commit.

Two contracts, one script (``backend/scripts/check_commits.py``):

- the message rules — a Conventional Commit header from the publishing skill's
  type list, the ``Assisted-by: Claude Code`` trailer the owner chose for agent
  work, and no agent ``Co-authored-by`` / ``Made-with`` trailers;
- the range walk — every non-merge, non-bot commit in the range is checked and
  every failing SHA is named before the exit.

The rules are asserted on the pure function; the walk is asserted against a real
temporary git repository, because merge and bot skipping only exist there.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_commits.py"
_spec = importlib.util.spec_from_file_location("check_commits", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_commits = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_commits)

_TRAILER = "Assisted-by: Claude Code"
_TYPES = (
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
_AGENTS = (
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


def _msg(header: str, *trailers: str, body: str = "") -> str:
    parts = [header]
    if body:
        parts.append(body)
    if trailers:
        parts.append("\n".join(trailers))
    return "\n\n".join(parts) + "\n"


# --- header ----------------------------------------------------------------------


@pytest.mark.parametrize("ctype", _TYPES)
def test_header_accepts_each_allowed_type(ctype: str) -> None:
    assert check_commits.check_message(_msg(f"{ctype}(ci): gate commit messages", _TRAILER)) == []


@pytest.mark.parametrize(
    "header",
    [
        "Keep the shared translator free of transport imports",  # untyped (PR #69)
        "feature(ci): gate commit messages",  # type outside the list
        "wip: gate commit messages",
        "feat(ci) gate commit messages",  # missing colon
        "feat(ci): Gate commit messages",  # uppercase summary
        "feat(CI): gate commit messages",  # scope not kebab-case
        "feat:gate commit messages",  # no space after the colon
    ],
)
def test_header_rejects_non_conventional_headers(header: str) -> None:
    errors = check_commits.check_message(_msg(header, _TRAILER))
    assert any("header" in e for e in errors), errors


def test_header_accepts_scope_less_and_breaking_marker() -> None:
    assert check_commits.check_message(_msg("refactor!: drop the legacy route", _TRAILER)) == []
    assert check_commits.check_message(_msg("docs: explain the gate", _TRAILER)) == []


# --- Assisted-by trailer ---------------------------------------------------------


def test_assisted_by_trailer_present_passes() -> None:
    message = _msg("ci: gate commit messages", _TRAILER, body="Why the gate exists.")
    assert check_commits.check_message(message) == []


def test_assisted_by_missing_fails() -> None:
    errors = check_commits.check_message(_msg("ci: gate commit messages"))
    assert any("Assisted-by" in e for e in errors), errors


@pytest.mark.parametrize(
    "near_miss",
    ["Assisted-by: Claude", "Assisted-by: claude code", "Assisted-By Claude Code"],
)
def test_assisted_by_near_miss_fails(near_miss: str) -> None:
    errors = check_commits.check_message(_msg("ci: gate commit messages", near_miss))
    assert any("Assisted-by" in e for e in errors), errors


def test_assisted_by_outside_the_trailer_block_fails() -> None:
    # The line sits in the body with prose after it, so it is not a trailer.
    message = "ci: gate commit messages\n\nAssisted-by: Claude Code\n\nMore prose after it.\n"
    errors = check_commits.check_message(message)
    assert any("Assisted-by" in e for e in errors), errors


def test_assisted_by_as_the_only_line_is_not_a_trailer() -> None:
    errors = check_commits.check_message("Assisted-by: Claude Code\n")
    assert errors, "a header-only message carries no trailer block"


# --- agent attribution trailers --------------------------------------------------


@pytest.mark.parametrize("agent", _AGENTS)
def test_agent_trailer_co_authored_by_any_agent_fails(agent: str) -> None:
    for spelling in (agent, agent.upper(), agent.capitalize()):
        coauthor = f"Co-Authored-By: {spelling} <noreply@example.com>"
        errors = check_commits.check_message(_msg("ci: gate", _TRAILER, coauthor))
        assert any("Co-authored-by" in e for e in errors), (spelling, errors)


def test_agent_trailer_lowercase_key_is_still_caught() -> None:
    coauthor = "co-authored-by: Claude <noreply@anthropic.com>"
    errors = check_commits.check_message(_msg("ci: gate", _TRAILER, coauthor))
    assert any("Co-authored-by" in e for e in errors), errors


def test_agent_trailer_made_with_fails() -> None:
    errors = check_commits.check_message(_msg("ci: gate", _TRAILER, "Made-with: Cursor"))
    assert any("Made-with" in e for e in errors), errors


def test_agent_trailer_human_co_author_passes() -> None:
    coauthor = "Co-authored-by: Maria Silva <maria@example.com>"
    assert check_commits.check_message(_msg("ci: gate", _TRAILER, coauthor)) == []


# --- range walk over a real repository -------------------------------------------


def _git(repo: Path, *args: str, author: str | None = None) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Owner",
        "GIT_AUTHOR_EMAIL": "owner@example.com",
        "GIT_COMMITTER_NAME": "Owner",
        "GIT_COMMITTER_EMAIL": "owner@example.com",
    }
    if author is not None:
        env["GIT_AUTHOR_NAME"] = author
    out = subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def _commit(repo: Path, message: str, *, author: str | None = None) -> str:
    _git(repo, "commit", "--allow-empty", "-q", "-m", message, author=author)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, "chore: root commit before the range")
    return tmp_path


def _run(repo: Path, rng: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), rng], cwd=repo, capture_output=True, text=True
    )


def test_range_all_good_exits_zero(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, _msg("feat(ci): one", _TRAILER))
    _commit(repo, _msg("fix(ci): two", _TRAILER))
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 0, result.stdout + result.stderr


def test_range_names_every_failing_sha_before_exiting(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    good = _commit(repo, _msg("feat(ci): good", _TRAILER))
    no_trailer = _commit(repo, _msg("feat(ci): no trailer"))
    untyped = _commit(repo, _msg("Untyped review fix", _TRAILER))
    result = _run(repo, f"{base}..HEAD")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert no_trailer[:12] in output
    assert untyped[:12] in output
    assert good[:12] not in output


def test_range_skips_bot_authored_commits(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "Bump actions/checkout from 5 to 6", author="dependabot[bot]")
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 0, result.stdout + result.stderr


def test_range_skips_merge_commits(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-q", "-c", "side")
    _commit(repo, _msg("feat(ci): on the side branch", _TRAILER))
    _git(repo, "switch", "-q", "main")
    _commit(repo, _msg("docs(ci): on main meanwhile", _TRAILER))
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "side")
    # The merge commit's default message ("Merge branch 'side'") is not
    # Conventional; it must not be checked at all.
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 0, result.stdout + result.stderr


def test_range_checks_the_non_bot_commit_next_to_a_bot_one(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "Bump something", author="dependabot[bot]")
    bad = _commit(repo, _msg("feat(ci): forgot the trailer"))
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 1
    assert bad[:12] in result.stdout + result.stderr
