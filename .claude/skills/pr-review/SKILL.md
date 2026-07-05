---
name: pr-review
description: 'Multi-agent PR reviewer for Learny. Use when — and only when — explicitly asked to review a pull request: "review PR #N", "review this PR", "code review this PR", "check this pull request". Not for automatic use during coding, feature implementation, or finalizing/publishing (use learny-finalize), nor for general questions.'
license: CC-BY-4.0
metadata:
  author: Learny contributors
  version: 1.0.0
---

# PR Review — Orchestration Protocol

Coordinates 6 specialized subagents (via the Task tool) then consolidates findings into a unified summary. Each subagent loads the relevant existing Learny docs (ADRs, `.specs/`, `CONVENTIONS.md`, `modular-design-principles`) — this skill does not duplicate them.

Learny stack (ADR-004): Python/FastAPI backend, React/Next.js frontend, PostgreSQL + pgvector, SQLAlchemy 2.x + Alembic, Redis + Celery workers, S3-compatible object storage. Auth is backend-owned HTTP-only cookies (ADR-015) reached through a thin same-origin Next.js proxy (ADR-017). Provider SDKs sit behind Learny-owned ports/adapters (ADR-007/009).

## Step 1: Initialize

1. Get PR number from context or ask the user.
2. Identify repo: `gh repo view --json nameWithOwner -q .nameWithOwner`
3. Fetch diff: `gh pr diff {PR_NUMBER}`
4. Load existing inline comments: `gh api repos/{REPO}/pulls/{PR_NUMBER}/comments` — build a set of `{path, line}` pairs to avoid reposting.
5. Read PR intent: `gh pr view {PR_NUMBER} --json title,body,headRefName`
6. Derive the feature slug from the branch name: strip the Conventional Commit prefix (`feat/`, `fix/`, `docs/`, …) and any leading issue number, leaving a kebab summary (e.g. `feat/scaffold-and-identity` → `scaffold-and-identity`). This slug is the fuzzy key for locating the matching spec under `.specs/features/`.

## Step 2: Launch Subagents in Parallel

Send **one message** with **six Task tool calls** — all launched simultaneously. Pass REPO, PR_NUMBER, the diff, existing comment locations, the PR intent, and the feature slug to each subagent prompt. After all complete, run Step 3.

---

## Severity Labels (all subagents use these)

- 🚨 Critical — bugs or logic errors that will cause failures
- 🔒 Security — security vulnerabilities or data exposure
- ⚡ Performance — significant performance concerns
- ⚠️ Warning — code smells or maintainability issues
- 💡 Suggestion — optional improvements

---

## Universal Rules (every subagent must follow)

1. **Comment allowlist:** Only post inline comments on lines in the diff starting with `+` (excluding `+++`).
2. **Skip duplicates:** If `{path, line}` within ±3 lines already has a comment, skip.
3. **Mark resolved:** Reply `[RESOLVED] This appears resolved by the recent changes.` on existing comments where the issue is fixed.
4. **False positive guard:** Only report findings with ≥80% confidence. Skip when uncertain.
5. **Positive highlight:** Include at least one well-done aspect of the change before listing issues.
6. **Tone:** Specific, actionable, collegial. Explain WHY something is a problem, and cite the ADR / `CONVENTIONS.md` / principle that grounds it.
7. **Never** approve, request-changes, or modify files. Use `--comment` only.
8. **Marker:** Start every inline comment body with `<!-- learny-review:{type} -->` (invisible in rendered view, used by the consolidation subagent).
9. **No AI attribution:** Never add tooling/authorship attribution (`Co-Authored-By`, "Generated with", model names) to any comment body — consistent with `learny-finalize` hygiene rules.
10. **Multiline bodies from a file:** Write the comment body to a temp file, then post with `gh pr comment --body-file <file>` or `gh api ... -F body=@<file>`. Never use `gh api -f body=@<file>` — lowercase `-f` does not expand `@`, so the comment is published as the literal file path instead of its content.
11. **PR-level comments must be issue comments, never reviews.** Post every PR-level comment (requirements summary, consolidation summary) with `gh pr comment` / `gh api .../issues/comments`, not `gh pr review`. Submitted reviews cannot be deleted, dismissed, or blanked via the API, so they leave permanent artifacts that break teardown (Step 4).

---

## Structural Compliance Checklist

For the full boundary rules, see `.claude/skills/modular-design-principles/SKILL.md` and `references/principles.md`. For repo tooling and layering conventions, see `.specs/codebase/CONVENTIONS.md`. Ground each item in ADR-004/007/009 and the CLAUDE.md durable direction.

- [ ] **Layering (ADR-007/009)** — backend code respects `domain / application / infrastructure / core`. `domain` imports nothing from `infrastructure`, FastAPI, SQLAlchemy, Celery, or provider SDKs; adapters depend inward only.
- [ ] **Composition root** — FastAPI wiring lives in the `infrastructure/web` (HTTP) composition root; route handlers stay thin and delegate to application/domain.
- [ ] **Ports & adapters (ADR-007/009)** — provider SDKs (OpenAI, Anthropic, object storage, parsing, embeddings) sit behind Learny-owned ports. No SDK objects, model names, or provider citation formats leak into core domain logic.
- [ ] **Proxy boundary (ADR-017)** — `frontend/app/api/*` (Next.js) is a thin same-origin proxy; it owns no domain logic, authorization, or product rules. FastAPI stays authoritative.
- [ ] **Auth boundary (ADR-015)** — sessions use secure HTTP-only cookies; no bearer tokens in browser-accessible storage.
- [ ] **Ownership & authorization** — sources, corpus records, and teaching sessions enforce per-user ownership (CLAUDE.md); no query returns another user's resources.
- [ ] **Workers, not request handlers (ADR-005)** — long-running ingestion, corpus generation, embedding, indexing, and evaluation run in Celery workers, not inside HTTP request handlers.
- [ ] **Module boundaries** — new code lands in a cohesive bounded context with an explicit contract; no cross-context reach-in that violates `modular-design-principles`.

---

## Subagent 1: Security

**Marker:** `<!-- learny-review:security -->`

Load `.specs/codebase/CONVENTIONS.md` and skim ADR-012 (email/password accounts), ADR-013 (object storage), ADR-015 (cookie auth), ADR-017 (proxy boundary). Review the PR diff for: hardcoded secrets or API keys (must be env-only, `LEARNY_`-prefixed via pydantic-settings), missing FastAPI auth dependencies / ownership guards on user-owned resources, session cookies missing `HttpOnly` / `Secure` / `SameSite`, missing or weak CSRF handling across the same-origin proxy, PII or secrets in logs, provider keys or SDK clients exported across module boundaries, sensitive fields leaking into response models, raw SQL string concatenation instead of parameterized SQLAlchemy, unvalidated file uploads / object keys, and overly permissive CORS.

**Second pass:** Re-read the full diff from top to bottom. List every file or hunk you did not comment on. For each uncovered file, ask: "Does this file violate any security rule in my scope?" Only skip a file when you can explicitly state why it is clean.

**Comment format:**
```
<!-- learny-review:security -->
🔒 Security — [Short title]
[What the issue is and why it matters]
**Recommendation:** [Specific fix]
```

---

## Subagent 2: Requirements & Definition of Done

**Marker:** `<!-- learny-review:requirements -->`
**Posts:** One PR-level summary comment only — no inline comments.

Use a two-track approach to find requirements. Run both tracks; use whichever yields content.

### Track A — Feature Spec (`.specs/features/`)

1. Use the feature slug derived in Step 1. Look for `.specs/features/{slug}/` — if an exact match is absent, fuzzy-match the slug against directory stems under `.specs/features/`, and also check the PR title/body for an explicit spec path or markdown link.
2. For the matched feature, read `spec.md`, `tasks.md`, and `validation.md` with `cat {path}`.
3. Extract: functional requirements (`FR-*` IDs), acceptance criteria, the task checklist, and stated goals / out-of-scope items.

### Track B — Accepted Decisions (ADR / TDD)

1. Scan the PR title, body, and matched spec for referenced decisions (`ADR-0NNN`, `TDD-0NNN`) under `docs/adr/` and `docs/tdd/`.
2. Read each referenced doc and extract the constraints the PR must honor (e.g. ADR-015 cookie auth, ADR-017 proxy, ADR-007/009 ports).

### Resolution Logic

| Tracks with content | Action |
|---|---|
| Both A and B | Merge requirements from both; note the source of each item (spec FR-ID or ADR number) |
| A only | Use the feature spec requirements |
| B only | Use the ADR/TDD constraints |
| Neither | Post: "⚠️ No matching `.specs/features/` spec or referenced ADR/TDD found — requirements verification skipped." and stop |

Compare the merged requirements against the PR diff and post the summary **idempotently as an issue comment** (never a review — see Step 3.8). Look for an existing PR comment containing `<!-- learny-review:requirements -->`: if one exists, update it in place with `gh api -X PATCH repos/{REPO}/issues/comments/{COMMENT_ID} -F body=@<tempfile>`; otherwise create it with `gh pr comment {PR_NUMBER} --body-file <tempfile>`. This keeps the comment editable and removable, and prevents duplicate requirements comments across re-runs.

**Second pass:** After drafting the summary, re-read the requirements list one item at a time and ask: "Did I evaluate this criterion against the diff?" For any item not yet assessed, find the relevant section of the diff and explicitly mark it ✅, ❌, or 🔲.

**Summary format:**
```markdown
<!-- learny-review:requirements -->
## 📋 Requirements Review

**Sources:** {e.g. "Spec: .specs/features/scaffold-and-identity" · "ADR-015, ADR-017" · "Both"}

### ✅ Implemented
### ❌ Missing or Incomplete
### 🔲 Definition of Done
- [x] covered  - [ ] not covered
### 💬 Notes
```

---

## Subagent 3: Test Coverage

**Marker:** `<!-- learny-review:tests -->`

Load the **Test runner** sections of `.specs/codebase/CONVENTIONS.md` and skim ADR-016 (golden fixtures for MVP evaluation). Learny testing: backend uses `pytest` (+ `pytest-asyncio`, `httpx` `TestClient`) under `apps/api/tests` (run `uv run pytest`); frontend uses `vitest` (`npm test`); ingestion, retrieval, and citation paths are validated with golden fixtures before Ragas/dashboards.

Review the PR diff for: new or changed FastAPI endpoints, application services, or Celery tasks with no covering test (🚨 Critical for new endpoints/handlers); missing golden-fixture coverage on new ingestion/retrieval/citation logic (ADR-016); test-quality issues (no assertion on response body, hardcoded IDs, missing DB/cleanup isolation, no ownership/authorization case); and anti-patterns (asserting only status codes, no error/edge case, brittle snapshot with no meaning).

**Second pass:** Re-read the full diff from top to bottom. List every new or modified endpoint, service method, and Celery task you did not comment on. For each uncovered handler, ask: "Is there a test covering the happy path and at least one error/authorization case?" Only skip a handler when you can explicitly state why coverage already exists or is not applicable.

**Comment format:**
```
<!-- learny-review:tests -->
[🚨/⚠️/💡] — [Short title]
[Description of the gap or anti-pattern]
**Recommendation:** [pytest/vitest pattern or golden fixture to add, per CONVENTIONS.md / ADR-016]
```

---

## Subagent 4: Architecture & Coding Patterns

**Marker:** `<!-- learny-review:architecture -->`

### Phase 0 — Load all reference documents

Load every document below before touching the diff. Do not skip any.

1. `.specs/codebase/CONVENTIONS.md`
2. `.claude/skills/modular-design-principles/SKILL.md`
3. `.claude/skills/modular-design-principles/references/principles.md`
4. `docs/adr/0004-python-fastapi-react-nextjs-postgresql-stack.md`
5. `docs/adr/0007-use-learny-owned-ports-for-ai-provider-integration.md`
6. `docs/adr/0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md`
7. `docs/adr/0017-use-thin-nextjs-same-origin-api-proxy-to-fastapi.md`

Then scan the diff for directory structure: note which layers (`domain`, `application`, `infrastructure`, `core`) and which side (backend `apps/api` / `frontend` proxy) the changed paths touch.

### Phase 1 — Extract the rule list from the loaded documents

Do not use a hardcoded list. After loading Phase 0, scan each document and extract every explicit rule into a single numbered checklist:

- **`principles.md`** — extract every agent rule / ✅ / ❌ item from each principle's rules block.
- **`modular-design-principles/SKILL.md`** — extract the compliance-review signals and violation patterns.
- **`CONVENTIONS.md`** — extract every locked convention (layering, config via `LEARNY_`-prefixed pydantic-settings, SQLAlchemy 2.x + Alembic, ruff line-length 100 / rule sets `E,F,I,UP,B`, proxy-owns-no-domain-logic, one atomic commit per task).
- **ADR-004/007/009/017** — extract each binding constraint (stack choices, ports/adapters, no SDK leakage into domain, thin same-origin proxy).

Number the combined list sequentially from 1. This is your evaluation matrix for Phase 2. Do not add rules absent from the documents, and do not omit any you find.

### Phase 2 — Evaluate the matrix

Work through the diff **one file at a time**. For each changed file:

- For each rule, decide **PASS** / **VIOLATION** / **N/A**.
- N/A is only valid when the rule is structurally inapplicable to the file type (e.g. a Pydantic schema file cannot violate a Celery-worker rule; an Alembic migration cannot violate route-handler leanness).
- For every VIOLATION: post an inline comment on the exact `+` line that is the evidence. Include the rule number and source document.

**Second pass:** After completing the matrix for all files, re-read the full diff top to bottom. List every file or hunk you did not evaluate. For any uncovered file, run the matrix again. Only skip a file when you can explicitly state which rules are N/A and why.

**Comment format:**
```
<!-- learny-review:architecture -->
[🚨/⚠️/💡] — [Short title]
Rule: [Rule number + source, e.g. "Rule 8 — principles.md P4 (state isolation)" or "ADR-007 ports"]
[What in the diff violates it — quote the offending line]
**Recommendation:** [Exact fix, code snippet if < 6 lines]
```

---

## Subagent 5: Regression & Hallucination Detection

**Marker:** `<!-- learny-review:regression -->`

Review the PR diff for changes unrelated to the PR's stated purpose, or signs of AI-generated artifacts. Look for: deleted code unrelated to the change (🚨 Critical), phantom imports referencing non-existent modules/symbols (🚨 Critical), function/method calls with wrong signatures (🚨 Critical), `TODO`/`FIXME`/`pass`-stubs left in production code, `# type: ignore` or `as any` hiding real type errors, duplicate logic that already exists in the module, weakened validation (Pydantic model constraints removed, auth checks loosened), silently swallowed exceptions in request handlers or Celery tasks, weakened test assertions, and dead code that is never called.

**Second pass:** Re-read the full diff from top to bottom. List every file or hunk you did not comment on. For each uncovered file, ask: "Does this file contain any unrelated deletions, phantom imports, duplicate logic, or weakened assertions?" Only skip a file when you can explicitly state why none of those categories apply.

**Comment format:**
```
<!-- learny-review:regression -->
[🚨/⚠️/💡] — [Short title]
Type: [unrelated-deletion | phantom-import | hallucination | duplicate | regression | dead-code]
[Specific description with quoted evidence from the diff]
**Recommendation:** [Exact fix]
```

---

## Subagent 6: Performance

**Marker:** `<!-- learny-review:performance -->`

Only flag issues **clearly visible in the diff** — no speculation. Learny persistence is SQLAlchemy 2.x over PostgreSQL + pgvector, with Celery workers for heavy work. Look for: N+1 query patterns (a query or lazy-loaded relationship accessed inside a loop — use `selectinload`/`joinedload`), unbounded queries with no `limit`/pagination, sequential `await` on independent async operations that could use `asyncio.gather`, blocking/synchronous I/O (network, disk, sync DB driver) inside an `async` request handler, missing transaction boundary around multiple writes, heavy ingestion/embedding/indexing work executed inside an HTTP request handler instead of a Celery task (ADR-005), and inefficient pgvector usage (missing index, fetching full vectors when not needed).

**Second pass:** Re-read the full diff from top to bottom. List every service method, query, loop, and async handler you did not comment on. For each uncovered block, ask: "Does this contain a clearly visible performance issue?" Only skip a block when you can explicitly state why none of the patterns above apply.

**Comment format:**
```
<!-- learny-review:performance -->
⚡ Performance — [Short title]
[Description with estimated impact, e.g. "O(N) queries per request"]
**Recommendation:** [Fix with short code sketch if < 6 lines]
```

---

## Step 3: Consolidation

After all 6 subagents complete, spawn one more subagent via Task tool to consolidate:

1. `gh api repos/{REPO}/pulls/{PR_NUMBER}/comments` — fetch all inline comments.
2. Filter to those starting with `<!-- learny-review:` and parse the type from the marker.
3. Fetch PR-level comments for the `<!-- learny-review:requirements -->` summary.
4. Group by severity: 🔒 Security → 🚨 Critical → ⚡ Performance → ⚠️ Warning → 💡 Suggestion.
5. Deduplicate findings at the same `{path, line}` (±3 lines) — note both agents in the entry.
6. Collect one positive highlight per agent.
7. **Gap detection:** Run `gh pr diff {PR_NUMBER} --name-only` to get the full list of changed files. Cross-reference against all collected inline comment paths. For any file with zero inline comments from any subagent, add it to a `### 🔍 Files With No Inline Comments` section. Omit a file from this section only if it is a config/lock file (`*.json`, `*.yaml`, `*.toml`, `*.lock`, `uv.lock`, `package-lock.json`, `.env.example`) or a pure schema/migration file with no logic (an Alembic migration, a bare Pydantic model).
8. Post the summary **as an issue comment, never as a review**. A submitted `gh pr review` (even `--comment`) creates a review that GitHub's API cannot delete, dismiss, or blank — it is permanent. An issue comment stays editable and removable. Post idempotently by marker: search existing PR comments for `<!-- learny-review:summary -->`; if found, update it in place with `gh api -X PATCH repos/{REPO}/issues/comments/{COMMENT_ID} -F body=@<tempfile>`; otherwise create it with `gh pr comment {PR_NUMBER} --body-file <tempfile>`. This keeps the summary removable and avoids duplicate summaries when the review is re-run.

**Summary format:**
```markdown
## 🤖 Learny AI Review Summary

| | |
|---|---|
| **Subagents invoked** | {N} of 6 (Security · Requirements (Spec + ADR) · Test Coverage · Architecture · Regression · Performance) |
| **Skills loaded** | `.claude/skills/pr-review/SKILL.md`, `.claude/skills/modular-design-principles/SKILL.md` |
| **Docs loaded** | `.specs/codebase/CONVENTIONS.md`, `.specs/features/{slug}/*`, `docs/adr/*`, `docs/tdd/0001-mvp-architecture.md` |
| **Findings** | {N} across {M} files |

---

### 🔒 Security ({N})
- [`path/file.py:L42`] Finding title

### 🚨 Critical ({N})
### ⚡ Performance ({N})
### ⚠️ Warnings ({N})
### 💡 Suggestions ({N})

---
### 🔍 Files With No Inline Comments
- `path/to/file.py` — no findings from any subagent (verify manually or re-run targeted review)

_(Omit this section if all logic files received at least one comment.)_

---
### ✅ Highlights
- [One positive highlight per agent]

---
> See inline comments for details and recommendations.
```

If no findings across all agents: post `✅ No issues found across all review dimensions.` but still include the metadata table.

---

## Step 4: Teardown / re-run

The review's artifacts must be fully removable so a re-run never duplicates them and the author can clear the PR. All review output is therefore inline comments and issue comments only (Step 3.8) — never a submitted review.

**Resolve a thread after its finding is fixed.** Reply, then resolve, via GraphQL:

```bash
# Reply in the thread
gh api graphql -f query='mutation($t:ID!,$b:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$t,body:$b}){comment{id}}}' -f t="$THREAD_ID" -f b="Fixed in <hash> — <one line>."
# Resolve it
gh api graphql -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' -f t="$THREAD_ID"
```

Thread IDs come from `repository.pullRequest.reviewThreads` (each node has `id`, `isResolved`, and its `comments`).

**Remove all bot comments.** Everything the review posts is deletable:

```bash
# Inline review comments (findings + replies)
for id in $(gh api repos/{REPO}/pulls/{PR_NUMBER}/comments --paginate --jq '.[].id'); do
  gh api -X DELETE repos/{REPO}/pulls/comments/$id
done
# PR-level issue comments (requirements + summary) — filter by marker if selective
for id in $(gh api repos/{REPO}/issues/{PR_NUMBER}/comments --paginate --jq '.[].id'); do
  gh api -X DELETE repos/{REPO}/issues/comments/$id
done
```

**Do not create what you cannot remove.** There is no API to delete or dismiss a `COMMENTED` review, and an empty review body is rejected (HTTP 422). That is why summaries are issue comments — keep it that way.
