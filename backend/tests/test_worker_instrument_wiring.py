"""Worker composition root — the instrument's bounds come from settings (OBS-26).

``get_engine()`` installs slow-statement capture on whatever process calls it, and
the worker calls it from every task, so the worker feeds the same recorder the API
does. Its bounds must therefore come from the same settings: the runbook documents
``LEARNY_INSTRUMENT_CAPACITY`` and ``LEARNY_SLOW_QUERY_STATEMENT_CHARS`` as
per-process, and a process where they sit at the module defaults makes that claim
false. (``LEARNY_SLOW_QUERY_MS`` was always honoured here — it is read when the
engine is built — which is exactly what hid the gap.)

The wiring under test is module-level, so the case runs it in a **subprocess**: it
imports the worker module the way the worker's entrypoint does, with the settings
supplied through the environment, and reads back the recorder that import
installed. Reproducing the composition in-process would test a copy of it, and
reloading the module here would swap the Celery app the rest of the suite has
already imported.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: The backend package root — the working directory the worker starts from.
BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: Imports the worker's composition root and reports the recorder it installed.
PROBE = (
    "import app.worker.celery_app;"
    "from app.core.instrumentation import get_recorder;"
    "r = get_recorder();"
    "print(r.capacity, r.statement_max_chars)"
)

#: Deliberately unlike the module defaults (500 / 2000), so a recorder left at
#: them cannot pass by coincidence.
CAPACITY = "7"
STATEMENT_CHARS = "11"


def test_the_worker_builds_its_recorder_from_the_configured_bounds() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND_ROOT,
        env={
            **os.environ,
            "LEARNY_INSTRUMENT_CAPACITY": CAPACITY,
            "LEARNY_SLOW_QUERY_STATEMENT_CHARS": STATEMENT_CHARS,
        },
        capture_output=True,
        text=True,
        check=True,
    )

    reported = result.stdout.strip().splitlines()[-1].split()
    assert reported == [CAPACITY, STATEMENT_CHARS], result.stdout
