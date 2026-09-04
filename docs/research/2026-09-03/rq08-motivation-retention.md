# RQ08 — Motivation & retention

- **Date:** 2026-09-03
- **Question:** Which motivation mechanics genuinely help learners come back to review and read, and which backfire or cheapen a serious learning product?
- **Audience:** public-launch fleet (quality-first; Learny is book intelligence with citations, not a language game).
- **Shipped today:** Home already shows Continue reading, Reviews due, and a GitHub-style 12-week heatmap counting reviews + pages, with a server-computed “Studied *X* of the last 14 days” line, silent empty cells (no broken-streak copy), and a local hide-stats toggle. FSRS-6 runs at `desired_retention=0.9`. The due-queue page defaults to 20 items (cap 100). RFC-004 capped gamification at progress + calm streaks and deferred notifications; this report revisits that cap now that a public instance needs email.

Sources accessed 2026-09-03. Prior product survey (Duolingo / Anki heatmap / RemNote / Readwise / Kindle): `docs/research/2026-07-18/student-experience/rq04-home-reentry-ritual.md`. This report goes one layer deeper: SDT, published streak experiments, gamification meta-analyses, habit science, SRS abandonment, digest UX, goal-setting, and social accountability.

## TL;DR

The mechanics that retain serious learners are **competence feedback that is informational** (heatmap, due-today, bounded “done for today”), **autonomy** (self-set volume, hideable stats, opt-in mail), and **a small, finishable daily job**. Consecutive-day streaks, freeze economies, XP/badges/leaderboards, and guilt notifications raise *app* DAU by converting learning into loss-aversion; they are a poor fit for Learny’s identity and they predict performative sessions, not recall.

Learny already shipped the high-evidence, low-shame core (heatmap + 14-day adherence, not a flame). The public-launch gap is not more gamification. It is (1) **SRS load shaping** so the due pile cannot become the reason people quit, (2) an **opt-in due digest** that is a ritual cue, not spam, and (3) a **when/where plan** on Home so showing up is cued by an existing routine. Social/shared-deck features should wait: accountability partners increase check-ins *and* fake study.

**Hard cap to keep:** no XP, coins, badges, leaderboards, mascot guilt, streak-repair shops, or push. **Narrow thaw of RFC-004:** opt-in transactional email only.

---

## Lens: self-determination theory (autonomy / competence / relatedness)

Ryan & Deci treat autonomy, competence, and relatedness as *needs*, not preferences. Controlling rewards shift the perceived locus of causality outward and undermine free-choice intrinsic motivation; informational feedback that affirms competence, given with a sense of choice, does not ([Ryan & Deci 2000, *American Psychologist*](https://selfdeterminationtheory.org/SDT/documents/2000%5FRyanDeci%5FSDT.pdf); [Deci, Koestner & Ryan 1999 meta-analysis, *Psychological Bulletin*](https://doi.org/10.1037/0033-2909.125.6.627)). Later CET-style meta-analysis still finds expected, engagement- and completion-contingent tangible rewards undermine free-choice IM (overall *d* ≈ −0.28; unexpected rewards ~0) and finds the only reliable *enhancement* on free-choice IM is **positive feedback** ([Turku 2021 dissertation summary of the CET pattern](https://www.utupub.fi/handle/10024/173853?show=full)).

Product translation for Learny:

| Need | Helps | Thwarts |
|---|---|---|
| **Autonomy** | Hide stats; self-set reading/review volume; digest opt-in; “pause reviews” without breaking a number | Flame that zeros; freeze you must buy; “you will lose your streak at midnight” |
| **Competence** | Due-today that ends; heatmap intensity as *work done*; citation-grounded cards that are actually recallable | Inflated desired-retention that makes every session a failure pile; XP for opening the app |
| **Relatedness** | Teach/Ask beside the passage; notes that talk back to the book; optional human share of a *passage* | Leaderboards, Friends Quests, deskmate check-ins that invite pretending |

The three needs are mutually supportive: a competence display that feels controlling also knocks autonomy ([Springer 2024 SDT-in-gamification](https://doi.org/10.1007/s11528-024-00968-9)). Organismic Integration Theory adds a continuum: *identified* regulation (“I review because I want to remember this chapter”) is high-quality and sticky; *introjected* regulation (“I review so I won’t feel like a failure at midnight”) looks like retention in DAU charts and feels like anxiety in the user. Consecutive streaks and guilt mail manufacture introjection. Learny’s audience arrives *already* intrinsically interested in a book. That is exactly the overjustification setup: controlling extras are most harmful when the activity was interesting to begin with.

**Verdict: adopt as the design filter**, not as a feature. Every mechanic below is scored against this table.

---

## Mechanic-by-mechanic

Evidence quality: **H** = peer-reviewed meta-analysis / multi-study experiment; **M** = vendor A/B (causal for DAU, not learning) or practitioner consensus (Anki/FSRS manuals); **L** = forums, UX commentary, correlational product stats. Duolingo “learners with a 7-day streak are *N*× more likely…” claims are **L/M** — they mix selection with treatment.

### 1. Heatmap + rolling adherence (already shipped)

- **Evidence.** Calm, retrospective calendars are the form of “gamification” even anti-game SRS users install ([glutanimate/review-heatmap](https://github.com/glutanimate/review-heatmap); [AnkiWeb listing](https://ankiweb.net/shared/info/1771074083)). Informational progress (how much you did) supports competence without a controlling contingency. Lally et al. found missing *one* opportunity did not materially slow habit formation; inconsistency did ([Lally, van Jaarsveld, Potts & Wardle 2010, *EJSP*](https://doi.org/10.1002/ejsp.674); [UCL summary: median ~66 days to automaticity, range 18–254](https://www.ucl.ac.uk/news/2009/aug/how-long-does-it-take-form-habit)). A 14-day window matches that science better than a consecutive counter.
- **Quality:** H (habit automaticity) + M (ecosystem revealed preference).
- **Learny design:** Keep the 84-day week-aligned grid, `studied_last_14` as the only headline number, intensity = reviews + pages, empty cells silent, hide toggle. Do **not** promote a consecutive count into chrome. Optional later: hover already shows the day; a weekly “pages + reviews” total is enough volume.

A study day in Learny already means *any* reading-position write or review (RFC-004 Cycle E). Keep that decoupling: showing up is binary; volume lives in the heatmap shading and the reviews/pages totals. Do not raise the bar so that only a 20-card session “counts.” That would re-couple habit to volume, which is the mistake Duolingo measured and then undid.

**Verdict: adopt (keep).** This is the right seriousness register. Do not “productize” it into GitHub-contribution FOMO copy.

### 2. Consecutive-day streaks (Duolingo flame)

- **Evidence (pro).** Official A/B: decoupling streak from the daily XP goal (one lesson extends the streak) → +3.3% D14 retention, +10.5% of daily learners on a streak in 20 days, ~⅓ → ½ of DAUs on a ≥7-day streak a year later ([blog.duolingo.com — improving the streak, 2020](https://blog.duolingo.com/improving-the-streak/)). Streak Freeze inventory of two → +0.38% relative DAU ([habit-research post, 2022](https://blog.duolingo.com/how-duolingo-streak-builds-habit/)). Streak Wager → +14% D7 retention; Weekend Amulet → +4% return a week later, −5% streak loss ([2017 growth post](https://blog.duolingo.com/how-streaks-keep-duolingo-learners-committed-to-their-language-goals/)). They explicitly tap **loss aversion** once the number is long (same 2022 post) and send streak-personalized practice reminders ([notification-bandit post](https://blog.duolingo.com/hi-its-duo-the-ai-behind-the-meme/)). Two headline multipliers are easy to mix up: **2.4× next-day use** at a 7-day streak ([2021 habit post](https://blog.duolingo.com/putting-in-work-the-habit-of-language-learning/)) vs **3.6× course completion** ([2022 habit-research post](https://blog.duolingo.com/how-duolingo-streak-builds-habit/)). Both are correlational: people who already show up seven days in a row are not a random sample.
- **Evidence (con).** The same decoupling post admits **fewer people hit the volume goal** once the streak no longer required it — DAU up, depth down. Intense daily goals *blocked* streaks. That is the performative-learning trap: protect the number with the cheapest legal action. Critiques of streak-as-goal and midnight cramming are widespread; treat as failure-mode reports, not as causal papers. Sharif & Shu’s *emergency reserve* work shows slack-with-a-cost raises *persistence on the goal as framed* ([JMR 2017](https://doi.org/10.1509/jmr.15.0231); [UCLA Anderson write-up](https://anderson-review.ucla.edu/emergency-reserves/)) — which is why freezes work *and* why they make the streak, not the book, the object of protection.
- **Quality:** M for DAU A/Bs; L for learning outcomes; H for the loss-aversion / slack mechanism, misapplied.
- **Learny design:** Do not add a consecutive counter, freeze shop, wager, or amulet. The 14-day adherence line *is* the emergency reserve (you can miss days inside the window without a zeroed identity). If a consecutive number is ever shown, put it in the heatmap tooltip only, never in chrome, never with a countdown.

**Verdict: avoid** as a primary mechanic. Duolingo optimized for opening the app; Learny’s unit of value is a finished review of a cited card and a page of a book.

### 3. Points, badges, leaderboards (PBL)

- **Evidence.** Sailer & Homner meta-analysis: small effects on cognitive (*g* = 0.49), motivational (*g* = 0.36), and behavioral (*g* = 0.25) outcomes; motivational/behavioral effects **weaken under high methodological rigor**; competition-without-collaboration is a poor moderator ([*Educational Psychology Review* 2020](https://doi.org/10.1007/s10648-019-09498-w); [ERIC EJ1245270](https://eric.ed.gov/?id=EJ1245270)). Mekler et al.: points, levels, and leaderboards raised **tag quantity**, not competence or intrinsic motivation — they behaved as extrinsic incentives ([*Computers in Human Behavior* 2017](https://doi.org/10.1016/j.chb.2015.08.048)). Hamari, Koivisto & Sarsa’s review: results mixed, context-dependent, novelty common ([HICSS 2014](https://doi.org/10.1109/HICSS.2014.377)). A 2023 systematic review of gamified learning notes short-term motivation that **declines with exposure** ([PMC10448467](https://pmc.ncbi.nlm.nih.gov/articles/PMC10448467/)).
- **Quality:** H.
- **Learny design:** None. Per-book progress % on the bookshelf is progress, not a badge. Do not mint “100 reviews” achievements.

**Verdict: avoid.** Cheapens the product and is the textbook CET undermining case.

### 4. Habit formation: implementation intentions and routine anchors

- **Evidence.** If-then plans (“When situation *Y*, I will do *X*”) produce a medium-to-large lift on goal attainment, *d* = 0.65 across 94 tests ([Gollwitzer & Sheeran 2006, *Advances in Experimental Social Psychology*](https://doi.org/10.1016/S0065-2601(06)38002-1)). Habits are context–response associations: stable cue + repetition; goals predict poorly once the habit is strong; context change (moving, new job) is a discontinuity window ([Wood & Neal 2016](https://dornsife.usc.edu/wendy-wood/wp-content/uploads/sites/183/2023/10/Wood.Neal_.2016.pdf); [Neal, Wood et al. 2012](https://doi.org/10.1016/j.jesp.2011.10.011)). Duolingo’s own copy test: habit-framed reminder opt-in beat streak-framed opt-in by +5% ([habit-of-language-learning post](https://blog.duolingo.com/putting-in-work-the-habit-of-language-learning/)).
- **Quality:** H (plans, habits); M (copy test).
- **Learny design:** One optional Home prompt after first successful review day: “When will you usually review?” (after morning coffee / after lunch / after the last chapter of the evening). Store a local-time window. Use it only to *schedule the digest* and to label the Reviews card (“Your evening review”). No nag if they miss. This is stacking onto an existing routine, not inventing a streak.

Reading has its own cue: the unfinished chapter (Zeigarnik / Kindle resume). Learny already leads Home with Continue reading; the plan prompt should treat *review* as the behavior that needs a cue, because reading has a built-in open loop and review does not.

**Verdict: adapt.** Highest-evidence, lowest-schlock retention lever Learny does not yet have.

### 5. Spaced-repetition adherence (why Anki is abandoned; FSRS load)

- **Evidence.** Practitioner consensus, repeatedly: the quit path is **backlog spiral** (miss days → 300 due → close the app → guilt → larger pile), compounded by uncapped new-card intake. Anki: ~20 new/day ≈ ~200 reviews/day at steady state; stop new cards while catching up; default review cap 200 exists to bound the display ([Anki deck options](https://docs.ankiweb.net/deck-options.html)). FSRS: desired retention is the main knob; **default 90%**; “above 90% the workload increases very quickly, and above 97% the workload can be overwhelming” (same manual). Workload vs knowledge is U-shaped: too-low DR causes relearn churn; too-high DR explodes reviews. Anki 24.04+ “minimum recommended retention” minimizes workload/knowledge, not raw recall ([FSRS Optimal Retention wiki](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Optimal-Retention); [fsrs4anki tutorial](https://github.com/open-spaced-repetition/fsrs4anki/blob/main/docs/tutorial.md)). Secondary ethnography matches: overwhelm, then guilt ([why people quit Anki](https://my-senpai.com/insights/why-people-quit-anki.html) — L, use as illustration not proof).
- **Learny today:** `LEARNY_FSRS_DESIRED_RETENTION` default 0.9, fuzzing on (good: fuzz spreads piles). Queue *page* size 20, but **total due is uncapped** and Home can still say “N due.” No new-card daily throttle. No catch-up mode. Empty review state is “Nothing due right now,” not a completion ritual. ADR-0021 deferred the optimizer and per-user DR — still correct until a user has hundreds of reviews.
- **Design (concrete):**
  1. **Today’s job ≠ total overdue.** Home and `/review` offer “Today’s reviews” = min(due, user cap, default ~20–40) plus a quiet “+N overdue, not in today’s session.” Finishing today’s job shows **Done for today** (Anki’s congratulations screen). Overdue remains available behind “Keep going.”
  2. **New-card intake follows reviews.** Until today’s reviews (or the cap) are done, do not inject newly generated deck items into the due pile that day. After a gap, **pause new** until overdue < cap.
  3. **Keep DR = 0.90** as the product default. Offer 0.85 / 0.90 / 0.93 only after the user has a real queue, with one sentence: “Higher remembers more cards; it also means more reviews.” Do not expose 0.97.
  4. **Vacation:** “Pause scheduling for *N* days” shifts `due` forward (or holds new) without a shame state. This is Sharif-style slack **without** a freeze SKU.

**Verdict: adopt** load shaping. This is the retention mechanic that protects Learny’s actual learning loop. **Adapt** per-user DR later, not at launch.

### 6. Notifications and email digests

- **Evidence.** NN/g: ask permission after value, say what you will send, do not burst, make off easy ([Five mistakes in push design](https://www.nngroup.com/articles/push-notification/)). Email is the right channel for non-urgent, durable content; push is for time-critical interruption ([NN/g smart-home channel guidance](https://www.nngroup.com/articles/smart-home-notifications/)). Readwise’s ritual is a **bounded, user-timed daily review** (commonly ~minutes, not an inbox firehose), with frequency tuning and a one-click “never email” that still leaves in-app review ([Readwise: reviewing highlights](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights)). Duolingo’s winning January copy was habit-framed, and reminders are **opt-in**; their aggressive owl is the anti-pattern for Iron Gall. Digest product practice: default to the slower cadence; skip empty sends; one-click unsubscribe; Gmail/Yahoo 2024 bulk-sender one-click `List-Unsubscribe`.
- **Quality:** M (UX research + analogous product); no Learny-specific RCT.
- **Learny design:**
  - **No push** for v1 public (desktop-web first; RFC-004).
  - **One digest, opt-in after the user has completed ≥1 review or ≥1 reading day.** User picks local hour. Default **off** at register (email verification is RQ09’s job; marketing is not).
  - Body, scannable in <30s, e.g. subject `12 cards today · Ch. 7 of <title>`; body: resume line, “12 in today’s session (31 overdue parked)”, two buttons. **No streak, no owl, no “you’re about to lose…”.** Skip the send if N=0 and there is no in-progress book.
  - Optional **Sunday recap** (separate toggle, default off): 14-day adherence, pages, reviews — the heatmap in prose. Recaps that arrive on empty weeks train people to ignore mail; skip those too.
  - Preference center: Daily / Weekly / Off, per type. Unsubscribe does not delete the account.

**Verdict: adapt** (opt-in due digest). **Avoid** guilt push and default-on mail.

### 7. Goal-setting (daily review targets, reading goals)

- **Evidence.** Specific, difficult goals beat “do your best”; meta-analytic *d* ≈ 0.52–0.82, moderated by commitment, feedback, and task complexity ([Locke & Latham 2002, *American Psychologist*](https://doi.org/10.1037/0003-066X.57.9.705)). Side effects when over-prescribed: tunnel vision, gaming, and reduced IM ([Ordóñez, Schweitzer, Galinsky & Bazerman 2009, *AMP*](https://www.hbs.edu/ris/Publication%20Files/09-083.pdf)). Duolingo: coupling a *volume* goal to the streak made intense goals the people *least* likely to hold a streak. RemNote’s current model splits a small streak goal from a daily learning goal and can **spread the week’s reviews** so the target is the load, not a vanity number ([RemNote Goals and Streaks](https://help.remnote.com/en/articles/7950933-goals-and-streaks)). Anki-user design threads converge on **percentage of today’s due**, not a fixed card count, so missed days don’t silently accumulate outside the goal ([Anki forums: beyond streaks](https://forums.ankiweb.net/t/beyond-streaks-daily-weekly-anki-goals/62943)).
- **Quality:** H (goal theory); M (product splits).
- **Learny design:** The goal *is* “finish today’s session” (mechanic 5). Do not add a second XP-like daily target. Optional reading goal: self-set “minutes in the reader” or “one chapter,” displayed only on the Continue-reading card as a progress tick, **never** required to “count the day” (a study day already counts any reading or review). Mastery framing (“finish this chapter’s cards”) over performance framing (“hit 50 reviews”).

**Verdict: adapt** as a bounded daily job. **Avoid** numeric volume goals that gate identity.

Kindle-style reading insights (days-read calendar, optional, prize-free) are the reading analog of Learny’s heatmap and are already in the 2026-07-18 survey. Do not add a second “reading streak” beside the study heatmap — one calendar, two intensity channels (pages vs reviews) is enough. A pages-per-day *target* would punish dense chapters and PDF page inflation; if a reading goal exists, denominate it in **minutes in the reader** or **chapter completed**, never pages.

### 8. Social / accountability (shared decks, study groups, partners)

- **Evidence.** Relatedness supports internalization — but platform “accountability partners” are a dual-use mechanic: Shanbay deskmate data show **more check-ins and less study time plus more pretending-to-study** ([HICSS 2025](https://doi.org/10.24251/hicss.2025.004)). A MOOC RCT of “tell someone inside vs outside the course” did **not** raise completion on average; inside-course accountability *reduced* comments ([Li, Kizilcec et al. 2025, *Online Learning*](https://doi.org/10.24059/olj.v29i4.5215)). Cooperative learning helps when there is **individual accountability plus structure**, which is a classroom technology, not a bookshelf.
- **Quality:** M (large observational + one RCT); not Learny-population.
- **Learny design:** Do not build shared decks, leagues, or study groups for public launch. Relatedness that fits: Teach mode (parasocial tutor against a cited passage), vault export into the user’s existing Obsidian graph, and later a *link to a passage* a friend can open if they also own the book. Shared Anki decks are a known quality/licensing swamp and fight Learny’s per-user FSRS state.

**Verdict: avoid** for launch. Revisit only as passage-level share, never as a leaderboard.

### Adjacent-product anti-patterns (do not port)

| Pattern | Source | Why it fails here |
|---|---|---|
| Flame in chrome + midnight countdown | Duolingo | Introjected regulation; performative 1-lesson days |
| Coin/XP daily goal | LingQ / Duolingo | Users farm cheap actions; volume ≠ learning |
| Streak freeze as SKU | Duolingo Super | Monetizes anxiety the product created |
| Celebration modal on every study day | LingQ forums | Serious learners experience it as spam |
| Store recommendations on Home | Kindle Home tab | Vendor goal displaces the open book |
| Deskmate / Friends Quest | Shanbay, Duolingo | More check-ins, less study, more pretending |
| Uncapped “N due” as the day’s job | Anki without limits | The backlog spiral |

Learny’s existing Home (two cards + heatmap) already avoids most of this list. The remaining holes are the uncapped due total, the missing Done-for-today ritual, and the missing external cue.

---

## Fit table (public-launch)

| Mechanic | Verdict | Why |
|---|---|---|
| Heatmap + 14-day adherence, hideable | **Adopt** | Informational competence; already shipped; Anki-user-proof |
| Consecutive streak + freeze/wager/amulet | **Avoid** | DAU via loss aversion; performative lessons; wrong identity |
| XP / badges / leaderboards | **Avoid** | CET undermining; Sailer/Mekler: quantity ≠ IM |
| Implementation intention on Home | **Adapt** | *d* = 0.65; cues the digest; no theatre |
| Today’s-session cap + new-card throttle + vacation | **Adopt** | The actual Anki-quit mechanism; protects FSRS |
| Per-user FSRS DR (0.85–0.93) with copy | **Adapt** (not cycle-1) | Real trade-off; needs a queue first |
| Opt-in due digest (email) | **Adapt** | Readwise ritual; NN/g; thaws RFC-004 narrowly |
| Default-on / guilt push | **Avoid** | Spam; desktop-web; Duolingo owl |
| “Done for today” as the goal | **Adopt** | Locke (specific + proximal) without Goals-Gone-Wild volume |
| Shared decks / accountability partners | **Avoid** | Check-ins up, study down; licensing; FSRS is personal |

---

## Cycle-sized moves

Each is one spec-driven cycle. Ordered for public launch.

### Cycle 1 — Bounded daily review (load shaping)

**Ship:** Split `due_total` from `today_session` (default 20–40, user-editable, hard cap). Home Reviews card and `/review` run the session. Empty session → **Done for today** with a link to the current book, not “nothing due” as a void. Hold **new** quiz items out of the session until today’s reviews are clear; after ≥2 missed days, auto-hold new until overdue ≤ session size. Optional “Pause for *N* days” shifts dues.

- **Why recommend:** Matches the highest-confidence SRS-quit mechanism; uses existing FSRS rows; no new provider; makes the heatmap’s “study day” a finishable ritual. Directly serves competence + autonomy.
- **Why not:** Caps hide true overdue and can delay FSRS’s target retention if users always stop at 20; vacation-shift is a scheduling-policy decision that needs a clear invariant (do not rewrite `review_log`). Users who *want* to clear 200 cards should still be able to “Keep going.”

### Cycle 2 — Opt-in due digest

**Ship:** Preference: Off (default) / Daily at local hour / Weekly Sunday recap. Celery beat; skip empty; body = resume chapter + today’s session count + one button each. One-click unsubscribe + `List-Unsubscribe`. Copy is habit-framed (“Time for today’s reviews”), never streak-framed.

- **Why recommend:** External cue is the missing half of Wood/Lally habit formation; Readwise shows the bounded email ritual works for bookish adults; public launch already needs transactional mail (verification).
- **Why not:** New infra (sender domain, deliverability, bounce) belongs with RQ09; bad copy or default-on will train spam reports and cheapen Iron Gall; RFC-004 explicitly froze notifications — this cycle is a documented, narrow thaw.

### Cycle 3 — Routine prompt (implementation intention)

**Ship:** After the first Done-for-today, a single dismissible Home card: “When do you usually study?” Stores `review_anchor` (enum + timezone). Feeds Cycle 2’s send hour. No reminders beyond the digest they already opted into.

- **Why recommend:** Best-replicated self-regulation intervention in this file (*d* = 0.65); tiny UI; autonomy-preserving (optional, skippable).
- **Why not:** Easy to over-build into a coach; without Cycle 2 it has nowhere to send the cue; some users have no stable routine (Lally: inconsistency never automated).

### Cycle 4 — Workload-aware FSRS (later)

**Ship:** Settings: desired retention 85 / 90 / 93% with a one-line workload hint; keep 90% default. Still no optimizer until *N* reviews (ADR-0021). Maybe a “this week vs last week reviews” line under the heatmap — volume as information, not a goal.

- **Why recommend:** Official FSRS guidance is that DR is the important knob and 90% is the balance point; giving autonomy here is more honest than a fake streak.
- **Why not:** Easy to scare people into 93% and recreate Anki overwhelm; needs copy + a sample-size gate; optimizer is still deferred for good cost/complexity reasons.

**Explicitly not a cycle:** freeze shops, wagers, badges, leagues, shared decks, Duo-style widgets, or celebrating a consecutive number.

---

## Caveats

- Duolingo A/Bs measure **return to the app**, not vocabulary or book comprehension. Treat them as a warning about what loss-aversion can buy, not a playbook.
- Anki abandonment literature is mostly practitioner + forums, not an RCT of “caps vs no caps.” The mechanism (compounding reviews) is still the right design threat.
- RFC-004’s “no notifications” cap should be amended in the next student-experience RFC if Cycle 2 is accepted — do not quietly contradict it.
- Relatedness for a single-reader product is mostly *book-as-interlocutor* (Teach/Ask). That is RQ03’s job; do not fake it with friends lists.
- Sharif & Shu emergency reserves increase persistence on the *framed* goal. Use that finding to justify silent slack in the 14-day window and a vacation pause — not to justify a freeze SKU that makes the consecutive number the goal.
- This report does not recommend changing heatmap shading, Iron Gall, or FSRS population defaults. Those are working.

## Open questions for synthesis

- Should “Done for today” allow a one-tap jump into the current chapter (reading-first) or stay on Review? Recommend: jump to the book; review was the duty, reading is the pull.
- Is a weekly recap worth its own toggle, or does the in-app heatmap already cover it? Recommend: ship Daily digest first; add Weekly only if Daily opt-in is healthy and people ask for less mail, not more.
- Per-user DR vs a global 0.90: wait until there is a real multi-user queue distribution to look at. Do not guess.
