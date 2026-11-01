# Hosted BYOK security review checklist

The go-live procedure an operator completes before offering learner provider
keys on a hosted instance. It is the gate behind `LEARNY_HOSTED_BYOK_ENABLED`:
nothing in the code can tell a public host from a private VPS (ADR-0033
point 11's own conclusion, carried into ADR-0035), so the review is the
mechanism. On a self-host none of this is required — learner keys serve as
soon as the KEK and a bound profile exist.

The policy this checklist gates is recorded in
[ADR-0035: Learner keys on a hosted instance](../adr/0035-learner-keys-on-a-hosted-instance.md).
The research underneath it — provider terms, the `base_url` CVE record, the
allow-list and ceiling recommendations — is
`docs/research/2026-09-30/byok-and-business-models.md`.

Work through every section in order. The go/no-go line is at the end; a single
unchecked box is a no-go.

---

## 1. Key-encryption key (KEK) custody

Learner keys are sealed at rest with envelope encryption (ADR-0033): each key
under its own data key, wrapped by the KEK in `LEARNY_SECRETS_KEK`. Whoever
holds the KEK can unwrap every stored learner key, so its custody is
load-bearing.

- [ ] Generate the KEK off-box, never on the server that stores it:
      `python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"`
- [ ] Record the generation date and the operator who generated it in the
      instance's secret register (wherever passwords and database credentials
      are already tracked).
- [ ] Back the KEK up to storage at least as strong as the database backups —
      losing it makes every stored learner key unrecoverable and every learner
      must re-enter theirs. Database backups alone do not expose keys (the
      sealed values are useless without the KEK); the backup must not become
      the weaker channel either.
- [ ] Confirm the API **and** the worker containers both receive the KEK — a
      worker without it fails every deck settle honestly, but the outage is
      avoidable.
- [ ] Plan rotation before go-live, not after: `LEARNY_SECRETS_KEK_PREVIOUS`
      accepts retired KEKs and `python -m app.cli.rotate_secrets_kek` re-wraps
      every stored key. A malformed KEK value fails startup naming the
      variable, never the value.

## 2. Declaring the instance hosted

Two flags, deliberately separate:

- `LEARNY_HOSTED_INSTANCE=true` — the declaration. It changes no behavior by
  itself; it is what the disclosure, the checklist gate and the codebase read
  when they say "this instance is hosted".
- `LEARNY_HOSTED_BYOK_ENABLED=true` — the opt-in. It does nothing without the
  declaration above (a self-host ignores it entirely), and with the
  declaration it turns the keys surface on exactly as a self-host's.

- [ ] Set `LEARNY_HOSTED_INSTANCE=true` on the API **and** the worker (the
      hosted gate is one gate for both assemblies; a worker that disagrees
      with the API would resolve key access differently).
- [ ] Leave `LEARNY_HOSTED_BYOK_ENABLED` unset until every box below is
      checked. While it is unset, the keys surface answers `enabled: false`
      and reads no credential row at all — verify that with a session cookie
      against `GET /api/me/provider-keys` before going further.
- [ ] Confirm the compose files / environment do not leak the flags: the
      declaration is not secret (the disclosure renders from it), but it
      should be set deliberately, not inherited from a staging overlay.

## 3. Provider-terms review

Learner keys run under the learner's own provider agreement; the operator is
the custodian of the key, not a party to it. Re-verify each row's terms at
review time — providers change them on their own schedule — and record the
date and source next to each verdict.

- [ ] **Anthropic** — API keys billed to the key owner are the documented
      pattern for third-party tools. Confirm the current terms still permit
      usage "billed to the key owner" when the key is entrusted to a hosted
      third party's server.
- [ ] **OpenAI** — the Services Agreement forbids buying, selling or
      transferring API keys to or with a third party. Whether a learner
      entrusting a key to a hosted instance's server engages that
      **key-transfer clause is unresolved** — it is untested, and it is not an
      issue on a self-host, where the learner is the operator. Record the
      current agreement version reviewed, and decide (with counsel, not from
      this checklist) whether the instance may offer OpenAI keys at all. This
      is the one provider whose review can end in "not offered on this
      instance".
- [ ] **Google Gemini** — the unpaid tier's terms train on the content sent
      with the key. The account surface discloses this on the Gemini row
      (the privacy badges ship from the 2026-09-30 terms research, dated in
      the ADR). Confirm the badge copy still matches the live terms, and
      accept that a hosted Gemini offer trains on learner content by default.
- [ ] Confirm no other provider is offered: the allow-list is exactly
      `anthropic`, `openai` and `gemini`, and no learner-supplied endpoint
      exists anywhere in the feature — the registry fails startup naming any
      profile that would send a key anywhere but the provider's canonical
      HTTPS host. Review every declared profile's `user_key_provider`
      binding once more under the hosted flags.

## 4. Rails and defaults worth reviewing

The house rails that protect the operator's wallet still stop every call the
learner's key does not serve; a learner-keyed call is exempt from the daily
USD cap only, and every rate rail survives. Review each default against this
instance's risk posture:

- [ ] `LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP` — the per-(learner, book,
      calendar-month) prompt-token ceiling on user-keyed calls; default
      **4,000,000**, `0` disables it. The ceiling is the relay/extraction
      brake: one book pumped through one key crosses it in a fraction of a
      month, an honest heavy month does not. Decide whether the default fits
      the instance's books; disabling it on a public host removes the only
      per-book bound on learner-keyed prompting.
- [ ] `LEARNY_DAILY_AI_SPEND_USD` and the per-day `daily_ask_cap` /
      `daily_teach_start_cap` counters — unchanged by the exemption (counters
      and the kill switch still stop a user-keyed call); confirm the values
      still make sense now that house spend and learner spend are separate
      ledgers.
- [ ] The learner's own soft monthly budget — set and cleared by the learner
      in Account, stored per user, never operator-enforced. It pauses only the
      learner's own key. No operator action is needed to raise or clear it.
- [ ] The kill switch (`ai_kill_switch`) — stops user-keyed calls too (503);
      confirm the operators on call know it covers both payers.
- [ ] Route rate limits on the key routes and the turn/deck/cards routes —
      unchanged for every payer; confirm the buckets fit a hosted cohort.
- [ ] Deck payer pinning — a deck submitted on a learner key runs on exactly
      the pinned credential row or fails terminally; it can never silently
      fall back to the house key and debit the operator.

## 5. Go/no-go

- [ ] Every box above is checked, with dates and sources recorded.
- [ ] The hosted disclosure and privacy badges render (spot-check the account
      page in both locales, `en` and `pt-BR`).
- [ ] A canary learner key: store, test, generate a turn, check the usage
      line and the month-to-date row, delete the key. The key value must never
      appear in any response, log or error (ADR-0033's leak canary test runs
      in CI; the spot-check is the operator's own confirmation).
- [ ] The incident path is understood: a leaked or compromised KEK means
      rotating it (invalidating every sealed key), and notifying learners that
      their keys must be re-entered.

**Go**: set `LEARNY_HOSTED_BYOK_ENABLED=true` on the API and the worker, and
record the date and who flipped it next to this checklist.

**No-go**: leave the opt-in unset. The declaration alone is safe — the keys
surface reads as feature-off everywhere, no credential row is read, and every
write answers 404.
