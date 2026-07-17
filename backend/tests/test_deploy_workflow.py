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
    # A fork whose branch is named `main` passes the head_branch check, so the
    # guard must also require the triggering run to belong to this repository.
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository" in guard
    )


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


# --- DEP-10: the deploy job runs only after the images are published -------------


def test_deploy_needs_the_build_job() -> None:
    needs = _job("deploy")["needs"]
    needs = [needs] if isinstance(needs, str) else needs
    assert "build" in needs


def test_deploy_shares_the_build_guard() -> None:
    guard = _job("deploy")["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in guard
    assert "github.event.workflow_run.head_branch == 'main'" in guard
    # The deploy job's manual path must be main-only too, and — like the build job —
    # only for a run that originated from this repository, never a fork.
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in guard
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository" in guard
    )


# --- DEP-11: absent VPS secrets → green skip with a notice ----------------------


def _gate_step() -> dict:
    return _step_by_id("deploy", "secrets")


def _step_by_id(job: str, step_id: str) -> dict:
    for step in _job(job)["steps"]:
        if step.get("id") == step_id:
            return step
    raise AssertionError(f"no step with id {step_id!r} in job {job!r}")


def test_secret_gate_maps_all_three_vps_secrets() -> None:
    env = _gate_step()["env"]
    assert env["VPS_HOST"] == "${{ secrets.VPS_HOST }}"
    assert env["VPS_USER"] == "${{ secrets.VPS_USER }}"
    assert env["VPS_SSH_KEY"] == "${{ secrets.VPS_SSH_KEY }}"


def test_secret_gate_emits_notice_and_present_flag_when_missing() -> None:
    run = _gate_step()["run"]
    assert "::notice::" in run
    assert "present=false" in run
    assert "present=true" in run
    # All three must be present for the deploy to proceed.
    assert '[ -z "$VPS_HOST" ]' in run
    assert '[ -z "$VPS_USER" ]' in run
    assert '[ -z "$VPS_SSH_KEY" ]' in run


def test_every_deploy_action_step_is_gated_on_the_present_flag() -> None:
    gate = "steps.secrets.outputs.present == 'true'"
    for step in _job("deploy")["steps"]:
        if step.get("id") == "secrets":
            continue  # the gate step itself always runs
        assert step.get("if") == gate, f"step {step!r} is not gated on the present flag"


# --- DEP-12: scp transfers exactly the compose triad, no secret material --------


def test_scp_transfers_exactly_the_three_compose_files() -> None:
    copy = _step_by_id_or_name("deploy", "Copy the compose files to the VPS")
    run = copy["run"]
    assert "docker-compose.yml" in run
    assert "docker-compose.prod.yml" in run
    assert "deploy/Caddyfile" in run
    assert "/opt/learny/deploy/Caddyfile" in run


def test_deploy_job_transfers_no_secret_material() -> None:
    body = yaml.dump(_job("deploy"))
    assert "secrets/" not in body  # no secrets/*.env transfer
    assert ".env" not in body  # no dotenv transfer


def _step_by_id_or_name(job: str, name: str) -> dict:
    for step in _job(job)["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in job {job!r}")


# --- DEP-10/DEP-13: remote command shape + sha injection ------------------------


def test_remote_command_pulls_and_waits_with_the_image_tag() -> None:
    deploy = _step_by_id_or_name("deploy", "Pull images and restart the stack")
    run = deploy["run"]
    assert "docker compose -f docker-compose.yml -f docker-compose.prod.yml pull" in run
    assert "up -d --no-build --wait" in run
    assert "LEARNY_IMAGE_TAG=$DEPLOY_SHA" in run
    # The injected tag resolves to the same sha the images were built and tagged with.
    assert deploy["env"]["DEPLOY_SHA"] == _SHA_EXPR


def test_deploy_checkout_uses_the_same_resolved_sha() -> None:
    checkout = _step("deploy", "actions/checkout")
    assert checkout["with"]["ref"] == _SHA_EXPR
