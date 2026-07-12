"""B1 gate — production compose overlay hardening (unit, PROD-01..05).

Loads the compose files as YAML and asserts the hardening the prod invocation
(`-f docker-compose.yml -f docker-compose.prod.yml`) produces, plus that the
auto-loaded local override restores db/redis/minio host ports (keeps local
aligned, ADR-0008 §3 / AD-042). Pure YAML — no Docker required, deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE = _REPO_ROOT / "docker-compose.yml"
_OVERRIDE = _REPO_ROOT / "docker-compose.override.yml"
_PROD = _REPO_ROOT / "docker-compose.prod.yml"

_INFRA = ("db", "redis", "minio")
_ALL_SERVICES = ("db", "redis", "minio", "api", "worker", "web")


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


@pytest.fixture
def prod() -> dict:
    return _services(_BASE, _PROD)


def test_infra_services_publish_no_host_ports_in_prod(prod: dict) -> None:
    for svc in _INFRA:
        assert not prod[svc].get("ports"), f"{svc} must not publish host ports in prod"


def test_every_service_has_a_restart_policy(prod: dict) -> None:
    for svc in _ALL_SERVICES:
        assert prod[svc].get("restart") in {"unless-stopped", "always"}, svc


def test_no_service_uses_a_floating_latest_image(prod: dict) -> None:
    for svc in _ALL_SERVICES:
        image = prod[svc].get("image")
        if image is not None:
            assert not image.endswith(":latest"), f"{svc} image must be pinned"
            assert ":" in image, f"{svc} image must carry an explicit tag"
    # db/redis/minio run from an image (not a build), so each must be pinned.
    for svc in _INFRA:
        assert prod[svc].get("image"), f"{svc} must declare a pinned image"


def test_api_runs_with_production_hardened_env(prod: dict) -> None:
    env = prod["api"]["environment"]
    assert env["LEARNY_ENVIRONMENT"] == "production"
    assert env["LEARNY_SESSION_COOKIE_SECURE"] == "true"
    assert env["LEARNY_LOG_FORMAT"] == "json"


def test_secrets_come_from_env_file_not_inline(prod: dict) -> None:
    # Credentials must arrive via env_file, never as inline environment literals.
    for svc in ("api", "worker", "db", "minio"):
        assert prod[svc].get("env_file"), f"{svc} must source secrets via env_file"

    for svc in ("api", "worker"):
        env = prod[svc].get("environment", {})
        assert "LEARNY_DATABASE_URL" not in env
        assert "LEARNY_STORAGE_SECRET_KEY" not in env
        assert "LEARNY_STORAGE_ACCESS_KEY" not in env
    assert "POSTGRES_PASSWORD" not in prod["db"].get("environment", {})
    assert "MINIO_ROOT_PASSWORD" not in prod["minio"].get("environment", {})


def test_web_prod_runs_built_app_not_dev_server(prod: dict) -> None:
    command = prod["web"].get("command")
    assert command == ["node", "server.js"]
    assert prod["web"]["build"].get("target") == "prod"


def test_local_override_restores_infra_ports() -> None:
    local = _services(_BASE, _OVERRIDE)
    for svc in _INFRA:
        assert local[svc].get("ports"), f"{svc} must publish host ports for local dev"
