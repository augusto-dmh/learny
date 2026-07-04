# Runtime: Registration, Config, and Compose

Register tasks under `app.worker`, configure on the existing `celery_app`, and drive broker/backend from `Settings`. Run workers (and, if needed, one beat scheduler) as separate Compose services over the same image.

## Registration and config

The app object lives at `backend/app/worker/celery_app.py` as `celery_app = Celery("learny", broker=_settings.broker_url(), backend=_settings.result_backend())`. URLs come from `Settings` (`app.core.config.get_settings`, env prefix `LEARNY_`); never hardcode them. Add new settings to the existing `celery_app.conf.update(...)` block (see [reliability.md](reliability.md)).

Make task modules importable so Celery registers them. Either add an `include` list to the app, or `autodiscover_tasks`:

```python
celery_app = Celery(
    "learny",
    broker=_settings.broker_url(),
    backend=_settings.result_backend(),
    include=["app.worker.tasks.ingestion"],   # explicit module list
)
# or autodiscover a `tasks` submodule in each listed package
# (default related_name="tasks", so this imports app.worker.tasks):
# celery_app.autodiscover_tasks(["app.worker"])
```

Route long work to a dedicated queue with `task_routes` (default queue is `celery`):

```python
celery_app.conf.task_routes = {"ingestion.*": {"queue": "ingest"}}
```

## Worker CLI

Compose already runs `celery -A app.worker.celery_app:celery_app worker --loglevel=info`, health-checked with `celery -A app.worker.celery_app:celery_app inspect ping`. Useful flags:

- `-c` / `--concurrency N` — worker processes/threads.
- `-P` / `--pool prefork|solo|threads` — `prefork` (default) for CPU-bound parsing/embedding.
- `-Q` / `--queues ingest` — consume specific queues.
- `-l` / `--loglevel info`, `-n` / `--hostname` — logging and node name.

```bash
celery -A app.worker.celery_app:celery_app worker -Q ingest -c 4 -P prefork -l info
```

## Beat (scheduled tasks)

For periodic work (e.g. sweeping stuck ingestions), define a schedule on the app:

```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "sweep-stuck-ingestions": {
        "task": "ingestion.sweep_stuck",
        "schedule": crontab(minute="*/15"),   # or a float/timedelta of seconds
    },
}
```

Run **exactly one** beat scheduler for a given schedule — duplicate schedulers send duplicate periodic tasks. As a separate Compose service: `celery -A app.worker.celery_app:celery_app beat -l info`. The embedded `-B`/`--beat` flag on a worker is single-node/dev only; do not use it with multiple workers.

## Compose and env

The `worker` service builds the same backend image, sets `LEARNY_DATABASE_URL` and `LEARNY_REDIS_URL`, and `depends_on` db + redis (`service_healthy`). Compose uses `redis://redis:6379/0`; the local default is `redis://localhost:6379/0`. A beat service is a second entry over the same image with the `beat` command. Note: `backend/.env.example` currently omits `LEARNY_REDIS_URL` even though `Settings` defines it — surface/add it so local runs match Compose.

Reference: [Celery — CLI reference](https://docs.celeryq.dev/en/stable/reference/cli.html), [Celery — Periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), [Celery — Redis broker/backend](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html), [Celery — Configuration and defaults](https://docs.celeryq.dev/en/stable/userguide/configuration.html)
