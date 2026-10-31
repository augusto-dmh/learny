# installable-and-adult-launch verification

## Batch A (C1-C8) — record at the batch A PR

- **Mechanical verification (check_proofs.py)** ran at HEAD `d0c27d8` with the tree clean: every batch A proof passed, all four Build commands green, and all 3 declared mutations were killed (purge-deletes-nothing, caches-before-user-known, cache-scope-widening). `proofs.md` is the script's own record.
- **Batch B rows (C9-C19) read red in the same run** — "no test ran" for the vitest proofs whose test files batch B creates, "fail" for the pytest proofs whose modules do not exist yet. This is the section-checkpoint precedent: the batch's own rows are the gate; the not-yet-built batch's rows stay red until batch B builds them, and the final Verifier runs over every check before the last PR (D2).
- **Deviation (limit-death clause, recorded per the ship cycle):** this lane's session cannot spawn sub-agents, so the Verifier did not run as a fresh sub-agent before the batch A PR; the mechanical half ran inline as above, and the independent Verifier over C1-C8 runs from the coordinating session where slots allow. Author ≠ verifier is restored there, not here.
- **Judgement rows the mutations do not cover**, stated for the Verifier's attention: (1) the reader cache is network-first, so a stale cached chapter can only be served when the network is actually gone (C4); (2) the registrar posts the user id on every page load, so a service-worker update relearns the current user even though its activation wiped the caches (C6); (3) data saver's Off choice deliberately overrides the browser signal (C8), and the Streamdown remount key is what makes a live flip strip already-rendered figures.

## Batch B (C9-C19)

(to be recorded at the batch B PR, where the completion gate runs over every check)
