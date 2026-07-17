# Learny backend image. A shared `base` stage carries the interpreter, uv, and
# the dependency manifests; two leaf stages build on it:
#   * `runtime`    — the default image for the `api` and `worker` services (the
#                    last stage, so a build with no `target` resolves here).
#   * `pdf-worker` — the isolated PDF ingestion worker: the `pdf` extra (docling)
#                    with its models baked in. Built only on demand (compose
#                    `target: pdf-worker`); the default image never installs it.
FROM python:3.13-slim AS base

# uv for fast, locked installs (CONVENTIONS.md).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# curl is used by the api healthcheck; build essentials kept minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency manifests first (cached layer) using the committed lockfile.
COPY pyproject.toml uv.lock ./

# PDF ingestion worker (ING-18/19, ADR-0025). Installs the `pdf` extra (docling +
# easyocr) — no dev extra — and bakes the layout, table-structure, and EasyOCR
# models into the image so conversion needs no network egress at task time. HOME
# is pinned so the bake and the runtime celery worker read/write the same docling
# model cache ($HOME/.cache/docling). EasyOCR's opencv-python-headless wheel
# links libxcb/glib, which the slim base lacks — installed after the dependency
# sync so the heavy wheel layers stay cacheable.
FROM base AS pdf-worker
ENV HOME=/root
RUN uv sync --frozen --no-install-project --extra pdf
COPY . .
RUN uv sync --frozen --extra pdf
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/*
RUN python -c "from docling.utils.model_downloader import download_models; download_models(with_layout=True, with_tableformer=True, with_rapidocr=False, with_code_formula=False, with_picture_classifier=False, with_easyocr=True)"
CMD ["celery", "-A", "app.worker.celery_app:celery_app", "worker", \
     "--loglevel=info", "--queues", "ingest-pdf", \
     "--concurrency", "1", "--max-tasks-per-child", "1"]

# Default image for the api and worker services. Last stage, so an untargeted
# build (api/worker in compose) resolves here; docling is never installed. Only
# the main dependencies land — no dev extra — so the dispatch factory's PDF
# branch is unreachable here and never imports docling/docling_core.
FROM base AS runtime
RUN uv sync --frozen --no-install-project

# Application source.
COPY . .
RUN uv sync --frozen

# Run as a dedicated non-root user. The venv and source are root-owned and only
# read at runtime — the api (uvicorn) and worker (celery) write nothing under
# /app — so read-only ownership is sufficient.
RUN groupadd --system --gid 10001 learny \
    && useradd --system --uid 10001 --gid learny --create-home learny
USER learny

EXPOSE 8000

# Default command runs the API; the worker service overrides this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
