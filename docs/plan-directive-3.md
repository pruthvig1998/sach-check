# Plan: Directive 3 and beyond (written 12 Nov 2026)

Freeze target: evening of 14 Nov. Everything stays at $0. The hard verdict rules in `sach/verdict.py` do not change.

## What the review found

| # | Finding | Consequence | Fix |
|---|---|---|---|
| 1 | The ledger is a file on Vercel's temporary disk | A verdict cache and impact counters would reset on every restart | Small storage layer: file by default, Upstash Redis (free, REST) when its two env vars are set |
| 2 | Evaluation has 31 claims, nearly all English | No per-language accuracy to show | Expand to about 50 with at least 5 Hindi and 5 Telugu forwards; per-language table; commit hash in the report |
| 3 | A verdict shows citations but not the reasoning path | A judge cannot audit a verdict from the card alone | Per-source trace (source, URL, fetched-at, stance, rule fired) stored with every verdict |
| 4 | Injection resistance is covered by scattered tests only | No published red-team evidence | Fixture file, offline tests, live script, `docs/red-team.md` |
| 5 | Fact-checker tier knows 3 sites; no fact-check search | Many UNVERIFIED results give the reader nothing to follow up | Optional Google Fact Check Tools retriever (secondary tier only) and a verified list of IFCN signatories |
| 6 | Banks moved to the regulated `.bank.in` zone; several statutory bodies are off `gov.in` | Real official pages are ignored | Verified additions to the official list, each documented in `docs/sources.md` |
| 7 | Directive lists `pibfactcheck@gmail.com` | Could not be confirmed on an official page | Report flow uses only channels confirmed on pib.gov.in at build time |
| 8 | Share image is a plain text canvas | Weak for WhatsApp sharing | Proper verdict card PNG (verdict, one line of why, Sach URL) |
| 9 | Rate limiter is per server instance | Best-effort only | Move counters to the storage layer once Upstash is connected (later) |
| 10 | Hindi, Telugu and Tinglish strings are unreviewed | Brief requires native review | Needs a person; cannot be automated |

## Work packages

Each package is built by a Sonnet 5.5 agent in its own git worktree, with its own files, then reviewed and merged.

### Wave 1 (parallel)
- **A. Cache, trace, storage.** `sach/store.py`, `sach/cache.py`, `sach/pipeline.py`, `sach/ledger.py`, `sach/models.py`, trace UI in `sach/site.py`. Repeat forwards return the stored verdict with a "first checked on" date. Decisive verdicts are kept 7 days, UNVERIFIED 6 hours, limited-mode and timed-out results never. Cache hits are counted separately.
- **B. Evaluation v2.** `data/eval_set.json`, `scripts/run_eval.py`. Every new claim is verified against a page fetched during the work. Per-language breakdown, commit hash, resume after a quota stop, earlier run archived as superseded.
- **C. Red team.** `data/red_team.json`, `tests/test_redteam.py`, `scripts/red_team.py`, `docs/red-team.md`. Embedded instructions, fabricated PIB quote, altered amount, Telugu and Hindi forwards with injected English, lookalike domains, a malicious judge model.
- **D. Sources.** `sach/fetch.py`, `sach/retrieve.py`, `sach/factcheck_api.py`, `docs/sources.md`. Verified official additions, IFCN fact-checker list, optional Fact Check Tools retriever.

### Wave 2 (after wave 1 merges)
- **E. Impact page and evidence snapshot.** `/impact` computed from the ledger and counters; `scripts/snapshot_impact.py` writes `evidence/impact-2026-11-14.json`.
- **F. Report to PIB and share image.** Copy-ready report on FALSE verdicts (Sach never sends anything). Verdict card PNG.

### Wave 3
- **G. README to top-tier standard.** Architecture diagram, rules table, evaluation with per-language numbers, limitations, live links.
- **H. Extras if time allows.** Install-as-app with Android share target (share a forward from WhatsApp straight into Sach); screenshot input; scam red-flag advisory that never changes a verdict.

### Final (run by the lead session, not delegated)
Full evaluation on the commit that is deployed, live red-team run, deploy, end-to-end check with a real fake forward, hand-back report.

## Needs the owner
- Create a free Upstash Redis database and add its two values to Vercel (commands will be provided). Without it the cache and impact numbers work but reset when the server restarts.
- Optional: a Google Cloud API key for the Fact Check Tools API (no billing needed).
- Native-speaker review of Hindi and Telugu strings and of the new Hindi and Telugu evaluation forwards.
