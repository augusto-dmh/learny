# Contracts

Fixtures that more than one stack has to agree with.

Learny keeps its stacks apart on purpose: the server owns the product logic, the reader
owns what a person sees. A few small derivations nonetheless exist on both sides, because
the reader cannot round-trip to the server for every page rule it draws. Those are the
dangerous ones — two hand-written mirrors of one rule, each with its own green test suite,
free to drift apart without either suite noticing.

A file here is the single statement of such a rule, in data. Every stack that implements
the rule reads this file in its own tests and asserts against every case, so a change on
one side that breaks agreement fails a test rather than shipping two different answers.

Each file names, in itself, which test files read it. Add a case rather than a comment: a
case is enforced everywhere, a comment nowhere. When a case changes, every listed suite
must be updated in the same change — that is the point of the file.

| File | The rule | Enforced by |
| --- | --- | --- |
| `page-boundaries.json` | Where a page number turns, given a word offset and a quantum | `backend/tests/test_reading_pure.py`, `frontend/tests/pages.test.ts` |
