"""E gate — PDF worker isolation topology (unit, ING-18/19).

Loads the compose files as YAML (and the Dockerfile / CI workflow as text) and
asserts the isolation seam that keeps a heavy, pathological PDF off the main
worker: worker-pdf drains only the ingest-pdf queue with concurrency 1, a memory
cap, and one task per child; the default worker drains only the default queue and
never ingest-pdf; the prod overlay hardens worker-pdf like worker; the pdf-worker
image lives behind its own build target; and CI never installs the pdf extra.
Pure text/YAML — no Docker required, deterministic.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE = _REPO_ROOT / "docker-compose.yml"
_OVERRIDE = _REPO_ROOT / "docker-compose.override.yml"
_PROD = _REPO_ROOT / "docker-compose.prod.yml"
_DOCKERFILE = _REPO_ROOT / "backend" / "Dockerfile"
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_INGEST_PDF_QUEUE = "ingest-pdf"
_DEFAULT_QUEUE = "celery"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _deep_merge(a: dict, b: dict) -> dict:
    """Merge ``b`` over ``a`` the way an added compose `-f` file overrides keys."""
    out = dict(a)
    for key, b_val in b.items():
        a_val = out.get(key)
        if isinstance(a_val, dict) and isinstance(b_val, dict):
            out[key] = _deep_merge(a_val, b_val)
        else:
            out[key] = b_val
    return out


def _services(*paths: Path) -> dict:
    merged: dict = {}
    for path in paths:
        merged = _deep_merge(merged, _load(path)["services"])
    return merged


def _tokens(command: object) -> list[str]:
    """A compose ``command`` (scalar or list form) as a flat token list."""
    if isinstance(command, list):
        return [str(token) for token in command]
    return shlex.split(str(command))


def _flag_value(tokens: list[str], flag: str) -> str | None:
    """The token following ``flag`` (e.g. the value of ``--queues``), or ``None``."""
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


@pytest.fixture
def base() -> dict:
    return _services(_BASE)


@pytest.fixture
def prod() -> dict:
    return _services(_BASE, _PROD)


@pytest.fixture
def local() -> dict:
    return _services(_BASE, _OVERRIDE)


# --- worker-pdf consumes only ingest-pdf, bounded (ING-18) ----------------------


def test_worker_pdf_consumes_only_the_ingest_pdf_queue(base: dict) -> None:
    tokens = _tokens(base["worker-pdf"]["command"])
    assert _flag_value(tokens, "--queues") == _INGEST_PDF_QUEUE


def test_worker_pdf_runs_single_task_per_child_at_concurrency_one(base: dict) -> None:
    tokens = _tokens(base["worker-pdf"]["command"])
    assert _flag_value(tokens, "--concurrency") == "1"
    assert _flag_value(tokens, "--max-tasks-per-child") == "1"


def test_worker_pdf_has_a_memory_limit(base: dict) -> None:
    assert base["worker-pdf"].get("mem_limit") == "4g"


def test_worker_pdf_builds_from_the_pdf_worker_image_target(base: dict) -> None:
    assert base["worker-pdf"]["build"].get("target") == "pdf-worker"


# --- the default worker never drains ingest-pdf (ING-18) ------------------------


def test_default_worker_consumes_only_the_default_queue(base: dict) -> None:
    tokens = _tokens(base["worker"]["command"])
    assert _flag_value(tokens, "--queues") == _DEFAULT_QUEUE
    assert _INGEST_PDF_QUEUE not in tokens


# --- worker-pdf is present in the local and prod compositions (ING-18) ----------


def test_worker_pdf_receives_local_dev_credentials(local: dict) -> None:
    env = local["worker-pdf"]["environment"]
    assert env["LEARNY_DATABASE_URL"] == "postgresql+psycopg://learny:learny@db:5432/learny"
    assert env["LEARNY_STORAGE_ACCESS_KEY"] == "learny"
    assert env["LEARNY_STORAGE_SECRET_KEY"] == "learny-dev-secret"


def test_worker_pdf_is_prod_hardened_like_worker(prod: dict) -> None:
    svc = prod["worker-pdf"]
    assert svc.get("restart") == "unless-stopped"
    assert svc["environment"]["LEARNY_ENVIRONMENT"] == "production"
    assert svc["environment"]["LEARNY_LOG_FORMAT"] == "json"
    env_file = svc.get("env_file")
    assert env_file, "worker-pdf must source secrets via env_file in prod"
    entry = env_file[0]
    assert entry.get("path") == "./secrets/worker.env"
    assert entry.get("required") is True


# --- the pdf-worker image target exists and bakes models (ING-19) ---------------


def test_dockerfile_defines_the_pdf_worker_target() -> None:
    text = _DOCKERFILE.read_text()
    assert "AS pdf-worker" in text


def test_pdf_worker_target_installs_the_pdf_extra_and_bakes_models() -> None:
    text = _DOCKERFILE.read_text()
    assert "--extra pdf" in text
    assert "download_models" in text


# --- CI never installs the pdf extra (AD-089 / CI parity) -----------------------


def test_ci_does_not_install_all_extras() -> None:
    text = _CI.read_text()
    assert "--all-extras" not in text
    assert "--extra dev" in text
