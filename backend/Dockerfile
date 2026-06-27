# Learny backend image — shared by the `api` and `worker` services.
FROM python:3.13-slim

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

# Install dependencies first (cached layer) using the committed lockfile.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra dev

# Application source.
COPY . .
RUN uv sync --frozen --extra dev

EXPOSE 8000

# Default command runs the API; the worker service overrides this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
