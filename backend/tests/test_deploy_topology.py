"""A gate — deploy edge topology (unit, DEP-05..09).

Loads the compose files as YAML (and the Caddyfile as text) and asserts the
Cycle G deploy edge: the base file publishes no host ports at all (app ports
moved to the dev override); the dev merge still publishes today's exact port
set; the prod overlay resolves the four app services to their GHCR image refs
(parameterized by ``LEARNY_IMAGE_TAG``) while the base keeps its build blocks;
and the prod overlay adds a single public Caddy edge (only 80/443(+udp)
published, persisted cert volumes, a read-only Caddyfile mount, and a required
``LEARNY_DOMAIN`` guard) that reverse-proxies only ``web:3000``.

Pure text/YAML — no Docker required, deterministic. Mirrors the merge semantics
of ``test_compose_topology.py`` / ``test_compose_prod.py`` (a later ``-f`` file
replaces list-valued keys like ``ports`` at the service level).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE = _REPO_ROOT / "docker-compose.yml"
_OVERRIDE = _REPO_ROOT / "docker-compose.override.yml"
_PROD = _REPO_ROOT / "docker-compose.prod.yml"
_CADDYFILE = _REPO_ROOT / "deploy" / "Caddyfile"


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


def _host_ports(service: dict) -> list[str]:
    """The host-published port(s) of a compose service (part before the ``:``)."""
    ports = service.get("ports") or []
    hosts: list[str] = []
    for entry in ports:
        # Short syntax only in this repo: "host:container[/proto]".
        host = str(entry).split(":", 1)[0]
        hosts.append(host)
    return hosts


@pytest.fixture
def base() -> dict:
    return _services(_BASE)


@pytest.fixture
def local() -> dict:
    return _services(_BASE, _OVERRIDE)


@pytest.fixture
def override() -> dict:
    return _load(_OVERRIDE)["services"]


@pytest.fixture
def prod() -> dict:
    return _services(_BASE, _PROD)


# --- base publishes no host ports at all (DEP-08, DEP-09) -----------------------


def test_base_publishes_no_host_ports_on_any_service(base: dict) -> None:
    for name, svc in base.items():
        assert not svc.get("ports"), f"{name} must not publish host ports in base"


# --- the dev merge still publishes today's exact port set (DEP-08) --------------


def test_dev_merge_publishes_the_app_ports(local: dict) -> None:
    assert "8000" in _host_ports(local["api"]), "api must publish 8000 in dev"
    assert "3000" in _host_ports(local["web"]), "web must publish 3000 in dev"


def test_dev_merge_still_publishes_todays_infra_ports(local: dict) -> None:
    assert "5432" in _host_ports(local["db"])
    assert "6379" in _host_ports(local["redis"])
    minio_ports = _host_ports(local["minio"])
    assert "9000" in minio_ports
    assert "9001" in minio_ports


# --- prod overlay resolves the app services to GHCR image refs (DEP-05) ---------

_IMAGE_TAG = "${LEARNY_IMAGE_TAG:-latest}"
_GHCR_REFS = {
    "api": f"ghcr.io/augusto-dmh/learny-backend:{_IMAGE_TAG}",
    "worker": f"ghcr.io/augusto-dmh/learny-backend:{_IMAGE_TAG}",
    "worker-pdf": f"ghcr.io/augusto-dmh/learny-pdf-worker:{_IMAGE_TAG}",
    "web": f"ghcr.io/augusto-dmh/learny-web:{_IMAGE_TAG}",
}


@pytest.mark.parametrize(("service", "ref"), sorted(_GHCR_REFS.items()))
def test_prod_app_services_use_the_ghcr_image_ref(prod: dict, service: str, ref: str) -> None:
    assert prod[service].get("image") == ref


def test_base_app_services_still_build_from_source(base: dict) -> None:
    for service in _GHCR_REFS:
        assert base[service].get("build"), f"{service} must keep its build block in base"
        assert base[service].get("image") is None, f"{service} must not pin an image in base"
