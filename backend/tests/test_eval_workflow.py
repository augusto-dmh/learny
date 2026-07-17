"""C gate — eval.yml nightly-results publish shape (unit, DEP-14, DEP-15).

Loads `.github/workflows/eval.yml` as YAML (and as raw text where GitHub
expressions and shell fragments must be matched verbatim) and asserts the
publish contract: the `generation-eval` job gains job-scoped `contents: write`,
a step commits the produced `evals/results/*.jsonl` to the dedicated
`eval-results` branch, gated on both the provider-secret presence flag and a
no-results green skip, under a dated `results/<utc-date>-<run_id>/` layout, and
never force-pushes — while the existing artifact upload stays intact.

"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL = _REPO_ROOT / ".github" / "workflows" / "eval.yml"

_RAW = _EVAL.read_text()
_WORKFLOW = yaml.safe_load(_RAW)


def _job(name: str) -> dict:
    return _WORKFLOW["jobs"][name]


def _step_by_name(job: str, name: str) -> dict:
    for step in _job(job)["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in job {job!r}")


_PUBLISH = "Publish eval results to the eval-results branch"


# --- DEP-14: the job holds job-scoped contents: write for the commit -------------


def test_generation_eval_job_has_contents_write_permission() -> None:
    assert _job("generation-eval")["permissions"]["contents"] == "write"


def test_workflow_default_permission_stays_read() -> None:
    # The elevated scope is job-level only; the workflow default remains read.
    assert _WORKFLOW["permissions"]["contents"] == "read"


# --- DEP-14: a publish step commits to the dedicated eval-results branch ----------


def test_publish_step_pushes_to_the_eval_results_branch() -> None:
    run = _step_by_name("generation-eval", _PUBLISH)["run"]
    assert "git push origin eval-results" in run
    # The commit lands on eval-results, never on the checked-out main commit.
    assert "git switch --orphan eval-results" in run
    assert "eval:" in run  # the bot commit message subject


def test_publish_step_runs_from_the_repo_root() -> None:
    # The judge writes repo-root evals/results/, so publish must not use backend/.
    assert _step_by_name("generation-eval", _PUBLISH)["working-directory"] == "."


# --- DEP-14: results land under a dated results/<run_id> layout -------------------


def test_publish_step_writes_under_a_dated_run_id_path() -> None:
    run = _step_by_name("generation-eval", _PUBLISH)["run"]
    assert 'DEST="results/$(date -u +%Y-%m-%d)-${{ github.run_id }}"' in run
    assert "${{ github.run_id }}" in run


# --- DEP-15: gated on the provider-secret flag AND a no-results green skip --------


def test_publish_step_is_gated_on_the_secret_present_flag() -> None:
    step = _step_by_name("generation-eval", _PUBLISH)
    assert step["if"] == "steps.secret.outputs.present == 'true'"


def test_publish_step_green_skips_when_no_results_exist() -> None:
    run = _step_by_name("generation-eval", _PUBLISH)["run"]
    assert "ls evals/results/*.jsonl" in run
    assert "::notice::No eval results to publish." in run
    assert "exit 0" in run


# --- Edge case: never force-push over eval-results history ------------------------


def test_publish_step_never_force_pushes() -> None:
    run = _step_by_name("generation-eval", _PUBLISH)["run"]
    assert "push --force" not in run
    assert "push -f" not in run
    assert "--force-with-lease" not in run
    assert "--force" not in run
    # The retry recovers via rebase, not by rewriting history.
    assert "git pull --rebase origin eval-results" in run


# --- DEP-14: the existing artifact upload is retained unchanged -------------------


def test_artifact_upload_step_is_retained() -> None:
    upload = _step_by_name("generation-eval", "Upload eval results")
    assert "actions/upload-artifact@v4" in str(upload["uses"])
    assert upload["with"]["name"] == "eval-results"
    assert upload["with"]["path"] == "evals/results/*.jsonl"
    assert upload["with"]["if-no-files-found"] == "warn"
    assert upload["if"] == "steps.secret.outputs.present == 'true'"
