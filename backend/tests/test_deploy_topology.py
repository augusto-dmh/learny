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


_LOOPBACK_IPS = {"127.0.0.1", "::1", "localhost"}


def _port_bindings(service: dict) -> list[tuple[str | None, str]]:
    """(host_ip, host_port) for each published port of a compose service.

    ``host_ip`` is ``None`` when the short syntax omits it — which binds the port
    on *every* host interface (the public case the exposure contract guards).
    """
    bindings: list[tuple[str | None, str]] = []
    for entry in service.get("ports") or []:
        spec = str(entry).split("/", 1)[0]  # drop an optional "/proto" suffix
        parts = spec.split(":")
        if len(parts) == 3:  # "ip:host:container"
            bindings.append((parts[0], parts[1]))
        elif len(parts) == 2:  # "host:container" — no IP, so all interfaces
            bindings.append((None, parts[0]))
    return bindings


def _publishes_non_loopback(service: dict) -> bool:
    """True if the service publishes any port on a non-loopback host interface."""
    return any(ip not in _LOOPBACK_IPS for ip, _port in _port_bindings(service))


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


# --- prod overlay adds a single public Caddy edge (DEP-06, DEP-07) ---------------


def _prod_volumes() -> dict:
    merged: dict = {}
    for path in (_BASE, _PROD):
        merged = _deep_merge(merged, _load(path).get("volumes") or {})
    return merged


def test_prod_publishes_non_loopback_ports_only_on_caddy(prod: dict) -> None:
    # OPS-14: adding the loopback-only monitoring UI must not widen the public
    # surface. Caddy stays the ONLY service publishing a non-loopback host port;
    # every other service (monitoring included, backup with none) publishes nothing
    # reachable off-host.
    for name, svc in prod.items():
        if name == "caddy":
            assert _publishes_non_loopback(svc), "caddy must publish public host ports in prod"
        else:
            assert not _publishes_non_loopback(svc), (
                f"{name} must not publish non-loopback host ports in prod"
            )


def test_caddy_publishes_only_80_443_and_quic(prod: dict) -> None:
    assert set(prod["caddy"]["ports"]) == {"80:80", "443:443", "443:443/udp"}


def test_caddy_uses_a_pinned_alpine_image(prod: dict) -> None:
    image = prod["caddy"]["image"]
    assert image.startswith("caddy:")
    assert not image.endswith(":latest"), "caddy image must be pinned"


def test_caddy_restarts_unless_stopped(prod: dict) -> None:
    assert prod["caddy"].get("restart") == "unless-stopped"


def test_caddy_persists_cert_and_config_volumes(prod: dict) -> None:
    volumes = prod["caddy"]["volumes"]
    assert "./deploy/Caddyfile:/etc/caddy/Caddyfile:ro" in volumes
    assert "caddy_data:/data" in volumes
    assert "caddy_config:/config" in volumes


def test_prod_declares_the_caddy_named_volumes() -> None:
    volumes = _prod_volumes()
    assert "caddy_data" in volumes
    assert "caddy_config" in volumes


def test_caddy_requires_the_domain_env(prod: dict) -> None:
    domain = prod["caddy"]["environment"]["LEARNY_DOMAIN"]
    # `:?` makes an unset LEARNY_DOMAIN abort the run instead of silent-defaulting.
    assert domain == "${LEARNY_DOMAIN:?LEARNY_DOMAIN must be set}"


def test_caddy_is_absent_from_base_and_override(base: dict, override: dict) -> None:
    assert "caddy" not in base
    assert "caddy" not in override


# --- the Caddyfile reverse-proxies only web, never api (ADR-0017/AD-093) ---------


def test_caddyfile_proxies_only_the_web_upstream() -> None:
    text = _CADDYFILE.read_text()
    assert "reverse_proxy web:3000" in text
    assert "api:8000" not in text
    assert "reverse_proxy api" not in text


def test_caddyfile_site_address_pins_the_tls_domain() -> None:
    # The `{$LEARNY_DOMAIN}` site address is what makes Caddy request an automatic
    # Let's Encrypt certificate for the operator's domain. A regression to a plain
    # `:80` block would silently drop TLS while every other assertion still passed.
    text = _CADDYFILE.read_text()
    assert "{$LEARNY_DOMAIN}" in text


# --- prod overlay adds a loopback-only netdata monitor (OPS-13, OPS-14) ----------


def test_monitoring_publishes_only_the_loopback_ui_port(prod: dict) -> None:
    # The UI is reached over an SSH tunnel, never off-host (docs/ops/monitoring.md).
    assert prod["monitoring"]["ports"] == ["127.0.0.1:19999:19999"]
    assert not _publishes_non_loopback(prod["monitoring"])


def test_monitoring_pins_a_non_floating_netdata_image(prod: dict) -> None:
    image = prod["monitoring"]["image"]
    assert image.startswith("netdata/netdata:")
    assert not image.endswith(":latest"), "netdata image must be pinned"
    assert image != "netdata/netdata:", "netdata image must carry an explicit tag"


def test_monitoring_restarts_unless_stopped(prod: dict) -> None:
    assert prod["monitoring"].get("restart") == "unless-stopped"


def test_monitoring_disables_anonymous_telemetry(prod: dict) -> None:
    # The host-privileged agent must not phone home; disable netdata's anonymous
    # statistics via its documented Docker opt-out env (ADR-0024).
    assert prod["monitoring"]["environment"]["DISABLE_TELEMETRY"] == "1"


def test_monitoring_caps_its_memory(prod: dict) -> None:
    # A runaway agent must not compete with worker-pdf for host RAM (OPS-13).
    assert prod["monitoring"].get("mem_limit") == "512m"


def test_monitoring_mounts_the_docker_socket_read_only(prod: dict) -> None:
    # Per-container metrics come from the docker socket; read-only, never rw.
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in prod["monitoring"]["volumes"]


def test_monitoring_mounts_the_host_metric_sources_read_only(prod: dict) -> None:
    volumes = prod["monitoring"]["volumes"]
    for mount in (
        "/proc:/host/proc:ro",
        "/sys:/host/sys:ro",
        "/etc/os-release:/host/etc/os-release:ro",
    ):
        assert mount in volumes, f"monitoring must mount {mount}"


def test_monitoring_declares_the_netdata_named_volumes() -> None:
    volumes = _prod_volumes()
    for vol in ("netdata_config", "netdata_lib", "netdata_cache"):
        assert vol in volumes, f"{vol} must be declared for netdata persistence"


def test_monitoring_is_absent_from_base_and_override(base: dict, override: dict) -> None:
    assert "monitoring" not in base
    assert "monitoring" not in override
