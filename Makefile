# Canonical verification vocabulary — same names locally, in agent sessions, and in docs.

.PHONY: infra test test-backend test-frontend lint lint-backend lint-frontend fitness check

infra: ## Start the local services DB/golden tests depend on
	docker compose up -d db minio redis

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm test

test: test-backend test-frontend

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check .

# CI parity: the frontend static gate is tsc --noEmit (no ESLint config exists; `next lint` prompts interactively).
lint-frontend:
	cd frontend && npx tsc --noEmit

fitness: ## Architecture boundaries (provider-SDK isolation, layering)
	python3 backend/scripts/check_boundaries.py

lint: lint-backend lint-frontend fitness

check: lint test
