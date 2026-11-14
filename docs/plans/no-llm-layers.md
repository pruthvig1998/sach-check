# Plan: cheap deterministic layers that answer without a language model

Status: proposed 14 Nov 2026, nothing built. Decisions for the owner are marked **[you]**.

## Why
Measured today (`docs/research/no-llm-measurement-2026-11-14.md`): with no model Sach answered 5 to 8 of 68 true-or-false claims, all FALSE, with 0 wrong answers. The live site's judge costs about ₹1 to ₹2 per check and fails when free tiers run out. Every question answered earlier in the cascade is a question that costs nothing and cannot fail.

**What these layers can and cannot do.** They answer claims that were already checked by a human (PIB, a fact-checker) or that match a known pattern. They cannot judge a brand-new claim. That still needs a model, and nothing here changes that. They also cannot produce TRUE on their own; TRUE needs an official source read by a judge.

## Fixed rules for everything below
1. **No new route to TRUE or FALSE.** The only decisive answers from these layers are the ones the match layer already allows today: a published verdict, attributed to its author, passing the existing `check_pair` rules in `sach/match.py`.
2. **The show-only layer (L2) never carries a verdict.** The result stays UNVERIFIED.
3. **Every layer sits behind its own switch, default off,** so any of them can be turned off in production by changing one environment variable.
4. **A permanent differential test** (new, committed in `tests/`): run the same claims with a layer off and on. The layer may turn an UNVERIFIED into an attributed match. It may never change a decisive verdict, and it may never create TRUE or FALSE from nothing. Last time this kind of harness lived in a scratch folder and was lost; this one goes in the repo.
5. No em dashes and no verdict logic touched in `sach/verdict.py`, `sach/stance.py` or `sach/llm.py`.

## The layers, in the order I would build them
| # | Layer | What it does | Files | Size | Risk |
|---|---|---|---|---|---|
| L0 | **Boilerplate strip + near-duplicate cache** | Before the cache key is made, remove WhatsApp wrapper text ("Forwarded many times", "please share", greetings, emoji runs). Then, if the exact key misses, compare the claim to recent cached claims on the same words, requiring the same figures, the same negation and the same distinctive words (the same guards as `check_pair`). A hit returns the cached answer, marked as a near match. | `sach/cache.py` (`normalise`, `lookup`), `sach/match.py` (reuse guards) | S | Low |
| L1 | **PIB Fact Check Telegram poller** | A small script reads the public channel (`t.me/s/PIB_FactCheck`, plain HTTP, paged) politely and appends debunk posts to the PIB posts file used by the match layer, replacing the unofficial fxtwitter ingest. Same acceptance rules (`POST_MIN_JACCARD`). | new `scripts/ingest_pib_telegram.py`, `sach/pibposts.py` | S to M | Low |
| L2 | **"What official sources say" (show-only)** | When a live check ends UNVERIFIED, show up to 3 retrieved official pages with the sentences closest to the claim highlighted (`sach/excerpt.py` already finds them). Heading: not a verdict, official pages that mention related things. No stance, no label. | `sach/honesty.py` (`unverified_panel`), `sach/site.py`, `sach/i18n.py` (strings in English, Hindi and Telugu) | M | **Medium: wording.** A reader could take a related sentence as confirmation. Needs the copy reviewed and tests that no verdict word appears. |
| L3 | **Own ClaimReview harvest** | Read the public fact-check markup (schema.org ClaimReview) from the pages of Alt News, BOOM, Factly, Vishvas, Newschecker and similar, through their sitemaps or feeds, keeping claim text, rating, date and URL only. Feeds the existing matcher. Reduces dependence on one API. | new `scripts/ingest_claimreview.py`, `data/claimreview.jsonl`, `sach/match.py` | M | Medium: etiquette and terms. Low volume, robots respected, attribution always shown. **[you]** decide whether to email the outlets first. |
| L4 | **Bigger PIB index with real ranking** | Daily harvest of PIB RSS (regional languages too) plus a backfill from the archive into a read-only SQLite full-text index (BM25 ranking), replacing the 358-record JSONL. Addresses retrieval misses such as the RPF recruitment claim. | new `scripts/harvest_pib.py`, `sach/index.py` | L | Medium: size and cold start on Vercel. Measure first. |
| L5 | **Official scam advisories as references** | A small hand-reviewed list (RBI, NPCI, I4C, TRAI) of scam patterns with the official guidance and link, shown next to the scam-pattern box. Reference only, no verdict. | `sach/scamsigns.py` or new data file | S, content heavy | Low |

**Out of scope for now:** image matching (perceptual hashing plus OCR; needs a decision on OCR and moves away from the current model-based image reader) and any change to the non-English path. Matching a non-English claim to an English fact-check still needs a cheap translation call, which is not the expensive judge step.

## How we will know it worked
- **No-LLM answer rate:** rerun the two configurations from today's measurement. Baseline: 5 of 68 (pure local) and 8 of 68 (search on). Target: at least double with **0 wrong answers**.
- **Share of live checks that never reach a judge:** report from the ledger, split into organic and test traffic once traffic classes exist.
- **Safety:** red team stays at 53 cases with 0 overclaims. The differential test above passes. The full suite passes.
- **L2 specifically:** a small reading test with 5 to 10 real people ("does this page tell you the claim is true?"). If more than a few say yes, change the wording or drop L2.

## Rollout
1. **Until 5 Dec (judging):** design, offline scripts and tests only. Nothing is deployed to production unless it is behind a switch that is off.
2. **Preview deployments** (Vercel) for L2 wording and L4 cold start, never the production alias.
3. **After judging:** turn layers on one at a time, in order, with the status page and the ledger watched for a day each. Rollback is one environment variable.

## Decisions for you
- **[you]** Build offline now and deploy after 5 Dec, or deploy earlier behind switches that stay off?
- **[you]** Comfortable reading the public PIB Telegram channel at low volume (it is a public web page; I have not read Telegram's terms for automated reading, and would do that first)?
- **[you]** Email the fact-checkers before harvesting their markup, or rely on their public syndication markup and keep volume tiny?
- **[you]** Is the "what official sources say" panel worth the wording risk, or should L2 wait for a native-speaker review of the new strings?

## Estimated effort (my build time, not calendar time)
L0 half a day. L1 half a day. L2 one day plus review. L3 one to two days. L4 two to three days. L5 half a day plus content review.
