# Submission issue draft v2 (merged: Muse's prose + verified corrections). NOT filed. For the owner's review.

Form: https://github.com/karlmehta/code-for-a-billion/issues/new?template=submission.yml . Deadline stated by the organizer's site: 15 Nov 2026
(timezone not stated). [BRACKETS] = only the owner can fill truthfully. Removed from Muse's draft because unsupported or untrue:
the AgentFoundry history paragraph, "zero cost on free tiers", "over 50 crore users", "figure Sach returns as TRUE", "EVIDENCE.md".
This version supersedes submission-draft.md in this folder.

## Team / Project name
Sach

## Team members (names + GitHub handles)
[Owner's full name, if he wants it public] (@pruthvig1998), solo

## Problem statement
Forwarded messages on WhatsApp are, for many Indian families, the way news arrives: a new government scheme, a cure, an urgent
warning. Some of them are false, and the harm is documented (cyber-fraud losses reported to Parliament, rumour-driven mob violence
counted by IndiaSpend). Fact-checks exist (PIB Fact Check, BOOM, Alt News), but they are published on websites, mostly in English,
usually after a forward has already circulated, and they do not travel the path the claim took. Sach lets a person paste a forward
in English or one of 15 Indian languages and returns a cited verdict, or says UNVERIFIED, before they pass it on.

## What you built
Sach checks a forward before you pass it on. It extracts the claims and checks each in three layers. First, a match layer looks up
published fact-checks (PIB's archive, PIB Fact Check posts on X, and other checkers through the Google Fact Check Tools API); when a
claim was already checked, Sach shows that verdict attributed to the original checker, never as its own. Second, a live layer
retrieves evidence, PIB and official sources first; an AI judge must quote a source verbatim and code verifies the quote. Third,
when neither layer can settle it, the result is UNVERIFIED and the page offers links to human fact-checkers with the question
prefilled. The verdict rules are hard code, not model mood: FALSE only on an official contradiction or a PIB debunk, TRUE only on
official confirmation, otherwise UNVERIFIED.
Around that core: a link, UPI ID and phone-number checker that never says "safe" (it only recognises a verified official list or
flags imitation and scam patterns); verdict cards for forwarding back in the claim's language; a ClaimReview feed; a Telegram bot
(off until a token is set); a public ledger of checks. Non-English wording is AI-written and not yet native-reviewed (docs/languages.md).
How I used AgentFoundry: **[Write ONLY what really happened in the AgentFoundry IDE, with dates and the resulting commit (see
agentfoundry-task-brief.md). If nothing happened, say so plainly here and do not tick the confirmation.]**
Demo video: [Attach only after the owner has watched it and checked every verdict against the live site.]

## GitHub repository URL
https://github.com/pruthvig1998/sach-check (public, MIT)

## Demo URL (live app or video)
https://sachcheck.in

## Scale & severity of the problem  (figures need the owner's approval; sources in docs/problem-evidence.md)
Kantar-IAMAI counted 886 million active internet users in India in 2024, and 98% of them accessed the internet in Indic languages.
In the Reuters Institute's 2025 India survey, 53% named WhatsApp as the channel with the biggest misinformation threat, the highest
of any market; that sample is mainly English-speaking, so regional-language users are under-measured. IndiaSpend counted 33 deaths in
69 mob attacks over child-lifting rumours between January 2017 and July 2018, with WhatsApp the named source in 19 cases. The Home
Ministry told the Lok Sabha that citizens lost Rs 22,845.73 crore to cyber fraud in 2024 against Rs 7,465.18 crore in 2023 (not
attributed to fake forwards). PIB Fact Check reports 2,913 fact checks to April 2026 and covers only central-government claims.

## Deployment & impact data
- Live at https://sachcheck.in; first commit 12 Nov 2026 [confirm the first public deploy date from Vercel]. No accounts, no ads.
  It runs mostly on free tiers plus Google Cloud trial credit for the AI judge and search; do not call it zero-cost.
- Tests: 5,125 automated tests pass on commit e81b1cc (command in the README). This measures software regressions, not fact-check accuracy.
- Evaluation: a published 79-claim set (data/eval_set.json: 34 PIB-debunked FALSE, 34 officially announced TRUE, 11 invented
  UNVERIFIED controls, English plus 15 Indian languages and code-mixed). On the final code (commit e81b1cc) we have
  not obtained a fully clean run: three complete runs were each partly degraded by search or AI-judge failures. Their exact-match
  results were 21/79, 32/79 and 29/79, with 0 overclaimed FALSE and 0 overclaimed TRUE in every run that finished; the system
  mostly abstains (UNVERIFIED on about 63% of the 68 claims labelled TRUE or FALSE) instead of guessing. Degraded runs are saved
  in docs/evaluation-fallback-run.md and are not presented as the headline. An earlier 31-claim run on older code scored 26/31
  (docs/evaluation.md, marked as measured on earlier code).
- Adversarial testing: a 53-case red-team set (data/red_team.json); final run on e81b1cc: 53 cases, 0 overclaims, 0 unexpected (docs/red-team.md).
- Public feeds: /impact and /claimreview.json; counters count checks including repeats and some test traffic, not people.
- Real users: no pilot has run and no user numbers are claimed. [If a pilot runs: report only collected responses with
  denominators and the selection-bias note.] Known limits are listed in the README.

## Track / category
Governance

## Contact email
[An address the owner is happy to publish; the form makes the issue public]

## Confirmations
- [ ] Built using AgentFoundry (AF), the official IDE (tick only if true)
- [ ] Our repository is public and includes a README with setup steps
- [ ] The demo link works and is accessible to judges
