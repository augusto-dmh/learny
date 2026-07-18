# RQ-04 — Home & Re-entry Ritual: What Makes a Student Open the App Every Day

- **Status:** Complete
- **Date:** 2026-07-18 (all sources accessed 2026-07-18)
- **Question:** What makes a student open the app every day — resume-reading, daily queues, streaks — and what belongs on Learny's new Home?

## Method

Surveyed the home/re-entry screens and habit mechanics of Duolingo (habit-mechanics maximum), Anki/AnkiWeb (+ the Review Heatmap add-on ecosystem), RemNote (Flashcard Home), Readwise (Daily Review email + Reader home), LingQ (coins/streaks/goals), and Kindle (Home tab + Reading Insights). Primary sources (official blogs, help centers, manuals) were fetched where available; Amazon's own Reading Insights page returned 503 and LingQ's knowledge base returned 403, so those rely on secondary coverage and support-mirror articles, marked **(unverified)** where applicable. Critiques of streak mechanics were gathered from UX/product-design commentary and user forums and are inherently secondary — treated as failure-mode evidence, not fact claims about internals.

## Per-Product Findings

### Duolingo — the habit-mechanics maximum

- **What Home shows first:** the lesson path with a single obvious next lesson; the streak flame + count is persistently visible in the app chrome and exported to an OS home-screen widget that updates through the local day ([Medium streak-system breakdown](https://medium.com/@salamprem49/duolingo-streak-system-detailed-breakdown-design-flow-886f591c953f), secondary, accessed 2026-07-18).
- **Streak mechanics:** Duolingo calls streaks its single most effective retention lever ([deconstructoroffun mechanics teardown](https://duolingo.deconstructoroffun.com/mechanics/streaks), secondary). Official numbers: learners reaching a 7-day streak are 3.6× more likely to complete their course; the Streak Wager experiment lifted D7 retention +14%; the Weekend Amulet (keep streak over a skipped weekend) made users 4% more likely to return a week later and 5% less likely to lose the streak ([blog.duolingo.com — how streaks keep learners committed](https://blog.duolingo.com/how-streaks-keep-duolingo-learners-committed-to-their-language-goals/), accessed 2026-07-18).
- **The decisive design lesson — decouple the streak from the volume goal:** Duolingo found learners with higher daily goals were *less* likely to maintain streaks, so it changed the rule to "one lesson extends the streak; the daily XP goal is tracked separately." Result: +3.3% D14 retention, +10.5% daily learners on streaks, and "just over half of daily learners have a streak ≥ 7 days" versus roughly one-third before ([blog.duolingo.com — improving the streak](https://blog.duolingo.com/improving-the-streak/), accessed 2026-07-18). Their stated principle: "lowering the barriers to building a consistent daily habit is more important than how much you learn each day."
- **Failure modes (critiques):** the streak weaponizes loss aversion and can become the goal itself — "performative learning" where users game the counter with trivial lessons rather than learning; time/repetition-based achievements rather than proficiency-based ones optimize DAU, not outcomes; streak anxiety and compulsive checking are widely reported ([UX Magazine on hot-streak design without shame](https://uxmag.com/articles/the-psychology-of-hot-streak-game-design-how-to-keep-players-coming-back-every-day-without-shame); [gamification case-study critique](https://www.uladshauchenka.com/p/duolingo-case-study-the-gamification); both secondary, accessed 2026-07-18). Proposed remedies in the critique literature: grace days, "welcome back" instead of zeroing, and adherence-percentage framing ("you studied 90% of days") instead of a fragile consecutive counter.
- **Notifications:** aggressive, personalized streak-guilt reminders are core to the model ([digia.tech UX breakdown](https://www.digia.tech/post/duolingo-habit-forming-reminders-retention-architecture/), secondary) — the exact register Learny's calm identity must not adopt.

### Anki / AnkiWeb — the queue *is* the home

- **What Home shows first:** the deck list with three per-deck counts — New, Learning, Due — and nothing else; tapping a deck shows today's counts and starts reviewing ([Anki manual — Studying](https://docs.ankiweb.net/studying.html), [AnkiMobile deck list](https://docs.ankimobile.net/deck-list.html), accessed 2026-07-18).
- **Bounded sessions:** when today's cards run out Anki says "Congratulations! You have finished this deck for now." — the day's work has a *defined end*, which users occasionally fight but which protects the habit from becoming endless ([Anki forums thread](https://forums.ankiweb.net/t/help-how-to-review-cards-continuously-every-day-or-anytime-i-want-when-anki-says-congratulations-you-have-finished-this-deck-for-now/61446), accessed 2026-07-18). Default daily review limit is 200 to avoid overwhelming displays ([deck options](https://docs.ankiweb.net/deck-options.html)).
- **Streaks are absent from core but massively demanded:** the Review Heatmap add-on (GitHub-style contribution calendar on Anki's home screen, with daily average, days-learned %, current and longest streak) is one of the most popular add-ons in the ecosystem ([glutanimate/review-heatmap](https://github.com/glutanimate/review-heatmap), [AnkiWeb listing](https://ankiweb.net/shared/info/1771074083), accessed 2026-07-18). This is strong evidence that even the most utilitarian, anti-gamification study population wants *calm, retrospective* progress visualization — a heatmap and a streak number, not XP or badges.
- **No resume-reading concept** — Anki has no reading surface; its lesson for Learny is purely the due-count-first, one-tap-to-start queue.

### RemNote — Flashcard Home, the closest structural analog

- **What Home shows first:** a weekly summary graph (cards studied per day, dark/pale blue vs. average, fire icons on goal-met days), total time and cards this week, and one prominent **"Practice Today's Cards"** button; below it a **"Jump Back In"** section of recently studied documents ordered by recency with due-card counts, then all documents with due counts, totals, and progress bars ([RemNote Flashcard Home](https://help.remnote.com/en/articles/7925835-the-flashcard-home), accessed 2026-07-18).
- **Daily goal + streak:** goal is cards/day set by slider with a completion-time estimate; streak = consecutive days hitting the goal, with a goal-met heatmap ([Daily Learning Goal](https://help.remnote.com/en/articles/7950933-the-daily-learning-goal), accessed 2026-07-18).
- **The clever grace mechanic — Daily Goal Smoothing:** RemNote automatically *lowers* the day's target when fewer cards are due, distributing workload across the week, and "you only have to reach your initial, smoothed daily goal to retain any practice streak" (same article). The streak survives light days by design rather than by purchased freezes — a calmer alternative to Duolingo's economy of amulets.
- **"Jump Back In" is the closest existing pattern to resume-reading in a study tool** — recency-ordered re-entry into documents, with the work remaining (due counts) attached.

### Readwise — the email as ritual anchor; Reader's honest "Continue reading"

- **Daily Review ritual:** a daily email (or in-app equivalent) presents a handful of past highlights (commonly described as 5–15) chosen by a recall-probability algorithm; frequency and source mix are tunable per document type; the review takes 2–3 minutes and is repeatedly described by users as a "beloved daily ritual" ([Readwise docs — reviewing highlights](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights), accessed 2026-07-18; ritual framing from user reviews, e.g. [lawsonblake.com](https://lawsonblake.com/readwise-review/), secondary). The docs describe no streak system — the habit anchor is the *external trigger* (email) plus tiny bounded effort, not loss aversion. (An in-app streak counter has existed at times per user reports — unverified.)
- **Reader home / "Continue reading":** Reader's default filtered view only surfaces documents with **>5% progress**, explicitly to keep barely-opened documents out of the resume list ([default filtered views](https://docs.readwise.io/reader/guides/filtering/default-views), accessed 2026-07-18) — an important honesty rule for any continue-reading rail. The **Shortlist** is a deliberately small, user-curated active-reading queue separating "must-read" from "might-read" ([library configuration guide](https://docs.readwise.io/reader/guides/workflows/library-configuration), accessed 2026-07-18). Home views are user-configurable and orderable.

### LingQ — cautionary volume-metric gamification

- **Mechanics:** daily goal and streak are denominated in **coins**, earned by any activity — creating LingQs, upgrading word statuses, marking words known, reading, listening; stats banner sits on the Library screen; milestone notifications ("you now know 1,000 words") ([LingQ 5.0 announcement](https://www.lingq.com/blog/introducing-lingq-5-0/); [LingQ statistics support article](https://lingq-support.groovehq.com/help/what-do-all-the-statistics-mean), accessed 2026-07-18). Streak repair exists per forum reports (unverified — KB page returned 403).
- **Failure modes, from LingQ's own forums:** users game the coin target with low-value actions to keep streaks, and the daily-streak popups generate active resentment — "[Daily streak pop up] so sick of these, can I turn it off?" ([forum thread](https://forum.lingq.com/t/daily-streak-pop-up-so-sick-of-these-can-i-turn-it-off/38209), accessed 2026-07-18). Lesson: a currency-denominated goal invites metric-gaming, and *celebration interruptions* read as spam to serious self-learners.

### Kindle — resume-reading done right, Home done wrong, stats made optional

- **Resume:** Kindle's whole re-entry model is "sync to the last read page; tap the cover of the current book (pinned at the bottom of Home/Library) and you're back at your position" ([aboutamazon.com Kindle app guide](https://www.aboutamazon.com/news/devices/kindle-app-guide), accessed 2026-07-18). Position-restore is invisible, automatic, and the single most load-bearing feature.
- **Home tab failure mode:** the Home tab leads with store recommendations around a small "From Your Library" strip (same source) — widely disliked because it puts the vendor's goals above the reader's. Learny has no store, but the analogous sin is leading Home with anything other than the user's current book.
- **Reading Insights:** consecutive-day and week streaks, a color-coded calendar of days read, and badges — with **no material rewards** and an explicit opt-out ("Don't want Reading Insights?") ([Good e-Reader coverage](https://goodereader.com/blog/kindle/kindle-reading-insights-is-an-excellent-system-that-monitors-reading-habits), secondary, accessed 2026-07-18). In 2025 iOS builds the insights/streaks were reportedly folded into a "Challenges" surface (secondary forum reports, unverified). Kindle demonstrates that a *reading* streak — days-read calendar, weeks-in-a-row — fits a calm bookish identity when it is retrospective, prize-free, and optional.

## Cross-Product Patterns: What Actually Drives the Daily Open

1. **The next action is one tap from open.** Duolingo's next lesson, RemNote's "Practice Today's Cards," Anki's deck due counts, Kindle's pinned current book. Every successful re-entry screen answers "what do I do right now?" before showing anything else.
2. **Two re-entry hooks beat one:** a *pull* (unfinished book, open loop — the Zeigarnik effect Kindle exploits) plus a *duty* (due cards today — Anki/RemNote). Products with both give the user two independent reasons to open.
3. **Bounded daily work.** Anki's "finished for now," Readwise's 2–3-minute review, Duolingo's one-lesson streak rule. The day's obligation must be finishable, and finishing must be visible.
4. **Decouple the habit metric from the volume metric.** Duolingo's single most-validated finding (+40% learners on 7+ day streaks). Showing up counts; how much you did is a separate, softer number.
5. **Grace beats rigidity.** Streak freezes/amulets *increased* retention; RemNote's goal smoothing keeps streaks through light days; critique literature converges on grace days and adherence-percentage framing over fragile consecutive counters.
6. **Calm retrospective visualization is universally loved; interruptive celebration is resented.** Anki users install a heatmap by the hundreds of thousands; LingQ users beg to turn off streak popups. The heatmap/calendar is the safe form of gamification; the popup is the unsafe form.
7. **External triggers (email) work but are a separate machine.** Readwise's ritual is anchored by the email arriving; that is infrastructure Learny's frozen boundary does not currently include.

## Implications for Learny

Learny's Home should be a **quiet two-card study desk**, not a dashboard and not a feed. Exact composition, top to bottom:

1. **Continue-reading hero card** (the Kindle move, given the reading-first principle): cover, title, author, current chapter/section title, human-readable position ("Chapter 7 — §7.2 · 42%"), one click → reader opened at the exact corpus anchor. Apply Reader's honesty rule: only books with meaningful progress (>~5%) qualify; otherwise show the most recently added book as "Start reading." One hero, not a carousel — the single-user persona reads one or two books at a time; a secondary "Also in progress" row of small covers suffices if more than one book is active.
2. **Review card**: "N cards due today · ~M min" with one button into the existing FSRS queue, and a quiet "Done for today ✓" state when the queue is empty (Anki's bounded ending). If N = 0 and nothing is in progress, the card collapses — Home never nags.
3. **A single progress strip below the fold**: a days-studied calendar heatmap (Anki Review Heatmap / Kindle Insights form) + current streak as a plain number with adherence framing ("Studied 12 of the last 14 days"), where *any* study event counts — opening the reader and turning pages, finishing a review, creating a note/card (the Duolingo decoupling: showing up extends the streak; volume is displayed, never demanded). A per-book progress bar lives on the bookshelf (demoted Library), not on Home.
4. **Nothing else.** No recommendations, no stats above the fold, no XP/coins/levels/badges/leaderboards/mascots, no celebration popups, no push notifications. Streak visibility follows Kindle: present, calm, and hideable via a setting.

**Habit mechanics — adopt vs. reject:**

| Mechanic | Verdict | Rationale |
|---|---|---|
| Resume-reading at exact position | **Adopt (hero)** | Kindle-proven; reading-first principle |
| Due-today count + one-tap queue | **Adopt** | Anki/RemNote-proven; FSRS queue already exists |
| Days-studied heatmap/calendar | **Adopt** | The calm gamification form even Anki users install |
| Streak (showing-up-based, adherence-framed, with grace) | **Adopt, capped** | Duolingo's decoupling + RemNote smoothing + critique-literature grace; matches the "progress + streaks" cap |
| Per-book progress % | **Adopt (bookshelf + hero)** | Universal; cheap from reading position |
| Bounded "done for today" state | **Adopt** | Anki; protects the habit from endlessness |
| Streak freezes as an economy / wagers | **Reject** | Loss-aversion monetization theater; use silent grace (e.g., streak survives 1 missed day per week or count "X of last 14 days") instead |
| XP/coins/points goals | **Reject** | LingQ shows currency goals invite gaming; volume ≠ habit |
| Badges, leaderboards, mascot guilt | **Reject** | Single-user, calm identity; proficiency isn't what they measure |
| Celebration popups / push notifications | **Reject** | LingQ forum resentment; desktop-web single-user makes push moot anyway |
| Daily email digest (Readwise model) | **Defer** | The strongest external trigger surveyed, but email infra is outside the frozen boundary; Home must carry the ritual for the 14-day gate first |
| Store-like recommendations on Home | **Reject** | Kindle's most-disliked pattern; nothing on Home but the user's own study state |

**Minimal backend state (frozen-boundary compliant — student-workflow-shaped only):**

| Home element | State needed | New? |
|---|---|---|
| Continue-reading hero | `reading_position` per (user, source): corpus anchor + updated_at | **New — already sanctioned by the boundary ("reading position")** |
| Position → "Chapter 7 · 42%" | progress percent derived from the anchor's ordinal within the corpus (or denormalized onto `reading_position` at write time for a cheap Home query) | Derived — no new domain concept |
| Due-today count | existing FSRS due query | No |
| Heatmap + streak | a `study_days` rollup (user, date), upserted on any reading-position write, review answer, or note/card creation; streak and adherence computed at read time, never stored | **New, minimal** — one table; computing (not storing) the streak avoids repair/freeze machinery entirely |
| Bookshelf per-book progress | same `reading_position` rows | No extra |

No provider, retrieval, or infra changes; no notification/email system; two small tables total.

## Recommendations

1. **Build Home as exactly two cards + one strip**: continue-reading hero (book, chapter/section title, position, one-click resume to the exact anchor), due-cards-today card (count + estimated minutes + one button), and a below-the-fold days-studied heatmap with an adherence-framed streak. Nothing else on the page.
2. **Make resume-reading automatic and invisible**: persist `reading_position` (source, corpus anchor, updated_at) on scroll/section change from the reader; Home's hero and the reader's open-at-position both read it. Apply the >5%-progress rule before a book earns "Continue reading" framing.
3. **Count showing up, not volume**: a study day = any reading, review, or capture event. Display streak as "Studied X of the last 14 days" alongside the consecutive count; a single missed day inside a week does not zero the display's prominence (silent grace, no freeze economy).
4. **Compute the streak, never store it**: one `study_days` (user, date) rollup upserted by existing write paths; heatmap, streak, and adherence are read-time queries. This keeps the boundary minimal and eliminates repair/freeze state machines.
5. **Give the review queue a visible end**: after the last due card, show a quiet completion state on Home ("Done for today") rather than offering more work — bounded effort is what makes the ritual repeatable (Anki/Readwise evidence).
6. **Cap gamification in code, not just intent**: no XP, coins, badges, leaderboards, celebration modals, or notifications anywhere in the v3 student experience; heatmap + streak + per-book progress is the complete list. Add a Kindle-style "hide reading stats" setting so even the streak is optional.
7. **Align the mechanic with the success gate**: the 14-day-daily-study gate is itself an adherence window — surface the same "X of 14" framing on Home so the author's gate and the product's habit metric are one number.
8. **Defer the daily email**, but design the Review card's content (due count + one resurfaced highlight/note teaser) so it could later be projected into a Readwise-style digest without new domain state — the email is the proven trigger to add *after* the frozen boundary thaws.

## Open Issues

- Amazon's first-party Reading Insights page was unreachable (503); the streaks/calendar/opt-out description rests on Good e-Reader's coverage, and the 2025 "Challenges" transition on forum reports (unverified).
- LingQ's official KB returned 403; coin/streak mechanics were confirmed via the LingQ 5.0 announcement and a support mirror, but streak-repair details are unverified.
- Readwise may show an in-app review streak counter not described in its docs (unverified); the docs-supported claim is only that the ritual is email-anchored and bounded.
- Duolingo home-widget internals come from secondary teardowns; official posts confirm the streak stats and the streak/goal decoupling but not widget implementation details.
