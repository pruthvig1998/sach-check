# Sach (सच · నిజం)

**Got a forward? Get the receipts.** Paste a viral WhatsApp-style message in English, Hindi, Telugu, Hinglish or Tinglish (Telugu in English letters). Sach splits it into claims, checks each against PIB and official sources, and returns a **cited verdict card** in the forward's own language (plus what it means in English), ready to paste back into the group. Every check is logged to a public evidence ledger.

- **Live:** https://sach-check-lilac.vercel.app
- **Track:** Governance · **License:** MIT · **Cost to run:** ₹0 (Vercel free, Gemini free tier, Brave free plan)

## Why it exists
Misleading forwards about government schemes, money and health spread in family groups faster than corrections do. The corrections exist (PIB Fact Check, ministry clarifications) but nobody reads a press release inside WhatsApp. Sach brings the correction to where the forward lives, in the language it was written in, with a link.

## How it works
1. **Split** the forward into atomic, checkable claims and tag each (scheme/money, health, news, other). Call-to-action fragments ("click the link") and abbreviations like `Rs.` / `रु.` / `రూ.` are handled.
2. **Search**, in priority order: **PIB first** (hand-seeded debunks, a local index of harvested PIB releases in `data/pib_index.jsonl`, the live RSS feed, and a PIB-scoped Brave query) → the wider official pool (`*.gov.in`, `*.nic.in`, `who.int`, `rbi.org.in`, `mygov.in`, `sansad.in`, NPCI) via keyword queries → fact-checkers (Alt News, BOOM, Vishvas News) as *secondary* evidence, queried only when nothing authoritative turned up. Duplicate URLs for the same PIB release are merged. Non-English claims are translated to English for search and judging; the ledger keeps the original wording.
3. **Judge** each fetched source: confirms / contradicts / partial / neither. The judge (Gemini) must **quote the exact sentence** it relies on, and the quote is verified verbatim against the page. A contradiction only counts if the page is itself a debunk or denial; a confirmation must contain the claim's numbers.
4. **Decide** with hard rules (below) and **reply** with a short card: verdict first, one line of why, the citation link.

### Verdict rules (hard, in code, tested)
| Verdict | Only when |
|---|---|
| **FALSE** | PIB or an official source directly contradicts the claim |
| **TRUE** | an official source directly confirms it, with the same numbers |
| **MISLEADING** | the core fact is real but numbers, dates or framing are distorted |
| **UNVERIFIED** | everything else. No evidence is never "false". Fact-checkers alone never decide a verdict. Conflicting official sources → UNVERIFIED. |

A citation appears only if the page was actually fetched (source, URL, date accessed). Overclaiming FALSE is the one failure we refuse to ship.

## Try these (checked against the live pipeline)
| Forward | Verdict |
|---|---|
| *Government is giving Rs 1000 to everyone under Corona Sahayata Yojana. Click the link to register.* | **FALSE** (PIB debunk, cited) |
| *The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore.* | **TRUE** (PIB release, cited) |
| *The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021 to March 2030.* (real scheme, wrong end date) | **MISLEADING** (PIB release, cited) |
| *सरकार कोरोना सहायता योजना के तहत सभी को 1000 रुपये दे रही है।* | **FALSE**, card in Hindi |
| *Central sarkaru employees retirement age ni 50 years ki taggistundi ani message vachindi* (Tinglish) | **FALSE**, card in Tinglish, with an English meaning |
| *Every household in India will receive a free solar-powered refrigerator next month.* | **UNVERIFIED** (invented; we say so plainly) |

## The website
Landing page, live checker with one-click examples, a reply-language selector (Auto, English, हिन्दी, తెలుగు, Tinglish) that works whatever the forward is written in, WhatsApp-style verdict card with **Copy**, **Share on WhatsApp** and **Download image**, per-claim citation table, public **evidence ledger** (filter + search), FAQ, dark mode, mobile-first layout, keyboard shortcut (Ctrl/Cmd+Enter), and a JSON API:

```bash
curl -s -X POST "https://sach-check-lilac.vercel.app/?format=json" \
  --data-urlencode "text=Government is giving Rs 1000 under Corona Sahayata Yojana" \
  --data-urlencode "lang=te"     # optional: auto (default), en, hi, te, tl
```
Checks read live sources and usually take 10 to 30 seconds (the function runs in Vercel's Mumbai region, close to the government sites). There is a best-effort rate limit (8 checks per minute per IP) and a 4000-character input cap.

## Evaluation (honest version)
31 claims: real PIB debunks (FALSE), real government announcements (TRUE), and invented controls (UNVERIFIED). Latest full run: **26/31 exactly right, 0 overclaimed FALSE, 0 wrong TRUE/FALSE**; all 5 misses were safe "unverified" abstentions. Full table including every miss: [`docs/evaluation.md`](docs/evaluation.md).

Read before citing: these numbers were measured at commit `dfbdaf2`, before the later hardening (second-opinion judge, subject matching, safe fallback); a fresh LLM-backed run is pending the reset of Gemini's free-tier quota (a fallback-mode run, which can only report clear PIB debunks, scored 0 overclaims and 0 wrong verdicts: [`docs/evaluation-fallback-run.md`](docs/evaluation-fallback-run.md)); the set is small; two labels were corrected after inspecting the evidence (disclosed in the report); many FALSE items paraphrase PIB debunk titles so recall there is optimistic; results move by a claim or two between runs because live search varies; the set contains no true MISLEADING examples (the MISLEADING demo above was checked separately).

## Retrieval evaluation (no AI involved)
Does retrieval put the known source page in front of the judge? For 26 eval claims with a known PIB source page: **24/26 combined**, 23/26 from live Brave search alone, and for the 11 pages that are in neither the hand-seeded list nor the harvested index, Brave alone found **10/11**. The local index (351 PIB releases, 132 of them debunks or clarifications, built with `scripts/harvest_pib.py`) is partly circular for the other items, since it was harvested from searches on the same topics. Details: [`docs/retrieval-evaluation.md`](docs/retrieval-evaluation.md).

## Data checkpoint (what actually worked)
`pib.gov.in` press-release pages (`PressReleasePage.aspx?PRID=`) fetch and parse. `pib.gov.in/factcheck.aspx` is only a Twitter embed and the RSS feed returns just the latest 20 items, so there is no scrapeable debunk archive. Debunks are therefore seeded by hand in `data/seed_debunks.json` (each fetched and parsed) and found live through Brave search of official domains.

## Run it yourself
```bash
pip install -r requirements-dev.txt
python -m pytest -q            # offline, recorded fixtures, no live web
python scripts/run_eval.py     # writes docs/evaluation.md and data/eval_summary.json
python scripts/eval_retrieval.py   # LLM-free: does retrieval surface the known source page? -> docs/retrieval-evaluation.md
python scripts/harvest_pib.py --max-queries 80   # grow the local PIB index (needs BRAVE_API_KEY)
python -m sach.web             # http://localhost:8080
```
Optional env (copy `.env.example` to `.env`): AI judge keys, tried in order with **automatic failover**: `GEMINI_API_KEY` (Google AI Studio free tier; several keys may be comma-separated), then `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY` (free tiers), then `ANTHROPIC_API_KEY` (paid, last resort). A key that runs out of quota is skipped for 5 minutes. `BRAVE_API_KEY` enables live search. Run `python scripts/check_llm.py` to verify every key and model with a live call and a quality probe. With no keys it still runs in a conservative heuristic mode: high precision, low recall, mostly UNVERIFIED.

Deploy: `vercel --prod` (entry point `api/index.py`, config in `vercel.json`); set the two keys as Vercel environment variables.

## Layout
```
sach/extract.py   claim splitting + domain tags      sach/verdict.py   hard verdict rules
sach/retrieve.py  PIB + Brave retrieval              sach/stance.py    quote/number/denial validation
sach/llm.py       Gemini/Claude judge + translate    sach/pipeline.py  orchestration with hard deadlines
sach/i18n.py      EN/HI/TE card strings              sach/site.py      website
sach/web.py       HTTP handlers, JSON API            tests/            60+ tests, no live web
```

## Known gaps
- **Free-tier quota.** The AI judge runs on free tiers, which can run out under heavy use. With several keys or providers configured it fails over automatically; when every one is out, Sach shows a "Limited mode" notice and only reports FALSE for a clear PIB debunk (never TRUE or MISLEADING).
- **Hindi and Telugu strings are human-written templates but have not been reviewed by a native speaker.** Do that before relying on them publicly.
- Live checks usually take 10 to 30 seconds. Every check has a 48-second budget inside Vercel's 60-second limit; a claim that runs out of time is reported as unverified, never guessed.
- The live ledger on Vercel is ephemeral (resets between instances); it ships with a starter set, and the repository is the permanent record.
- Translation for non-English claims can drift; numbers and quotes are still verified against the English page, but a mistranslated claim could be matched to the wrong source.
- Sach is not a government service and does not speak for PIB or any ministry.
