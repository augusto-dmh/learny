# Contributing

Thanks for your interest! Learny is a personal project with a research-driven process — please open an issue to discuss before starting a large PR.

## Development setup

```bash
docker compose up --build        # full stack: http://localhost:3000 (app), :8000 (API)

# Backend (Python 3.13, uv)
cd backend
uv sync --all-extras
docker compose exec db psql -U learny -c 'CREATE DATABASE learny_test'
LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test uv run pytest
uv run ruff check .

# Frontend (Node 20)
cd frontend
npm ci
npx vitest run && npx tsc --noEmit && npm run build
```

## Conventions

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (`feat(scope): …`, `fix(scope): …`), imperative mood, no attribution trailers.
- **Architecture**: decisions live in [docs/adr/](docs/adr/); read the relevant ADR before proposing structural changes. Provider SDKs stay behind Learny-owned ports ([ADR-0007](docs/adr/0007-use-learny-owned-ports-for-ai-provider-integration.md)/[0009](docs/adr/0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md)).
- **Tests**: every behavior change ships with tests; CI must be green (`.github/workflows/ci.yml` mirrors the commands above).
