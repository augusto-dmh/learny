"""E gate — service isolation + WAL-archiving topology (unit, ING-18/19, PITR-01/02).

Loads the compose files as YAML (and the Dockerfiles / CI workflow as text) and
asserts two topology seams.

* **PDF worker isolation** — what keeps a heavy, pathological PDF off the main
  worker: worker-pdf drains only the ingest-pdf queue with concurrency 1, a memory
  cap, and one task per child; the default worker drains only the default queue and
  never ingest-pdf; the prod overlay hardens worker-pdf like worker; the pdf-worker
  image lives behind its own build target; and CI never installs the pdf extra.
* **WAL archiving substrate** — the `db` service continuously captures completed
  WAL segments onto a volume that outlives its data directory, and does so on a
  clean deploy with no host-side step. The assertions here pin the *mechanisms*
  that make that true (an image-declared, database-owned archive directory whose
  path is exactly the compose mount point; a replication-capable pg_hba.conf), not
  merely the wiring — a fresh named volume is root-owned when its mount path is
  absent from the image, which would fail at runtime far from its cause.

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

_PG_DIR = _REPO_ROOT / "deploy" / "postgres"
_PG_DOCKERFILE = (_PG_DIR / "Dockerfile").read_text()
_PG_HBA = (_PG_DIR / "pg_hba.conf").read_text()

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


def _dockerfile_stage(name: str) -> str:
    """The text of the ``FROM ... AS <name>`` stage, up to the next stage or EOF."""
    text = _DOCKERFILE.read_text()
    marker = f"AS {name}\n"
    start = text.index(marker) + len(marker)
    rest = text[start:]
    next_from = rest.find("\nFROM ")
    return rest if next_from == -1 else rest[:next_from]


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


def test_pdf_worker_bakes_the_easyocr_models() -> None:
    # Selective OCR needs its models at build time (no runtime downloads). Assert
    # on the executed download_models line, not the whole file, so flipping the
    # flag back off fails here.
    text = _DOCKERFILE.read_text()
    bake_lines = [
        line
        for line in text.splitlines()
        if "download_models" in line and line.lstrip().startswith("RUN")
    ]
    assert len(bake_lines) == 1
    assert "with_easyocr=True" in bake_lines[0]


# --- runtime image ships without dev deps and runs as non-root (OPS-16/17) ------


def test_runtime_stage_installs_no_dev_extra() -> None:
    assert "--extra dev" not in _dockerfile_stage("runtime")


def test_runtime_stage_runs_as_a_non_root_user() -> None:
    stage = _dockerfile_stage("runtime")
    users = [
        line.split(maxsplit=1)[1].strip() for line in stage.splitlines() if line.startswith("USER ")
    ]
    assert users, "runtime stage must set a USER"
    assert users[-1] not in {"root", "0"}


# --- CI never installs the pdf extra (AD-089 / CI parity) -----------------------


def test_ci_does_not_install_all_extras() -> None:
    text = _CI.read_text()
    assert "--all-extras" not in text
    assert "--extra dev" in text


# --- WAL archiving substrate (PITR-01, PITR-02) ---------------------------------
#
# The archive directory the whole recovery chain writes into. Named once here and
# cross-checked against the image, the compose mount, and the archive_command, so a
# change to any one of them without the others fails loudly.
_ARCHIVE_DIR = "/wal_archive"
_HBA_PATH = "/etc/postgresql/pg_hba.conf"


def _pg_settings(command: object) -> dict[str, str]:
    """The ``-c key=value`` postgres settings in a compose ``command``."""
    tokens = _tokens(command)
    settings: dict[str, str] = {}
    for index, token in enumerate(tokens):
        if token == "-c" and index + 1 < len(tokens):
            key, _, value = tokens[index + 1].partition("=")
            settings[key] = value
    return settings


def _hba_records() -> list[list[str]]:
    """The shipped pg_hba.conf as records, comments and blank lines dropped."""
    return [
        line.split()
        for line in _PG_HBA.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


@pytest.fixture
def db_settings(base: dict) -> dict[str, str]:
    return _pg_settings(base["db"]["command"])


def test_db_builds_from_the_repo_owned_postgres_image(base: dict) -> None:
    # Every guarantee below (a database-owned archive directory, a replication-capable
    # pg_hba.conf) is a property of the repo's own image. Falling back to the stock
    # image silently removes all of them, so pin that db is built here.
    assert base["db"]["build"]["context"] == "./deploy/postgres"
    assert "image" not in base["db"], "the base db service must build, not pull a stock image"
    assert _PG_DOCKERFILE.startswith("#")  # header comment retained
    assert "FROM pgvector/pgvector:pg16" in _PG_DOCKERFILE


def test_db_archives_completed_wal_segments(db_settings: dict[str, str]) -> None:
    # PITR-01: archiving is on and writes into the archive directory.
    assert db_settings["archive_mode"] == "on"
    assert _ARCHIVE_DIR in db_settings["archive_command"]


def test_archive_command_refuses_to_overwrite_an_existing_segment(
    db_settings: dict[str, str],
) -> None:
    # PITR-01's discriminating half. A bare `cp %p ...` also "archives", but silently
    # overwriting a segment corrupts the replay chain with no error anywhere. The
    # existence test must GUARD the copy (&&, so a present file fails the command and
    # PostgreSQL retains and retries) — never `||`, which would overwrite on failure.
    command = db_settings["archive_command"]
    assert f"test ! -f {_ARCHIVE_DIR}/%f" in command, (
        "archive_command must refuse to overwrite an existing segment"
    )
    guard, sep, copy = command.partition("&&")
    assert sep, "the existence test must be AND-joined to the copy, not sequenced"
    assert "||" not in command, "an OR would archive precisely when the guard refused"
    assert "test ! -f" in guard and "cp" in copy


def test_db_bounds_archive_timeout_so_an_idle_database_still_closes_segments(
    db_settings: dict[str, str],
) -> None:
    # PITR-01: without a bounded timeout an idle database holds a partially filled
    # segment indefinitely, so the archive silently lags the database by that segment.
    timeout = db_settings["archive_timeout"]
    default = timeout.partition(":-")[2].rstrip("}") if ":-" in timeout else timeout
    assert default.isdigit() and 0 < int(default) <= 3600, (
        f"archive_timeout must be bounded and non-zero, got {timeout!r}"
    )


def test_db_command_starts_the_postgres_server(base: dict) -> None:
    # The settings above only take effect if they are arguments to `postgres` itself.
    assert _tokens(base["db"]["command"])[0] == "postgres"


def test_the_archive_volume_is_mounted_at_the_path_the_image_declares(base: dict) -> None:
    """PITR-02 — the mechanism, not the wiring.

    Docker copies an image path's ownership into a *fresh, empty* named volume only
    when that exact path exists in the image; otherwise the volume is created
    root-owned and `archive_command`, which runs as the unprivileged database user,
    fails at runtime on a clean deploy. So the image must create the directory owned
    by the database user, and the compose mount point must be that same path — the
    coupling is what guarantees writability with no host-side chown.
    """
    created = [
        line
        for line in _PG_DOCKERFILE.splitlines()
        if "install -d" in line and _ARCHIVE_DIR in line
    ]
    assert created, f"the image must create {_ARCHIVE_DIR} owned by the database user"
    assert "-o postgres" in created[0], "the archive directory must be owned by the database user"
    mounts = base["db"]["volumes"]
    assert any(mount.endswith(f":{_ARCHIVE_DIR}") for mount in mounts), (
        f"db must mount the archive volume at {_ARCHIVE_DIR}, the path the image creates"
    )


def test_the_archive_never_lives_inside_the_data_volume(base: dict) -> None:
    # An archive stored under the data directory is lost with the very data directory
    # it exists to recover.
    data_mount = next(m for m in base["db"]["volumes"] if m.endswith("/var/lib/postgresql/data"))
    assert not _ARCHIVE_DIR.startswith(data_mount.split(":", 1)[1])
    archive_volume = next(
        m.split(":", 1)[0] for m in base["db"]["volumes"] if m.endswith(f":{_ARCHIVE_DIR}")
    )
    assert archive_volume != data_mount.split(":", 1)[0]
    assert archive_volume in (_load(_BASE).get("volumes") or {}), (
        "the archive volume must be declared as a named volume, not a bind mount"
    )


def test_the_backup_sidecar_shares_the_archive_volume() -> None:
    # The db holds no S3 client and no offsite credential by decision; the sidecar is
    # what ships and prunes, so it must see the same volume in prod and in dev/CI.
    archive_volume = next(
        m.split(":", 1)[0]
        for m in _services(_BASE)["db"]["volumes"]
        if m.endswith(f":{_ARCHIVE_DIR}")
    )
    for path in (_PROD, _OVERRIDE):
        backup = _load(path)["services"]["backup"]
        assert f"{archive_volume}:{_ARCHIVE_DIR}" in backup["volumes"], (
            f"the backup sidecar in {path.name} must mount the archive volume"
        )


# --- replication connectivity for pg_basebackup (T5 finding) --------------------


def test_db_uses_the_shipped_hba_file(base: dict, db_settings: dict[str, str]) -> None:
    # The stock entrypoint's generated pg_hba.conf has no remote replication rule, and
    # PostgreSQL's `all` database keyword does not match replication connections, so
    # pg_basebackup from the sidecar is refused outright. The shipped file is selected
    # via hba_file (a path outside PGDATA), which — unlike an initdb hook — also
    # applies to data directories that already exist.
    assert db_settings["hba_file"] == _HBA_PATH
    assert f"COPY pg_hba.conf {_HBA_PATH}" in _PG_DOCKERFILE


def test_the_shipped_hba_admits_remote_physical_replication() -> None:
    remote_replication = [
        record
        for record in _hba_records()
        if record[0] == "host" and record[1] == "replication" and record[3] == "all"
    ]
    assert remote_replication, (
        "pg_basebackup runs from another container; without a remote `replication` "
        "rule PostgreSQL refuses the connection regardless of the `all all` rule"
    )


def test_no_remote_rule_weakens_authentication_to_trust() -> None:
    # Admitting replication must not be paid for with authentication. `trust` may
    # appear only for the in-container local socket and loopback (what the stock image
    # already does); every rule reachable over the compose network stays password-based.
    loopback = {"127.0.0.1/32", "::1/128"}
    for record in _hba_records():
        connection_type, address, method = record[0], record[3], record[-1]
        if connection_type == "local" or address in loopback:
            continue
        assert method != "trust", f"remote rule must not use trust: {' '.join(record)}"
        assert method == "scram-sha-256", f"unexpected remote auth method: {' '.join(record)}"
