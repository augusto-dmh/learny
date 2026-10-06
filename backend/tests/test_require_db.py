"""``LEARNY_REQUIRE_DB=1`` turns a missing test database into a failed run.

Every database-backed test skips when ``LEARNY_TEST_DATABASE_URL`` is unset, so a
run in a session with no database reports green over a suite that never touched
the schema — a Verifier once issued PASS over 940 such skips. CI and the Verifier
set the flag; a plain local run keeps the quiet skip for a fast unit-only loop.

Each case runs pytest in a subprocess over one real database-gated test, because
the guard lives in the session's own configuration and cannot be observed from
inside a run that already started.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_DB_GATED_TEST = "tests/test_migrations.py::test_upgrade_honors_caller_provided_url"


def _run_without_database(*, require_db: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("LEARNY_TEST_DATABASE_URL",)}
    env.pop("LEARNY_REQUIRE_DB", None)
    if require_db is not None:
        env["LEARNY_REQUIRE_DB"] = require_db
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", _DB_GATED_TEST],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_flag_refuses_a_run_without_a_database_url() -> None:
    result = _run_without_database(require_db="1")
    output = result.stdout + result.stderr
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, output
    assert "LEARNY_TEST_DATABASE_URL" in output
    # Refused before collection ran anything: nothing passed, nothing skipped.
    assert "skipped" not in output
    assert "passed" not in output


def test_a_database_test_still_skips_without_the_flag() -> None:
    result = _run_without_database(require_db=None)
    output = result.stdout + result.stderr
    assert result.returncode == pytest.ExitCode.OK, output
    assert "1 skipped" in output


def test_a_flag_value_other_than_one_keeps_the_skip() -> None:
    # The flag is exactly "1"; anything else is off, so a stray value cannot
    # silently change what a local run means.
    result = _run_without_database(require_db="0")
    assert result.returncode == pytest.ExitCode.OK, result.stdout + result.stderr
