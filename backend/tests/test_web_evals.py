"""The dev-only eval-results surface (integration, live test DB; EVDASH-05..07).

Every case derives from the spec's gating and payload acceptance criteria: what
the flag decides, what a production process decides regardless of the flag, what
authentication decides, and what an enabled, authenticated read returns.

The gates are exercised independently on purpose — a single test that both
enabled the flag and authenticated would still pass with either gate removed, so
one test per gate is what makes each of them a sensor. The production case is the
sensor for the refusal itself: it sets the flag *and* configures the process as
production, which is the state a leaked ``.env`` or an operator-authored secrets
file produces, and asserts nothing is mounted.

The two dev surfaces are also pinned as independent here. They share a shape, and
sharing a shape is exactly how one switch quietly comes to serve both.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.eval.judge import FAITHFULNESS_MIN, RELEVANCY_MIN, RESULTS_DIR
from tests.conftest import TEST_ORIGIN, requires_db

pytestmark = requires_db

ClientBuilder = Callable[..., TestClient]

EVALS_PATH = "/api/dev/evals"
INSTRUMENT_PATH = "/api/dev/instrument"

#: Logger the composition root records a refused dashboard flag on — its own,
#: not the instrument's, so an operator can filter a refusal by the surface it
#: belongs to.
EVAL_LOGGER = "app.eval_dashboard"


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    """A results directory holding one passing run and one failing run.

    Both mix the two record families, because every real nightly file does.
    """
    directory = tmp_path / "results"
    directory.mkdir()
    passing = [
        {
            "case_id": "printing-movable-type",
            "ts": "2026-07-30T10:00:00+00:00",
            "git_sha": "aaa1111",
            "generation_model": "claude-sonnet-5",
            "judge_model": "claude-opus-4-8",
            "prompt_hash": "hash",
            "faithfulness": 1.0,
            "relevancy": 5,
            "citation_valid": True,
            "found": True,
        },
        {
            "item_id": "free_recall-0",
            "ts": "2026-07-30T10:00:01+00:00",
            "judge_model": "claude-haiku-4-5",
            "answerable": True,
            "score": 5,
            "reason": "recoverable",
        },
    ]
    failing = [
        {
            "case_id": "weak-case",
            "ts": "2026-07-29T10:00:00+00:00",
            "git_sha": "bbb2222",
            "generation_model": "claude-sonnet-5",
            "judge_model": "claude-opus-4-8",
            "prompt_hash": "hash",
            "faithfulness": 0.2,
            "relevancy": 1,
            "citation_valid": True,
            "found": True,
        },
    ]
    for name, lines in (
        ("2026-07-30-aaa1111.jsonl", passing),
        ("2026-07-29-bbb2222.jsonl", failing),
    ):
        (directory / name).write_text(
            "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines), encoding="utf-8"
        )
    return directory


@pytest.fixture
def build_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[ClientBuilder]:
    """Build a ``TestClient`` over an app assembled with a chosen flag/environment.

    Assembly is deferred to the test because the flag is read at app-assembly
    time and each case needs a different reading of it.
    """
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    with ExitStack() as stack:

        def _build(*, enabled: bool, **env: str) -> TestClient:
            monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
            monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
            monkeypatch.setenv("LEARNY_DEV_EVAL_DASHBOARD_ENABLED", "true" if enabled else "false")
            for name, value in env.items():
                monkeypatch.setenv(name, value)
            get_settings.cache_clear()

            app = create_app()

            def _override() -> Iterator[Connection]:
                yield db_conn

            app.dependency_overrides[get_db_connection] = _override
            client = stack.enter_context(TestClient(app, headers={"Origin": TEST_ORIGIN}))
            stack.callback(app.dependency_overrides.clear)
            return client

        yield _build

    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201, resp.text


# --- EVDASH-05: the flag decides whether the route exists at all ----------------


def test_surface_is_absent_when_the_flag_is_off(build_client: ClientBuilder) -> None:
    client = build_client(enabled=False)
    _register(client, "evals-flag-off@example.com")

    assert client.get(EVALS_PATH).status_code == 404


def test_surface_is_absent_from_the_schema_when_the_flag_is_off(
    build_client: ClientBuilder,
) -> None:
    """An unmounted route is not merely refused — it is not advertised either."""
    off = build_client(enabled=False)
    on = build_client(enabled=True)

    assert EVALS_PATH not in off.get("/openapi.json").json()["paths"]
    assert EVALS_PATH in on.get("/openapi.json").json()["paths"]


def test_production_process_refuses_the_flag(
    build_client: ClientBuilder, caplog: pytest.LogCaptureFixture
) -> None:
    """The state a leaked env file produces: flag on, process configured production."""
    with caplog.at_level(logging.WARNING, logger=EVAL_LOGGER):
        client = build_client(enabled=True, LEARNY_ENVIRONMENT="production")
    _register(client, "evals-production@example.com")

    assert client.get(EVALS_PATH).status_code == 404
    assert EVALS_PATH not in client.get("/openapi.json").json()["paths"]
    assert any("eval_dashboard.surface.refused" in record.message for record in caplog.records)


def test_the_two_dev_surfaces_switch_independently(build_client: ClientBuilder) -> None:
    """Enabling the dashboard must not expose the instrument, or vice versa."""
    dashboard_only = build_client(enabled=True, LEARNY_DEV_INSTRUMENT_ENABLED="false")
    paths = dashboard_only.get("/openapi.json").json()["paths"]

    assert EVALS_PATH in paths
    assert INSTRUMENT_PATH not in paths


def test_instrument_alone_does_not_expose_the_dashboard(build_client: ClientBuilder) -> None:
    instrument_only = build_client(enabled=False, LEARNY_DEV_INSTRUMENT_ENABLED="true")
    paths = instrument_only.get("/openapi.json").json()["paths"]

    assert INSTRUMENT_PATH in paths
    assert EVALS_PATH not in paths


# --- EVDASH-05: authentication gates a mounted surface --------------------------


def test_mounted_surface_refuses_an_unauthenticated_read(build_client: ClientBuilder) -> None:
    client = build_client(enabled=True)

    assert client.get(EVALS_PATH).status_code == 401


# --- EVDASH-06/07: what an enabled, authenticated read returns ------------------


def test_authenticated_read_returns_the_discovered_runs(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-read@example.com")

    resp = client.get(EVALS_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [run["run_id"] for run in body["runs"]] == ["2026-07-30-aaa1111", "2026-07-29-bbb2222"]


def test_payload_carries_the_gate_thresholds(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    """The client draws its reference lines from the server's constants."""
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-thresholds@example.com")

    thresholds = client.get(EVALS_PATH).json()["thresholds"]

    assert thresholds == {
        "faithfulness_min": FAITHFULNESS_MIN,
        "relevancy_min": RELEVANCY_MIN,
    }


def test_payload_names_the_judge_in_force(build_client: ClientBuilder, results_dir: Path) -> None:
    """A run judged by another model was gated against other thresholds.

    Without this the page cannot tell a real regression from a run that merely
    predates a recalibration — which is most of the published history.
    """
    client = build_client(
        enabled=True,
        LEARNY_EVAL_RESULTS_DIR=str(results_dir),
        LEARNY_JUDGE_MODEL="claude-opus-4-8",
    )
    _register(client, "evals-judge@example.com")

    assert client.get(EVALS_PATH).json()["judge_model_in_force"] == "claude-opus-4-8"


def test_payload_names_the_directory_it_read(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    """A default checkout is not the whole history; the reader must say where it looked."""
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-scope@example.com")

    body = client.get(EVALS_PATH).json()

    assert body["results_dir"] == str(results_dir)
    assert body["scope"]


def test_verdicts_distinguish_the_passing_run_from_the_failing_one(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-verdict@example.com")

    runs = {run["run_id"]: run for run in client.get(EVALS_PATH).json()["runs"]}

    assert runs["2026-07-30-aaa1111"]["verdict"] == "pass"
    assert runs["2026-07-29-bbb2222"]["verdict"] == "fail"
    assert set(runs["2026-07-29-bbb2222"]["failures"]) == {"faithfulness", "relevancy"}


def test_cases_are_included_for_the_drill_down(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-cases@example.com")

    runs = {run["run_id"]: run for run in client.get(EVALS_PATH).json()["runs"]}

    assert [case["case_id"] for case in runs["2026-07-30-aaa1111"]["cases"]] == [
        "printing-movable-type"
    ]


def test_answerability_records_are_reported_separately(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    """They share the file with the generation records and must not vanish."""
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-answerability@example.com")

    runs = {run["run_id"]: run for run in client.get(EVALS_PATH).json()["runs"]}

    assert runs["2026-07-30-aaa1111"]["answerability_count"] == 1
    assert runs["2026-07-30-aaa1111"]["answerability_mean_score"] == 5.0


def test_an_unset_results_dir_falls_back_to_the_judges_own_directory(
    build_client: ClientBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented default. Every other 200-returning test sets the variable."""
    monkeypatch.delenv("LEARNY_EVAL_RESULTS_DIR", raising=False)
    client = build_client(enabled=True)
    _register(client, "evals-default-dir@example.com")

    assert client.get(EVALS_PATH).json()["results_dir"] == str(RESULTS_DIR)


def test_the_run_list_is_bounded_and_says_when_it_truncates(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    """The nightly appends forever with no retention, so the read path needs a cap."""
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-limit@example.com")

    body = client.get(f"{EVALS_PATH}?limit=1").json()

    assert len(body["runs"]) == 1
    assert body["total_runs"] == 2
    # Newest first, so a truncated view keeps the runs that matter.
    assert body["runs"][0]["run_id"] == "2026-07-30-aaa1111"


def test_an_out_of_range_limit_is_refused(build_client: ClientBuilder, results_dir: Path) -> None:
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-limit-range@example.com")

    assert client.get(f"{EVALS_PATH}?limit=0").status_code == 422
    assert client.get(f"{EVALS_PATH}?limit=100000").status_code == 422


def test_headline_metrics_are_reported_beside_the_verdict(
    build_client: ClientBuilder, results_dir: Path
) -> None:
    """The page renders these next to the badge, so they share the verdict's lines."""
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(results_dir))
    _register(client, "evals-metrics@example.com")

    runs = {run["run_id"]: run for run in client.get(EVALS_PATH).json()["runs"]}

    assert runs["2026-07-30-aaa1111"]["metrics"] == {
        "scored": 1,
        "answered": 1,
        "mean_faithfulness": 1.0,
        "mean_relevancy": 5.0,
        "citation_valid_rate": 1.0,
    }


def test_a_directory_with_no_runs_reads_as_empty_not_as_an_error(
    build_client: ClientBuilder, tmp_path: Path
) -> None:
    """Nothing has run yet is a normal state, not a failure."""
    client = build_client(enabled=True, LEARNY_EVAL_RESULTS_DIR=str(tmp_path / "absent"))
    _register(client, "evals-empty@example.com")

    resp = client.get(EVALS_PATH)

    assert resp.status_code == 200
    assert resp.json()["runs"] == []
