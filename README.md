# Sach (सच · నిజం)

Paste a viral forward (English, Hindi, Telugu or Hinglish). Sach splits it into claims, looks for official evidence, and returns a **cited verdict card** in the forward's own language, ready to paste back into the group. Every check is logged to a public evidence ledger. MIT licensed. Track: Governance.

## Verdict rules (hard, tested)
- **FALSE** only when a PIB debunk or an official source directly contradicts the claim.
- **TRUE** only when an official source directly confirms it.
- **MISLEADING** when the core fact exists but numbers, dates or framing are distorted.
- Otherwise **UNVERIFIED**. Absence of evidence is never FALSE. Fact-checkers (Alt News, BOOM, Vishvas News) are labelled secondary and can never produce FALSE or TRUE alone. Conflicting official sources give UNVERIFIED.
- A citation appears only if the page was actually fetched (source, URL, date accessed).

## Data checkpoint (Nov 12, from this Mac)
Worked: `pib.gov.in` press-release pages (`PressReleasePage.aspx?PRID=`) fetch and parse; RSS fetches; `factcheck.pib.gov.in` is 200.
Did not work as a source: `pib.gov.in/factcheck.aspx` is only a Twitter embed (no debunk list); the RSS feed returns just the latest 20 items whatever the parameters.
So debunks come from a hand-seeded list (`data/seed_debunks.json`, found via web search, each fetched and parsed) plus an optional search provider. End-to-end on 3 claims: known fake policy forward -> FALSE with PIB citation; health myth -> UNVERIFIED (no matching PIB page seeded); genuine announcement -> UNVERIFIED (heuristic cannot confirm; needs LLM).
A first run wrongly returned FALSE on the genuine claim; fixed and covered by regression tests.

## Setup
```
pip install -r requirements.txt
python -m pytest -q          # offline, recorded fixtures
python scripts/run_eval.py   # writes docs/evaluation.md
python -m sach.web           # http://localhost:8080
```
Optional env (see `.env.example`): `ANTHROPIC_API_KEY` enables LLM stance judgement; `BRAVE_API_KEY` enables live search of official domains then fact-checkers.

## Current status (Nov 12, 2026)
Running in **heuristic mode**: high precision, low recall, so most checks return UNVERIFIED. Live retrieval uses PIB press releases plus Brave search of official domains and fact-checkers. A Gemini free-tier stance judge and a Vercel deployment are in progress. Nothing here has cost money: no Anthropic credits, no GCP billing.

## Known gaps
- Hindi/Telugu card strings are fixed templates but **not yet reviewed by a native speaker**; do that before the demo.
- Without an LLM key, stance detection is a conservative heuristic: high precision, low recall (most things become UNVERIFIED).
- Evaluation set is 6 claims, not 100+ (see `docs/evaluation.md`).
- Not yet deployed (Vercel, in progress).
