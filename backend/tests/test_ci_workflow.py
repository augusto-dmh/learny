"""CI wiring for the harness sensors (``.github/workflows/ci.yml`` and the Makefile).

The sensors only protect anything while CI runs them: the backend suite under
``LEARNY_REQUIRE_DB=1`` so a missing database fails the job instead of skipping
the database suite, and a ``commits`` job that reads every pull-request commit.
``make lint`` runs the same commit checker locally so the agent sees the failure
before pushing.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI = yaml.safe_load((_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())
_MAKEFILE = (_REPO_ROOT / "Makefile").read_text()


def _steps(job: str) -> list[dict]:
    return _CI["jobs"][job]["steps"]


def test_backend_test_runs_pytest_with_require_db() -> None:
    pytest_steps = [s for s in _steps("backend-test") if "pytest" in str(s.get("run", ""))]
    assert pytest_steps, "backend-test has no pytest step"
    for step in pytest_steps:
        assert step.get("env", {}).get("LEARNY_REQUIRE_DB") == "1", step


def test_commits_job_runs_only_on_pull_requests() -> None:
    job = _CI["jobs"]["commits"]
    assert job["if"] == "github.event_name == 'pull_request'"


def test_commits_job_checks_out_full_history() -> None:
    checkout = next(
        s for s in _steps("commits") if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0


def test_commits_job_checks_the_pull_request_range() -> None:
    runs = " ".join(str(s.get("run", "")) for s in _steps("commits"))
    assert "backend/scripts/check_commits.py" in runs
    assert (
        "${{ github.event.pull_request.base.sha }}..${{ github.event.pull_request.head.sha }}"
        in runs
    )


def test_nothing_softens_the_commits_gate() -> None:
    # A gate that cannot fail is the green-over-unread-commits outcome again.
    job = _CI["jobs"]["commits"]
    assert "continue-on-error" not in job
    for step in job["steps"]:
        assert "continue-on-error" not in step, step
        assert "|| true" not in str(step.get("run", "")), step


def _recipe(target: str) -> tuple[list[str], str]:
    match = re.search(rf"^{re.escape(target)}:([^\n]*)\n((?:\t[^\n]*\n?)*)", _MAKEFILE, re.M)
    assert match is not None, f"no Makefile target {target!r}"
    return match.group(1).split("#")[0].split(), match.group(2)


def test_make_lint_checks_commits_over_the_branch() -> None:
    prerequisites, _ = _recipe("lint")
    recipes = [_recipe(p)[1] for p in prerequisites]
    commit_recipes = [r for r in recipes if "check_commits.py" in r]
    assert commit_recipes, f"make lint runs no commit check: {prerequisites}"
    assert "origin/main..HEAD" in commit_recipes[0]
