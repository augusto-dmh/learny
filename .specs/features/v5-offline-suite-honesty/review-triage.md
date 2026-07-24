# Review triage — v5-offline-suite-honesty (PR #47)

Every review comment checked against the actual code: real or not, act or not, why. Comments are deleted at cleanup, so this is the surviving record.

| # | Source comment | Location | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | Inline `3646937342` (tests lane, ⚠️) | `backend/tests/conftest.py:62` → real target `backend/tests/test_config.py` | **REAL** | **FIX** | The autouse `_force_local_providers` pin injects `LEARNY_*_PROVIDER=local` into `os.environ`. `Settings(_env_file=None)` disables only the dotenv source, **not** the env source — empirically confirmed: with `LEARNY_EMBEDDING_PROVIDER=openai` in `os.environ`, `Settings(_env_file=None).embedding_provider == "openai"`. So `test_embedding_settings_defaults` / `test_generation_settings_defaults` now assert `local` because the pin sets it, not because the field default is `local` — a code-default regression (changing `embedding_provider: str = "local"`) would no longer be caught. FR-5/AC-4 said these "pass unchanged", but passing is not enough; they must still *discriminate*. Fix restores the sensor without weakening the pin. |
| 2 | PR-level `5072362686` (requirements review) | — | N/A (positive) | none | All requirements/acceptance criteria verified satisfied against the diff. Confirmation only. |
| 3 | PR-level `5072414630` (review summary) | — | N/A (summary artifact) | none | Consolidated review summary. No action. |

## Fix (finding 1)

In `backend/tests/test_config.py`, make the two affected provider-default tests observe the true field default independent of the suite-wide pin:
- `test_embedding_settings_defaults`: add `monkeypatch` param, `monkeypatch.delenv("LEARNY_EMBEDDING_PROVIDER", raising=False)` before `Settings(_env_file=None)`.
- `test_generation_settings_defaults`: same with `LEARNY_GENERATION_PROVIDER`.

Only these two are affected — the pin touches only those two vars; `test_quiz_settings_defaults` / `test_pdf_ocr_settings_defaults` / etc. assert unrelated fields. The pin and its own tests are unchanged; this reinstates the code-default regression guard.
