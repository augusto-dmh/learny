"""C1 gate — slow-statement capture on the application engine (integration, OBS-11..15).

Every case derives from the spec's "Slow query capture" acceptance criteria, and
every one of them drives a *real statement through the engine the application
builds* (``get_engine``) against the live test database. That is deliberate: the
thing under test is not a handler function but the wiring, so a test that called
the handler by hand would keep passing after someone removed the listener from
``get_engine``. The companion case pins the other half — an engine built with a
bare ``create_engine`` (which is what the test fixtures and Alembic use) captures
nothing, so capture is demonstrably a property of the application's engine rather
than a global side effect of importing anything.

The redaction case is the one that matters most: session tokens and password
hashes reach the database as *bound parameters*. It therefore asserts the absence
of a value that would be a secret — through the single-execute path and the
``executemany`` path — rather than merely asserting that the captured text looks
like SQL.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from app.core.config import get_settings
from app.core.instrumentation import (
    InstrumentRecorder,
    get_recorder,
    set_recorder,
)
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.instrumentation import (
    SLOW_QUERY_LOGGER,
    SLOW_QUERY_MESSAGE,
    is_slow,
)
from tests.conftest import TEST_DB_URL, requires_db

pytestmark = requires_db

#: Long enough to clear a 200 ms threshold on a loaded machine without slowing the
#: suite noticeably.
SLEEP_SECONDS = 0.35

#: Threshold that captures nothing a local Postgres can produce.
NEVER_SLOW_MS = 10_000

#: A value shaped like the secrets that really travel as bound parameters.
SECRET_TOKEN = "s3ss10n-token-3f9c1d0a-never-log-me"
OTHER_SECRET_TOKEN = "s3ss10n-token-77bb2e41-never-log-me"


class _RecordingHandler(logging.Handler):
    """Collect the structured slow-query records emitted during one test."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == SLOW_QUERY_LOGGER:
            self.records.append(record)

    @property
    def slow_queries(self) -> list[logging.LogRecord]:
        return [r for r in self.records if r.getMessage() == SLOW_QUERY_MESSAGE]


@pytest.fixture
def captured() -> Iterator[_RecordingHandler]:
    """Attach a recording handler to root; force the slow-query logger enabled."""
    handler = _RecordingHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.DEBUG)
    query_logger = logging.getLogger(SLOW_QUERY_LOGGER)
    query_logger.disabled = False
    query_logger.setLevel(logging.NOTSET)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@pytest.fixture
def recorder() -> Iterator[InstrumentRecorder]:
    """Install a fresh recorder for the duration of one test."""
    previous = get_recorder()
    fresh = InstrumentRecorder()
    set_recorder(fresh)
    try:
        yield fresh
    finally:
        set_recorder(previous)


@pytest.fixture
def build_app_engine(  # noqa: ANN201
    monkeypatch: pytest.MonkeyPatch,
    recorder: InstrumentRecorder,
    captured: _RecordingHandler,
):
    """Build *the application engine* against the test database at a given threshold.

    Goes through ``get_engine`` — the same call the web layer and the worker make —
    with the configured threshold supplied through the environment, so what the
    tests exercise is the shipped wiring. The engine is warmed first: SQLAlchemy's
    dialect issues its own setup statements on the first connection, which a
    zero threshold would otherwise capture and count.
    """
    built: list[Engine] = []

    def _build(*, slow_query_ms: int) -> Engine:
        monkeypatch.setenv("LEARNY_DATABASE_URL", str(TEST_DB_URL))
        monkeypatch.setenv("LEARNY_SLOW_QUERY_MS", str(slow_query_ms))
        get_settings.cache_clear()
        get_engine.cache_clear()
        engine = get_engine()
        built.append(engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        recorder.reset()
        captured.records.clear()
        return engine

    yield _build

    for engine in built:
        engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _statements(recorder: InstrumentRecorder) -> list[str]:
    return [sample.statement for sample in recorder.recent_queries()]


def _record_text(record: logging.LogRecord) -> str:
    """Every value the record carries, so a leak cannot hide in an unexpected field."""
    return " ".join(str(value) for value in record.__dict__.values())


# --- OBS-11: a slow statement produces one log record and one recorder entry ----


def test_a_slow_statement_is_logged_and_recorded_with_its_text_and_duration(
    build_app_engine, recorder: InstrumentRecorder, captured: _RecordingHandler
) -> None:
    engine = build_app_engine(slow_query_ms=200)

    with engine.connect() as conn:
        conn.execute(text(f"SELECT pg_sleep({SLEEP_SECONDS})"))

    (sample,) = recorder.recent_queries()
    assert "pg_sleep" in sample.statement
    assert sample.duration_ms >= 200

    (record,) = captured.slow_queries
    assert "pg_sleep" in record.statement
    assert record.duration_ms >= 200


# --- OBS-12: a fast statement produces neither -----------------------------------


def test_a_statement_below_the_threshold_is_neither_logged_nor_recorded(
    build_app_engine, recorder: InstrumentRecorder, captured: _RecordingHandler
) -> None:
    engine = build_app_engine(slow_query_ms=NEVER_SLOW_MS)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1

    assert recorder.recent_queries() == ()
    assert captured.slow_queries == []


def test_a_threshold_of_zero_captures_every_statement(
    build_app_engine, recorder: InstrumentRecorder
) -> None:
    # AD-175: no implicit floor, so the capture path is exercisable without sleeping
    # and an environment can deliberately record everything.
    engine = build_app_engine(slow_query_ms=0)

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    assert _statements(recorder) == ["SELECT 1"]


def test_the_threshold_is_met_at_its_boundary_and_has_no_implicit_floor() -> None:
    # "at least ``LEARNY_SLOW_QUERY_MS``" — the boundary value itself qualifies, the
    # value just below it does not, and a threshold of zero or below admits
    # everything rather than being floored to some minimum.
    assert is_slow(200.0, 200.0) is True
    assert is_slow(199.999, 200.0) is False
    assert is_slow(0.0, 0.0) is True
    assert is_slow(0.0, -1.0) is True


# --- OBS-13: no bound parameter value reaches the capture ------------------------


def test_a_bound_parameter_value_never_reaches_the_captured_statement(
    build_app_engine, recorder: InstrumentRecorder, captured: _RecordingHandler
) -> None:
    engine = build_app_engine(slow_query_ms=0)

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT :session_token AS session_token"),
                {"session_token": SECRET_TOKEN},
            ).scalar_one()
            == SECRET_TOKEN
        )

    statements = _statements(recorder)
    assert statements, "the statement should have been captured at a zero threshold"
    assert any("session_token" in statement for statement in statements)
    for statement in statements:
        assert SECRET_TOKEN not in statement
    for record in captured.records:
        assert SECRET_TOKEN not in _record_text(record)


def test_an_executemany_parameter_value_never_reaches_the_captured_statement(
    build_app_engine, recorder: InstrumentRecorder, captured: _RecordingHandler
) -> None:
    # ``executemany`` hands the listener a *sequence* of parameter sets; it is a
    # separate driver path and must leak no more than the single-execute one.
    engine = build_app_engine(slow_query_ms=0)

    with engine.begin() as conn:
        conn.execute(text("CREATE TEMP TABLE slow_query_probe (token text)"))
        conn.execute(
            text("INSERT INTO slow_query_probe (token) VALUES (:token)"),
            [{"token": SECRET_TOKEN}, {"token": OTHER_SECRET_TOKEN}],
        )

    statements = _statements(recorder)
    assert any("INSERT INTO slow_query_probe" in statement for statement in statements)
    for secret in (SECRET_TOKEN, OTHER_SECRET_TOKEN):
        for statement in statements:
            assert secret not in statement
        for record in captured.records:
            assert secret not in _record_text(record)


# --- OBS-14: the captured statement is stored truncated to the cap ---------------


def test_a_long_statement_is_stored_truncated_to_the_configured_cap(
    build_app_engine, recorder: InstrumentRecorder
) -> None:
    engine = build_app_engine(slow_query_ms=0)
    capped = InstrumentRecorder(statement_max_chars=40)
    set_recorder(capped)

    with engine.connect() as conn:
        conn.execute(text("SELECT 1 AS a -- " + "x" * 3000))

    (sample,) = capped.recent_queries()
    assert len(sample.statement) == 40
    assert sample.statement.startswith("SELECT 1 AS a")


# --- OBS-15: a failing capture leaves the database operation intact --------------


def test_a_failing_capture_leaves_the_statement_result_untouched(
    build_app_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explode(**_: object) -> None:
        raise RuntimeError("capture exploded")

    engine = build_app_engine(slow_query_ms=0)
    monkeypatch.setattr("app.infrastructure.db.instrumentation.record_query", _explode)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT 42 AS answer")).scalar_one() == 42


def test_a_failing_capture_leaves_a_database_error_raised_as_before(
    build_app_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explode(**_: object) -> None:
        raise RuntimeError("capture exploded")

    engine = build_app_engine(slow_query_ms=0)
    monkeypatch.setattr("app.infrastructure.db.instrumentation.record_query", _explode)

    with engine.connect() as conn, pytest.raises(ProgrammingError):
        conn.execute(text("SELECT * FROM no_such_table_for_instrumentation"))


# --- The instrumented engine is the application's, not any engine ----------------


def test_an_engine_not_built_by_the_application_captures_nothing(
    db_engine: Engine, build_app_engine, recorder: InstrumentRecorder
) -> None:
    # The fixtures' engine and Alembic's are separate ``create_engine`` calls. Only
    # the engine the application builds is instrumented, so capture cannot be an
    # accident of importing a module.
    build_app_engine(slow_query_ms=0)

    with db_engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    assert recorder.recent_queries() == ()
