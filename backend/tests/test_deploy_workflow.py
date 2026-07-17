"""B/C gate — deploy.yml workflow shape (unit, DEP-01..04, DEP-10..13).

Loads `.github/workflows/deploy.yml` as YAML (and as raw text where GitHub
expressions must be matched verbatim) and asserts the publish + deploy contract:
CI-gated triggers, non-cancelling concurrency, the three-image GHCR build matrix
with sha+latest tags and job-scoped GITHUB_TOKEN, then the secret-gated SSH deploy
that scp's exactly the compose triad and drives `pull` + `up -d --no-build --wait`
with the same resolved sha. Pure text/YAML — no Docker or network required.

PyYAML parses the workflow's ``on:`` key as the boolean ``True`` (YAML 1.1
treats ``on`` as a boolean), so trigger assertions read it via ``_on`` below.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEPLOY = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"

_RAW = _DEPLOY.read_text()
_WORKFLOW = yaml.safe_load(_RAW)

# The resolved build sha — used for both the image tags and the deploy tag.
_SHA_EXPR = "${{ github.event.workflow_run.head_sha || github.sha }}"


def _on(data: dict) -> dict:
    """The `on:` trigger block (PyYAML parses the key as boolean ``True``)."""
    if True in data:
        return data[True]
    return data["on"]


def _job(name: str) -> dict:
    return _WORKFLOW["jobs"][name]


def _step(job: str, uses_substr: str) -> dict:
    for step in _job(job)["steps"]:
        if uses_substr in str(step.get("uses", "")):
            return step
    raise AssertionError(f"no step using {uses_substr!r} in job {job!r}")


def _secret_refs(fragment: object) -> set[str]:
    """Every ``secrets.<NAME>`` referenced within a YAML fragment."""
    return set(re.findall(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)", yaml.dump(fragment)))


# --- DEP-02: triggers are exactly CI-completed workflow_run + dispatch -----------


def test_triggers_are_exactly_workflow_run_ci_and_dispatch() -> None:
    on = _on(_WORKFLOW)
    assert set(on.keys()) == {"workflow_run", "workflow_dispatch"}
    assert on["workflow_run"]["workflows"] == ["CI"]
    assert on["workflow_run"]["types"] == ["completed"]


def test_no_push_or_pull_request_triggers() -> None:
    on = _on(_WORKFLOW)
    assert "push" not in on
    assert "pull_request" not in on


def test_workflow_couples_to_the_ci_workflow_name() -> None:
    # Renaming ci.yml's `name: CI` must break this coupling loudly.
    assert _on(_WORKFLOW)["workflow_run"]["workflows"] == ["CI"]


# --- DEP-02: build/deploy run only on green CI @ main ----------------------------


def test_build_guard_requires_green_ci_on_main() -> None:
    guard = _job("build")["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in guard
    assert "github.event.workflow_run.head_branch == 'main'" in guard
    # workflow_dispatch path is pinned to the main ref.
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in guard


# --- DEP-04: non-cancelling concurrency ------------------------------------------


def test_concurrency_group_is_deploy_and_does_not_cancel() -> None:
    concurrency = _WORKFLOW["concurrency"]
    assert concurrency["group"] == "deploy"
    assert concurrency["cancel-in-progress"] is False


# --- DEP-03: GHCR auth uses the job-scoped GITHUB_TOKEN, no PAT ------------------


def test_build_job_has_packages_write_permission() -> None:
    assert _job("build")["permissions"]["packages"] == "write"
    assert _job("build")["permissions"]["contents"] == "read"


def test_build_job_uses_only_the_github_token_secret() -> None:
    assert _secret_refs(_job("build")) == {"GITHUB_TOKEN"}
    login = _step("build", "docker/login-action")
    assert login["with"]["password"] == "${{ secrets.GITHUB_TOKEN }}"
    assert login["with"]["registry"] == "ghcr.io"


# --- DEP-01: three-image build matrix with correct context + target -------------


def test_build_matrix_covers_the_three_images() -> None:
    include = _job("build")["strategy"]["matrix"]["include"]
    by_name = {entry["name"]: (entry["context"], entry["target"]) for entry in include}
    assert by_name == {
        "learny-backend": ("./backend", "runtime"),
        "learny-pdf-worker": ("./backend", "pdf-worker"),
        "learny-web": ("./frontend", "prod"),
    }


# --- DEP-01: each image is tagged both :latest and the commit sha ---------------


def test_build_push_tags_both_latest_and_the_sha() -> None:
    build_push = _step("build", "docker/build-push-action")
    tags = build_push["with"]["tags"]
    assert "ghcr.io/augusto-dmh/${{ matrix.name }}:latest" in tags
    assert f"ghcr.io/augusto-dmh/${{{{ matrix.name }}}}:{_SHA_EXPR}" in tags
    assert build_push["with"]["push"] is True
    assert build_push["with"]["context"] == "${{ matrix.context }}"
    assert build_push["with"]["target"] == "${{ matrix.target }}"


def test_build_checkout_uses_the_resolved_sha() -> None:
    checkout = _step("build", "actions/checkout")
    assert checkout["with"]["ref"] == _SHA_EXPR


def test_docker_action_versions_are_pinned_to_real_majors() -> None:
    assert "docker/setup-buildx-action@v3" in _RAW
    assert "docker/login-action@v3" in _RAW
    assert "docker/build-push-action@v6" in _RAW
    assert "actions/checkout@v4" in _RAW
