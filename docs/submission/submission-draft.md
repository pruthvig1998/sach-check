# Organizer submission draft (NOT filed; for the owner's review)

Form: https://github.com/karlmehta/code-for-a-billion/issues/new?template=submission.yml (fields read from the organizer's
`submission.yml` on 13 Nov 2026). Deadline stated by the organizer's site: **15 November 2026** (timezone not stated; confirm
before relying on a late-evening filing). Anything in [BRACKETS] is a placeholder that only the owner can fill truthfully.
Nothing below claims users, outcomes, accuracy, endorsements or AgentFoundry history that do not exist.

## Team / Project name
Sach (Sach Check): a free fact-checker for viral WhatsApp forwards in India

## Team members (names + GitHub handles)
[Owner's name] (@pruthvig1998). [Add other members only if they really contributed.]

## Problem statement (2-5 sentences)
Millions of people in India receive forwarded messages on WhatsApp claiming a government scheme, order or payment that
they cannot easily check, and most existing fact-checking is in English and reachable only after a claim has gone viral.
A wrong forward can mean a lost payment, a panic, or a scam link tapped by someone who cannot tell it from the real
notice. Sach lets a person paste a forward (in English or any of 16 other Indian languages) and returns TRUE, FALSE,
MISLEADING or UNVERIFIED with the official source cited, and says "UNVERIFIED" rather than guessing.

## What you built (key features, and how AgentFoundry was used)
Features in the repository (see README and docs/):
- Cited verdicts under hard rules: FALSE only when an official or PIB source contradicts the claim, TRUE only when an
  official source confirms it; the AI judge must quote the page verbatim and the quote is checked in code; every other
  case is UNVERIFIED.
- Three layers: a match layer (PIB Fact Check archive, PIB Fact Check posts on X, Google Fact Check Tools, always credited to
  the original checker), a live official-source check, and human hand-off links when the answer is UNVERIFIED.
- A link, UPI ID and phone-number checker that never calls anything "safe": it only confirms a verified official list,
  or says an address imitates one or looks like a scam pattern.
- 17 reply languages (all non-English wording is AI-written and NOT native-reviewed; see docs/languages.md).
- WhatsApp share, Telegram bot (off until a token is set), an evidence page and a ClaimReview feed.
- [Only list the items below after the owner has reviewed and deployed them: share-text fix for multi-claim forwards,
  honest incomplete-check wording, UNVERIFIED guidance panel, optional anonymous feedback flow, Vertex-based search.]
How AgentFoundry was used: **[Owner: write exactly what was done inside the AgentFoundry IDE, with the date and the commit
that came out of it. If nothing has been done yet, do not tick the confirmation below. See agentfoundry-task-brief.md.]**

## GitHub repository URL
https://github.com/pruthvig1998/sach-check (MIT licence)

## Demo URL
https://sachcheck.in  [plus a 2-3 minute video link if recorded; script in demo-script.md]

## Scale & severity of the problem  (DRAFT: every figure needs the owner's approval; sources in docs/problem-evidence.md)
Kantar-IAMAI counted 886 million active internet users in India in 2024, and 98% of them accessed the internet in Indic
languages. In the Reuters Institute's 2025 India survey, 53% of respondents named WhatsApp as the channel carrying the
biggest threat from false or misleading information, the highest of any market; that sample is mainly English-speaking, so
regional-language users are under-measured. IndiaSpend counted 33 deaths in 69 mob attacks over child-lifting rumours
between January 2017 and July 2018, with WhatsApp the named source in 19 cases. The Home Ministry told the Lok Sabha that
citizens lost Rs 22,845.73 crore to cyber fraud in 2024, against Rs 7,465.18 crore in 2023 (this figure is not attributed to
fake forwards). PIB Fact Check reports 2,913 fact checks to April 2026 but covers only central-government claims.
[Optionally delete the cyber-fraud sentence if misinformation-only wording is preferred. Do NOT add "English-only checking
leaves most users unserved" as a fact: it is an inference; no source measures it.]

## Deployment & impact data (optional field; honest status)
- Field-impact data: **none yet.** [If the owner runs the pilot: report only the responses actually collected, with
  denominators and the selection-bias note, from `scripts/pilot_report.py`; see pilot-protocol.md.]
- Public usage counters on /impact include testing and demo traffic and must not be quoted as user numbers.
- Evaluation: [Fill from the final clean run only: docs/evaluation.md and data/eval_summary.json. If no clean run exists, say
  so. Last degraded runs (not headline numbers): 31/79 exact with 0 overclaims, and a 53-case red team with 0 overclaims.]
- 4,545 automated tests pass on the current local main (commit 85ec45c); production runs an earlier commit until the owner
  approves a deploy.

## Track / category
Governance

## Contact email
[Owner's email]

## Confirmations (all three are required by the form)
- [ ] Built using AgentFoundry (AF), the official IDE: **do NOT tick unless it is true; see agentfoundry-task-brief.md**
- [ ] Our repository is public and includes a README with setup steps
- [ ] The demo link works and is accessible to judges  (re-test on the day)
