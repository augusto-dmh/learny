---
description: Read-only status report on the current ship cycle
---

Report the current ship-cycle status WITHOUT modifying anything or resuming any work — this command may be run from a parallel session while a cycle is in flight, and it must not disturb that cycle.

1. Read `.specs/.ship-status` if it exists and report its line (cycle, stage, branch/PR, timestamp, status). If absent, say "no cycle in flight per the heartbeat" and continue — the remaining checks catch a cycle from before the heartbeat existed.
2. Run `git branch --show-current` and `git status --short` (report at most the first 10 lines).
3. Run `gh pr list --limit 5`; for the newest open PR, run `gh pr checks <N>` and report the check states.
4. Report any background tasks or teammate agents visible in this session and whether they look active or idle.

End with a single summary line: what stage the cycle appears to be in and what it is waiting on (CI, review, merge gate, nothing). Do not nudge agents, do not push, do not edit files.
