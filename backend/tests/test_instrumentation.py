"""A1 gate — the in-process timing recorder (unit, OBS-01..06).

Every case here derives from the spec's "One timing recorder" acceptance
criteria: what a recorded sample carries (and what it must never carry), the
constant placeholder for an unmatched request, the eviction boundary, the shape
and ordering of the ranking, the exact nearest-rank p95, and safety under
concurrent recording. The containment cases pin the property the request and
database producers rely on — recording never raises into the path it measures.
"""

from __future__ import annotations

import inspect
import threading

from app.core.instrumentation import (
    UNKNOWN_METHOD,
    UNMATCHED_ROUTE,
    InstrumentRecorder,
    get_recorder,
    record_query,
    record_request,
    set_recorder,
)


def _record_many(
    recorder: InstrumentRecorder,
    durations: list[float],
    *,
    method: str = "GET",
    route: str = "/api/things",
) -> None:
    for duration in durations:
        recorder.record_request(method=method, route=route, status_code=200, duration_ms=duration)


# --- OBS-01: what a request sample carries ------------------------------------


def test_request_sample_carries_route_method_status_and_duration() -> None:
    recorder = InstrumentRecorder()

    recorder.record_request(
        method="get", route="/api/sources/{source_id}", status_code=204, duration_ms=12.5
    )

    (sample,) = recorder.recent_requests()
    assert sample.method == "GET"
    assert sample.route == "/api/sources/{source_id}"
    assert sample.status_code == 204
    assert sample.duration_ms == 12.5


def test_recording_a_request_accepts_no_path_query_header_or_body() -> None:
    # Invariant 1 is structural: the recorder cannot be handed request data that
    # would leak into a surface with weaker access control than the resources it
    # names. The keyword set is the whole contract.
    params = inspect.signature(InstrumentRecorder.record_request).parameters
    assert set(params) - {"self"} == {"method", "route", "status_code", "duration_ms"}
    assert set(inspect.signature(record_request).parameters) == {
        "method",
        "route",
        "status_code",
        "duration_ms",
    }


def test_a_query_string_never_reaches_the_stored_label() -> None:
    # A producer should always pass a route template; if a raw path with a query
    # string ever arrives, its values must not be stored.
    recorder = InstrumentRecorder()

    recorder.record_request(
        method="GET",
        route="/api/sources?token=super-secret",
        status_code=200,
        duration_ms=1.0,
    )

    (sample,) = recorder.recent_requests()
    assert sample.route == "/api/sources"
    assert "super-secret" not in repr(recorder.snapshot())


# --- OBS-02: the unmatched placeholder -----------------------------------------


def test_an_unmatched_request_buckets_under_one_constant_label() -> None:
    recorder = InstrumentRecorder()

    recorder.record_request(method="GET", route=None, status_code=404, duration_ms=2.0)
    recorder.record_request(method="GET", route="   ", status_code=404, duration_ms=3.0)

    (row,) = recorder.rank_endpoints()
    assert row.route == UNMATCHED_ROUTE
    assert row.count == 2


def test_a_missing_method_falls_back_to_a_constant_label() -> None:
    recorder = InstrumentRecorder()

    recorder.record_request(method="", route="/api/things", status_code=200, duration_ms=1.0)

    (row,) = recorder.rank_endpoints()
    assert row.method == UNKNOWN_METHOD


# --- OBS-03: the eviction boundary ---------------------------------------------


def test_the_newest_samples_up_to_capacity_are_retained_exactly() -> None:
    recorder = InstrumentRecorder(capacity=3)

    _record_many(recorder, [1.0, 2.0, 3.0, 4.0, 5.0])

    retained = [sample.duration_ms for sample in recorder.recent_requests()]
    assert retained == [5.0, 4.0, 3.0]
    assert recorder.rank_endpoints()[0].count == 3


def test_slow_query_entries_are_bounded_by_the_same_capacity() -> None:
    recorder = InstrumentRecorder(capacity=2)

    for index in range(4):
        recorder.record_query(statement=f"SELECT {index}", duration_ms=300.0)

    assert [entry.statement for entry in recorder.recent_queries()] == [
        "SELECT 3",
        "SELECT 2",
    ]


def test_a_captured_statement_is_truncated_to_the_configured_cap() -> None:
    # Bounded storage has two dimensions: a buffer of unbounded strings is not
    # bounded, so the statement text is capped as well as the sample count.
    recorder = InstrumentRecorder(statement_max_chars=10)

    recorder.record_query(statement="SELECT * FROM a_very_wide_table", duration_ms=900.0)

    (entry,) = recorder.recent_queries()
    assert entry.statement == "SELECT * F"


# --- OBS-04: the ranking ---------------------------------------------------------


def test_ranking_reports_count_mean_max_and_p95_per_method_and_route() -> None:
    recorder = InstrumentRecorder()

    _record_many(recorder, [10.0, 20.0, 30.0], method="GET", route="/api/books")
    recorder.record_request(method="POST", route="/api/books", status_code=201, duration_ms=50.0)

    rows = {(row.method, row.route): row for row in recorder.rank_endpoints()}
    assert set(rows) == {("GET", "/api/books"), ("POST", "/api/books")}
    get_row = rows[("GET", "/api/books")]
    assert get_row.count == 3
    assert get_row.mean_ms == 20.0
    assert get_row.max_ms == 30.0
    assert get_row.p95_ms == 30.0


def test_ranking_is_ordered_by_descending_p95() -> None:
    recorder = InstrumentRecorder()

    _record_many(recorder, [5.0], route="/api/fast")
    _record_many(recorder, [500.0], route="/api/slow")
    _record_many(recorder, [50.0], route="/api/middling")

    assert [row.route for row in recorder.rank_endpoints()] == [
        "/api/slow",
        "/api/middling",
        "/api/fast",
    ]


def test_equal_p95_falls_back_to_descending_maximum() -> None:
    # Both groups have a p95 of 100 ms; the one whose worst sample is far worse
    # must rank first. Recorded steady-first so ordering cannot come from arrival.
    recorder = InstrumentRecorder()

    _record_many(recorder, [100.0], route="/api/steady")
    _record_many(recorder, [100.0] * 19 + [900.0], route="/api/spiky")

    ranked = recorder.rank_endpoints()
    assert [row.route for row in ranked] == ["/api/spiky", "/api/steady"]
    assert ranked[0].p95_ms == ranked[1].p95_ms == 100.0
    assert (ranked[0].max_ms, ranked[1].max_ms) == (900.0, 100.0)


def test_an_empty_recorder_ranks_to_nothing_without_raising() -> None:
    snapshot = InstrumentRecorder().snapshot()

    assert snapshot.endpoints == ()
    assert snapshot.slow_queries == ()


# --- OBS-05: nearest-rank p95 ------------------------------------------------------


def test_p95_of_a_single_sample_is_that_sample() -> None:
    recorder = InstrumentRecorder()

    _record_many(recorder, [42.0])

    assert recorder.rank_endpoints()[0].p95_ms == 42.0


def test_p95_is_the_ascending_sorted_value_at_the_nearest_rank() -> None:
    # n = 20 -> ceil(0.95 * 20) - 1 = 18, i.e. the second-largest of 1..20, and
    # insertion order must not matter.
    recorder = InstrumentRecorder()

    _record_many(recorder, [float(value) for value in reversed(range(1, 21))])

    row = recorder.rank_endpoints()[0]
    assert row.p95_ms == 19.0
    assert row.max_ms == 20.0


def test_p95_rounds_the_rank_up_for_a_sample_count_that_does_not_divide() -> None:
    # n = 3 -> ceil(2.85) - 1 = 2, the largest sample.
    recorder = InstrumentRecorder()

    _record_many(recorder, [1.0, 2.0, 9.0])

    assert recorder.rank_endpoints()[0].p95_ms == 9.0


# --- OBS-06: concurrent recording ---------------------------------------------------


def test_concurrent_recording_loses_no_sample() -> None:
    recorder = InstrumentRecorder(capacity=4000)
    threads = [
        threading.Thread(target=_record_many, args=(recorder, [1.0] * 200)) for _ in range(8)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert recorder.rank_endpoints()[0].count == 1600
    assert len(recorder.recent_requests()) == 1600


def test_concurrent_recording_stays_within_capacity() -> None:
    recorder = InstrumentRecorder(capacity=100)

    def _mixed_load() -> None:
        for index in range(200):
            recorder.record_request(
                method="GET", route="/api/things", status_code=200, duration_ms=float(index)
            )
            recorder.record_query(statement=f"SELECT {index}", duration_ms=float(index))

    threads = [threading.Thread(target=_mixed_load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(recorder.recent_requests()) == 100
    assert len(recorder.recent_queries()) == 100
    # No torn samples: every retained entry is one a producer actually wrote.
    assert all(
        sample.route == "/api/things"
        and sample.method == "GET"
        and sample.status_code == 200
        and sample.duration_ms in {float(index) for index in range(200)}
        for sample in recorder.recent_requests()
    )


def test_reading_a_snapshot_while_recording_never_tears() -> None:
    # The consumer reads from the event loop while producers record from the sync
    # threadpool, so reads and writes overlap by construction. Neither side may
    # observe a half-mutated buffer.
    recorder = InstrumentRecorder(capacity=50)
    stop = threading.Event()
    failures: list[BaseException] = []

    def _write() -> None:
        try:
            for index in range(2000):
                recorder.record_request(
                    method="GET",
                    route="/api/things",
                    status_code=200,
                    duration_ms=float(index),
                )
                recorder.record_query(statement=f"SELECT {index}", duration_ms=1.0)
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            failures.append(exc)
        finally:
            stop.set()

    def _read() -> None:
        try:
            while not stop.is_set():
                snapshot = recorder.snapshot()
                assert sum(row.count for row in snapshot.endpoints) <= 50
                assert len(snapshot.slow_queries) <= 50
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            failures.append(exc)

    threads = [threading.Thread(target=_write) for _ in range(4)]
    threads += [threading.Thread(target=_read) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []


# --- Containment: the instrument never changes what it measures ----------------------


def test_recording_an_unusable_duration_is_dropped_rather_than_raised() -> None:
    recorder = InstrumentRecorder()

    recorder.record_request(method="GET", route="/api/things", status_code=200, duration_ms="slow")
    recorder.record_request(
        method="GET", route="/api/things", status_code=200, duration_ms=float("nan")
    )
    recorder.record_query(statement="SELECT 1", duration_ms=None)

    # Nothing was stored, and the read path still answers.
    assert recorder.recent_requests() == ()
    assert recorder.recent_queries() == ()
    assert recorder.snapshot().endpoints == ()


def test_a_failing_recorder_cannot_escalate_into_its_producer() -> None:
    class ExplodingRecorder(InstrumentRecorder):
        def record_request(self, **kwargs: object) -> None:
            raise RuntimeError("instrument is broken")

        def record_query(self, **kwargs: object) -> None:
            raise RuntimeError("instrument is broken")

    previous = get_recorder()
    set_recorder(ExplodingRecorder())
    try:
        record_request(method="GET", route="/api/things", status_code=200, duration_ms=1.0)
        record_query(statement="SELECT 1", duration_ms=900.0)
    finally:
        set_recorder(previous)


def test_the_producer_entry_points_write_to_the_active_recorder() -> None:
    recorder = InstrumentRecorder()
    previous = get_recorder()
    set_recorder(recorder)
    try:
        record_request(method="GET", route="/api/things", status_code=200, duration_ms=7.0)
        record_query(statement="SELECT 1", duration_ms=900.0)
    finally:
        set_recorder(previous)

    assert recorder.rank_endpoints()[0].route == "/api/things"
    assert recorder.recent_queries()[0].statement == "SELECT 1"
