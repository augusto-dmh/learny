# byok-secrets-and-chains batch B — security lens

Lens: `security-best-practices`, with the FastAPI and React references, over the batch-B diff
(`origin/main..HEAD`) before the PR. Run by the builder on 2026-10-11, author = reviewer for
this pass. The fresh-context `pr-review` security lane runs after it.

## What was checked

| Rule (reference) | Surface | Result |
| --- | --- | --- |
| FASTAPI-AUTH-001: auth as a dependency on every protected route | the four `/api/me/provider-keys*` routes; the card routes now depend on `get_learner_credentials`, which depends on `get_authenticated_user` | pass: all four answer 401 without a session (C43) |
| FASTAPI-CSRF-001: cookie-authenticated writes are CSRF-protected | `PUT`, `POST …/test`, `DELETE` carry `enforce_csrf` at the router level, before the handler runs | pass: 403 and no row change without the token (C16) |
| FASTAPI-AUTHZ-001: object-level authorization | every repository statement filters by the caller's `user_id`; the path `provider` is checked against the offered set before any read; the worker resolves the pinned row by (owner of the job's source, provider) and compares ids, so a handle naming another learner's row id cannot use their key | pass |
| FASTAPI-VALID-001: schema-driven validation | the PUT body is parsed by hand on purpose: a pydantic model's 422 echoes `input`, which would reflect a key sent as a raw JSON string. The hand parser checks type, length 20-256, whitespace and the provider prefix, and answers fixed copy | deliberate deviation, recorded in plan Assumptions; C11 covers every rejection including the raw-string body |
| FASTAPI-RESP-001: explicit response models, no excess exposure | `ProviderKeyView` / `ProviderKeysView` / `KeyTestView`: provider, brand label, configured, last4, added date, bound profile ids/display names and mode flags. No model, host, kind, key env name or price | pass (C9, C18) |
| FASTAPI-SSRF-001: outbound requests to user-supplied URLs | the key test calls the host of an operator-declared profile; batch A's binding rule pins each provider to its own HTTPS host. The learner supplies only the key | pass: no user-controlled URL |
| FASTAPI-LIMITS-001 / abuse | PUT and test are rate limited per user and route template (a free key-checking oracle otherwise); DELETE is not (cheap, idempotent, CSRF-bound) | pass. Observation, not new: no request-body size cap exists in the app or the Caddyfile for any JSON route; verify at the edge (pre-existing, outside this diff) |
| FASTAPI-INJECT-001 | SQLAlchemy Core statements only | pass |
| Secrets never logged (§0) | log filter masks key shapes in message, args, extras, exception and stack text; both formatters mask the final line; the probe logs the exception class only; the worker logs no key and no credential field | pass (C33, C34 with negative control C35) |
| Secrets in queues | Celery args carry source, job, note ids and the handle (with `credential_id`), never a key | pass (C32, C34) |
| Key lifetime in memory | a replaced or deleted key's cached adapters are evicted at once in the serving process; other processes cannot reach theirs (fingerprint no longer live) and drop them at the 15-minute TTL | pass |
| React: secrets in client storage, XSS sinks | the key lives in component state only while typed; cleared on a confirmed save or cancel; never in `localStorage`, a URL or a log; the input is `type="password"`, `autoComplete="off"`; no `dangerouslySetInnerHTML` | pass (C38) |
| React: destructive action confirmation | inline confirmation, no browser dialog | pass (C40) |

## Findings

None that need a change before review. One pre-existing observation (no app or edge request-body
size limit for JSON routes) is outside this diff and left to the owner.
