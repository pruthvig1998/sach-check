# Sach (सच · నిజం)

**Got a forward? Get the receipts.** Paste a viral WhatsApp-style message in English, Hindi, Telugu or Hinglish. Sach splits it into claims, checks each against PIB and official sources, and returns a **cited verdict card** in the forward's own language, ready to paste back into the group. Every check is logged to a public evidence ledger.

- **Live:** https://sach-check-lilac.vercel.app
- **Track:** Governance · **License:** MIT · **Cost to run:** ₹0 (Vercel free, Gemini free tier, Brave free plan)

## Why it exists
Misleading forwards about government schemes, money and health spread in family groups faster than corrections do. The corrections exist (PIB Fact Check, ministry clarifications) but nobody reads a press release inside WhatsApp. Sach brings the correction to where the forward lives, in the language it was written in, with a link.

## How it works
1. **Split** the forward into atomic, checkable claims and tag each (scheme/money, health, news, other). Call-to-action fragments ("click the link") and abbreviations like `Rs.` / `रु.` / `రూ.` are handled.
2. **Search**, in priority order: PIB (hand-seeded debunks + live RSS) → official domains (`*.gov.in`, `*.nic.in`, `who.int`) via Brave search → fact-checkers (Alt News, BOOM, Vishvas News) as *secondary* evidence. Non-English claims are translated to English for search and judging; the ledger keeps the original wording.
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
| *…with an outlay of Rs 50,000 crore.* (real scheme, wrong number) | **MISLEADING** |
| *सरकार कोरोना सहायता योजना के तहत सभी को 1000 रुपये दे रही है।* | **FALSE**, card in Hindi |
| *కేంద్ర ప్రభుత్వం ఉద్యోగుల పదవీ విరమణ వయస్సును 50 సంవత్సరాలకు తగ్గిస్తుంది.* | **FALSE**, card in Telugu |
| *Every household in India will receive a free solar-powered refrigerator next month.* | **UNVERIFIED** (invented; we say so plainly) |

## The website
Landing page, live checker with one-click examples, WhatsApp-style verdict card with **Copy**, **Share on WhatsApp** and **Download image**, per-claim citation table, public **evidence ledger** (filter + search), FAQ, dark mode, mobile-first layout, keyboard shortcut (Ctrl/Cmd+Enter), and a JSON API:

```bash
curl -s -X POST "https://sach-check-lilac.vercel.app/?format=json" \
  --data-urlencode "text=Government is giving Rs 1000 under Corona Sahayata Yojana"
```
Checks read live sources and take roughly 15 to 40 seconds. There is a best-effort rate limit (8 checks per minute per IP) and a 4000-character input cap.

## Evaluation (honest version)
31 claims: real PIB debunks (FALSE), real government announcements (TRUE), and invented controls (UNVERIFIED). Latest full run: **26/31 exactly right, 0 overclaimed FALSE, 0 wrong TRUE/FALSE**; all 5 misses were safe "unverified" abstentions. Full table including every miss: [`docs/evaluation.md`](docs/evaluation.md).

Read before citing: the set is small; two labels were corrected after inspecting the evidence (disclosed in the report); many FALSE items paraphrase PIB debunk titles so recall there is optimistic; results move by a claim or two between runs because live search varies; the set contains no true MISLEADING examples (the MISLEADING demo above was checked separately).

## Data checkpoint (what actually worked)
`pib.gov.in` press-release pages (`PressReleasePage.aspx?PRID=`) fetch and parse. `pib.gov.in/factcheck.aspx` is only a Twitter embed and the RSS feed returns just the latest 20 items, so there is no scrapeable debunk archive. Debunks are therefore seeded by hand in `data/seed_debunks.json` (each fetched and parsed) and found live through Brave search of official domains.

## Run it yourself
```bash
pip install -r requirements-dev.txt
python -m pytest -q            # offline, recorded fixtures, no live web
python scripts/run_eval.py     # writes docs/evaluation.md and data/eval_summary.json
python -m sach.web             # http://localhost:8080
```
Optional env (copy `.env.example` to `.env`): `GEMINI_API_KEY` (Google AI Studio free tier, enables the stance judge and translation), `BRAVE_API_KEY` (live search), `ANTHROPIC_API_KEY` (alternative judge). With no keys it still runs in a conservative heuristic mode: high precision, low recall, mostly UNVERIFIED.

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
- **Hindi and Telugu strings are human-written templates but have not been reviewed by a native speaker.** Do that before relying on them publicly.
- Live checks take 15 to 40 seconds and can approach Vercel's 60-second function limit on slow claims.
- The live ledger on Vercel is ephemeral (resets between instances); it ships with a starter set, and the repository is the permanent record.
- Translation for non-English claims can drift; numbers and quotes are still verified against the English page, but a mistranslated claim could be matched to the wrong source.
- Sach is not a government service and does not speak for PIB or any ministry.
