# App Instrumentation — Review Triage

PR #49. Six review lanes ran; Performance and Regression posted nothing (both clean, with
substantive positive findings). Seven inline findings and one consolidated requirements
summary were posted. Each was judged against the code as it stands, not against the
reviewer's authority.

**Outcome: 11 findings, 11 real, 11 accepted. 0 rejected.** Unusually high — the lanes
found gaps rather than opinions, and two of them (F4, F5) found real defects that the
cycle's own verification missed because they live *between* the phases rather than inside
one.

| # | Source | File:line | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- | --- |
| F1 | inline `3650150623` (tests) | `tests/test_worker_task_duration.py:160` | **Real** | Fix | `len(records) == 2` passes for two records about the *same* attempt. Independently corroborated: the Verifier's surviving mutant M21 is this exact hole. Two reviewers converging on one gap is the strongest signal in this review. |
| F2 | inline `3650150827` (tests) | `app/worker/instrumentation.py:123` | **Real** | Fix | `dispatch_uid` is documented as preventing double registration, but the installer is only ever called once, so deleting the argument leaves the suite green while every task would emit two duration records. A documented guard with no sensor. |
| F3 | inline `3650151022` (tests) | `tests/test_db_slow_query.py:271` | **Real** | Fix | The log-untruncated / recorder-capped asymmetry is deliberate and load-bearing, but is pinned only by a docs string match. A behavioural assertion makes the doc claim and the code fail together. |
| F4 | inline `3650152332` (architecture, ⚠️) | `app/worker/celery_app.py:45` | **Real** | Fix | The worker calls `get_engine()` from ~20 sites, so it installs the slow-query listener — but never calls `set_recorder`, so `LEARNY_INSTRUMENT_CAPACITY` and `LEARNY_SLOW_QUERY_STATEMENT_CHARS` are inert there while the runbook documents them as per-process. `LEARNY_SLOW_QUERY_MS` *is* honoured, which is what hides the asymmetry. This is the same class of gap Phase B found for the API — the cycle fixed one composition root and missed the other. |
| F5 | inline `3650152370` (security, Medium) | `app/main.py:67` | **Real** | Fix | The cycle claims production is safe *by construction*; in fact it is safe by a YAML omission. The prod `api` service also loads operator-authored `secrets/api.env`, and `Settings` reads `.env` — either can enable the flag with the whole suite green. The second gate does not narrow the blast radius: `get_authenticated_user` admits any registered account (no admin role), and the payload is process-wide SQL text plus the full route inventory. The app already knows `settings.environment`; a code-level cross-check converts a claim about a file into an invariant about the application. |
| F6 | inline `3650152460` (architecture, 💡) | `app/infrastructure/web/instrument.py:108` | **Real** | Fix | Every other handler in this layer declares collaborators via `Depends`; this one reaches into module state, putting the recorder out of reach of `app.dependency_overrides`. The producers genuinely have no injection point — a route does. Two lines. |
| F7 | inline `3650152496` (security, Low) | `app/infrastructure/web/middleware.py:168` | **Real** | Fix | `AuthenticateUser` deliberately maintains timing uniformity with a dummy hash, and that uniformity is imperfect (the credential lookup is an extra round trip only when the email exists). Shipping microsecond server-side timing to anonymous callers on exactly those endpoints hands away, jitter removed, a property the application layer spends code defending. The reviewer asked only that the exposure be a decision; the cheaper and more defensible decision is not to expose it. |
| R1 | summary (requirements) | `.specs/project/STATE.md` | **Real** | Fix | Handoff says "9 commits" (14), "1722 passed" (1736), and "NOT DONE HERE: the Verifier pass, PR publication" — all three now false. A handoff that contradicts the file next to it is worse than none. |
| R2 | summary (requirements) | `.specs/project/ROADMAP.md` | **Real** | Fix | Row reads `Done (PR pending)`; every other row carries its PR number. Applied at merge. |
| R3 | summary (requirements) | `spec.md` Goals / Success Criteria | **Real** | Fix | All checkboxes still `- [ ]` while the traceability table in the same file says 26/26 verified. Internally contradictory. |
| R5 | summary (requirements) | PR #49 body | **Real** | Fix | The body says "all 26 acceptance criteria" without disclosing that two of them were amended mid-cycle. The `.specs/` artifacts are explicit about it; the public record should be too. |

## Not actioned

- **`# pragma: no cover` on recorder `except` branches is cosmetically inaccurate** (Regression lane, deliberately not posted). True, but inert: there is no coverage gate in `pyproject.toml` or CI. Noted, not fixed — churn without a consequence.
- **Recorder `capacity <= 0` / `statement_max_chars <= 0` degenerate behaviour, and the unused `limit` arguments** (Test Coverage lane, judged below its own bar). Agreed: documented behaviour with no production caller.

## Decisions taken while triaging

### AD-181 — The dev surface is refused in production by the application, not by a config file

F5's fix. `create_app` mounts the surface only when the flag is set **and** the process is
not running as production, logging a warning when a set flag is refused so a
misconfiguration is visible rather than silent. Collection is untouched (AD-173 stands):
what is refused is exposure. Production diagnosis remains the structured log, which
carries both durations and every slow statement.

*Rejected:* trusting the compose omission (the reviewer's point stands — `secrets/api.env`
and `.env` both bypass it); and requiring an admin role (there is none, and inventing one
is a product decision far outside this cycle).

### AD-182 — `Server-Timing` is emitted only when the instrument is enabled

F7's fix. This also removes the asymmetry the reviewer identified: the surface was
double-gated while the header — the one part that leaves the process — was ungated. Both
are now the same switch. The access record keeps `response_start_ms` unconditionally, so
nothing about diagnosis is lost; only the anonymous oracle is.

*Rejected:* excluding `/api/auth/*` by path (a denylist rots, and new anonymous endpoints
would silently rejoin the oracle); suppressing only for unauthenticated requests (would
strip the header from `/healthz` and from ordinary unauthenticated dev probing, which is
where the header is actually read).

*Consequence, stated plainly:* production browsers no longer see a server-timing split.
That is consistent with an instrument the RFC scopes as development-first, and with AD-181
above — in production the log is the instrument.

### Spec amendments required by the two decisions

OBS-08 and OBS-19 are amended in `spec.md` to state the gating, with the reasoning
recorded there rather than silently rewritten. The Verifier's 26/26 verdict predates these
amendments; the fix commits carry their own sensors, and the amended criteria are listed
in the fix report.
