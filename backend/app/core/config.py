"""Environment-based application configuration.

Secrets and connection strings come from the environment only (NFR-SEC-003);
nothing here is committed with real values. See `.env.example` for the contract.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment variables.

    Defaults are safe placeholders for local boot; production values are injected
    via the environment (Docker Compose / VPS).
    """

    model_config = SettingsConfigDict(
        env_prefix="LEARNY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "learny-backend"
    environment: str = "local"
    debug: bool = False

    # NOTE: the log format is intentionally NOT a Settings field. It is read
    # directly from ``LEARNY_LOG_FORMAT`` in ``app.core.logging.configure_logging``
    # (single source of truth) so bootstrap logging setup does not prime the
    # ``get_settings`` lru-cache, which Alembic's ``env.py`` later reads.

    # Database (used by /readyz and, later, repositories + migrations)
    database_url: str = "postgresql+psycopg://learny:learny@localhost:5432/learny"

    # Redis / Celery (worker wiring; ingestion tasks land in a later cycle)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    def broker_url(self) -> str:
        """Effective Celery broker URL (falls back to ``redis_url``)."""
        return self.celery_broker_url or self.redis_url

    def result_backend(self) -> str:
        """Effective Celery result backend URL (falls back to ``redis_url``)."""
        return self.celery_result_backend or self.redis_url

    # Session cookie attributes (NFR-SEC-002) — wired fully in Phase C.
    session_cookie_name: str = "learny_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    session_cookie_path: str = "/"

    # CSRF (AD-007) — comma-separated list of trusted browser origins for the
    # Origin/Referer check on state-changing requests. Empty disables the host
    # check (header-token validation still applies); set explicitly in prod.
    csrf_trusted_origins: str = "http://localhost:3000"

    def trusted_origins(self) -> tuple[str, ...]:
        """Parsed, normalized tuple of trusted origins (scheme://host[:port])."""
        return tuple(
            o.strip().rstrip("/")
            for o in self.csrf_trusted_origins.split(",")
            if o.strip()
        )

    # Object storage (S3-compatible; MinIO locally, AD-011). Secrets env-only.
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "learny"
    storage_secret_key: str = "learny-dev-secret"
    storage_bucket: str = "learny-sources"
    storage_region: str = "us-east-1"

    # Upload limits (AD-009) — cap the bytes buffered through the request, per
    # format. The web handler reads at most ``max(caps) + 1`` and validation
    # enforces the per-format cap (ING-09/ING-20): EPUB stays at 50 MiB; PDFs are
    # larger on average (born-digital books with images), so the PDF cap is 100 MiB.
    epub_max_bytes: int = 52428800  # 50 MiB
    pdf_max_bytes: int = 104857600  # 100 MiB

    # Ingestion safety — cap the summed *uncompressed* size an EPUB archive may
    # declare before parsing; the upload cap above only bounds compressed bytes,
    # so a crafted archive could otherwise inflate far past it in worker memory.
    epub_max_uncompressed_bytes: int = 524288000  # 500 MiB

    # Corpus chunking (A-5) — max characters per retrieval chunk before packing
    # starts a new one; oversized single blocks split at sentence boundaries.
    chunk_max_chars: int = 2000

    # Embeddings (ADR-0007/0019) — the provider/model lives only in the adapter;
    # these knobs stay LEARNY_-prefixed and never hard-coded in query/repository
    # code. ``embedding_dim`` is the single source of truth for the vector width: the
    # deterministic adapter derives its ``local-deterministic@{dim}`` identity from
    # it, the OpenAI adapter sends it as the ``dimensions`` request param, and the
    # migration's ``vector(1536)`` column literal must match it (A-1).
    # ``embedding_provider`` selects the adapter at the composition root (``local``
    # default → deterministic, network-free; ``openai`` → the OpenAI adapter built
    # from the key/model/dim below). ``embedding_model`` names the *provider* model —
    # the deterministic adapter ignores it and reports its own identity, so the
    # default is unaffected.
    embedding_dim: int = 1536
    embedding_provider: str = "local"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-large"
    embedding_batch_size: int = 128

    # Hybrid retrieval tuning (ADR-0006) — candidate limits, RRF constant, default
    # and max top-k, and the pgvector HNSW query-time recall knob. All infrastructure
    # tuning, not domain concepts (A-9).
    retrieval_semantic_limit: int = 50
    retrieval_lexical_limit: int = 50
    retrieval_rrf_k: int = 60
    retrieval_top_k: int = 10
    retrieval_max_top_k: int = 50
    hnsw_ef_search: int = 100

    # Cited Q&A (Phase 7) — question length bound enforced by the web validator
    # and the server-controlled evidence budget. ``qa_evidence_top_k`` is the
    # ``top_k`` handed to Phase-6 retrieval; keep it ≤ ``retrieval_max_top_k``.
    qa_question_max_chars: int = 2000
    qa_evidence_top_k: int = 8

    # Teaching sessions (Phase 8) — message length bound enforced by the web
    # validator, the server-controlled evidence budget handed to scoped retrieval
    # (keep ≤ ``retrieval_max_top_k``), and the number of prior turns passed to the
    # generation port as bounded context (TEACH-12).
    teaching_message_max_chars: int = 2000
    teaching_evidence_top_k: int = 8
    teaching_history_turns: int = 6

    # Generation (ADR-0020) — the provider SDK and model names live only in the
    # answer/teaching adapters; these knobs stay LEARNY_-prefixed and never
    # hard-coded in application/domain code. ``generation_provider`` selects the
    # adapter at the composition root (``local`` default → deterministic,
    # network-free; ``anthropic`` → the Claude adapters built from the key/model/
    # max-tokens below), so CI and local development stay offline and key-free.
    # ``anthropic_api_key`` is an env-only secret. ``judge_model`` and
    # ``eval_max_cases`` bound the offline-optional evaluation harness.
    generation_provider: str = "local"
    anthropic_api_key: str = ""
    generation_model: str = "claude-sonnet-4-6"
    generation_max_tokens: int = 1024
    judge_model: str = "claude-haiku-4-5"
    eval_max_cases: int = 50

    # Active recall — quiz deck generation (RFC-002 Cycle E). The provider SDK and
    # model name live only in the quiz adapter; these knobs stay LEARNY_-prefixed and
    # never hard-coded in application/domain code. ``quiz_model`` names the batched
    # generation model (deterministic ``local`` adapter ignores it). The item/section
    # caps and character floor bound deck density; ``quiz_dedup_threshold`` is the
    # cosine-similarity ceiling above which a candidate is a near-duplicate; the batch
    # timeout/poll-interval bound the Anthropic Message Batches polling loop.
    quiz_model: str = "claude-haiku-4-5"
    quiz_max_items_per_section: int = 6
    quiz_min_section_chars: int = 200
    quiz_dedup_threshold: float = 0.90
    quiz_batch_timeout_s: int = 3600
    quiz_batch_poll_interval_s: int = 30

    # Active recall — FSRS scheduling (RFC-002 Cycle E). ``fsrs_desired_retention`` is
    # the FSRS-6 target recall probability; ``fsrs_fuzzing`` spreads due dates to avoid
    # review pile-ups (disabled in tests for deterministic interval assertions).
    fsrs_desired_retention: float = 0.9
    fsrs_fuzzing: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance loaded from the environment."""
    return Settings()
