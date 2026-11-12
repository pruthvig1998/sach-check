# Sach (सच · నిజం)

**Got a forward? Get the receipts.** Paste a viral WhatsApp-style message in English, Hindi, Telugu, Hinglish or Tinglish (Telugu in English letters). Sach splits it into claims, checks each against PIB and official sources, and returns a **cited verdict card** in the forward's own language (plus what it means in English), ready to paste back into the group. Every check is logged to a public evidence ledger.

- **Live:** https://sach-check-lilac.vercel.app (an example: the site's address is configurable, see `SACH_SITE_URL` below)
- **Track:** Governance · **License:** MIT · **Cost to run:** ₹0 (Vercel free, Gemini free tier, Brave free plan)

## Why it exists
Misleading forwards about government schemes, money and health spread in family groups faster than corrections do. The corrections exist (PIB Fact Check, ministry clarifications) but nobody reads a press release inside WhatsApp. Sach brings the correction to where the forward lives, in the language it was written in, with a link.

## How it works
1. **Split** the forward into atomic, checkable claims and tag each (scheme/money, health, news, other). Call-to-action fragments ("click the link") and abbreviations like `Rs.` / `रु.` / `రూ.` are handled.
2. **Search**, in priority order: **PIB first** (hand-seeded debunks, a local index of harvested PIB releases in `data/pib_index.jsonl`, the live RSS feed, and a PIB-scoped Brave query) → the wider official pool (`*.gov.in`, `*.nic.in`, `who.int`, `rbi.org.in`, `mygov.in`, `sansad.in`, NPCI) via keyword queries → fact-checkers (BOOM, Vishvas News, Newschecker, Factly and other IFCN-verified outlets) as *secondary* evidence, queried only when nothing authoritative turned up. Duplicate URLs for the same PIB release are merged. Non-English claims are translated to English for search and judging; the ledger keeps the original wording.
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

## Tip jar (optional)
Tips have two routes. Both are optional and independent; set the environment variables for whichever you want, and the section only shows what is configured.

**1. Card / UPI checkout (Razorpay).** Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (use the `rzp_test_...` pair while testing, then your `rzp_live_...` pair once Razorpay has activated your account). The pay panel then shows "Pay ₹N by UPI or card". Flow: the browser asks `POST /?api=rzp-order` for an order (amount checked server-side, ₹1 to ₹10,000, converted to paise), Razorpay's `checkout.js` is loaded only when the button is tapped, and on success the browser sends the three returned values to `POST /?api=rzp-verify`, which checks the HMAC-SHA256 signature before anything is called paid. The key secret never leaves the server and never appears in a page. There is no SDK: it is a few stdlib HTTP calls in `sach/razorpay_pay.py`.
- **Webhook (optional but recommended).** In Razorpay's dashboard add a webhook to `https://<your-site>/?api=rzp-webhook`, choose a secret, and set the same value as `RAZORPAY_WEBHOOK_SECRET`. Events (`payment.captured`, `payment.failed`, `order.paid`, `refund.processed`) are verified against the raw body and acknowledged, so Razorpay stops retrying even if the payer closed the tab. Sach logs one non-personal line per event (event name, payment id, amount); it stores nothing, because the free Vercel deployment has no persistent storage.
- **Limits.** Tip orders are limited to 6 per minute per IP and verifications to 20, in their own buckets, so tipping never uses up anyone's fact-check allowance.
- **Cost.** No setup or monthly fee on Razorpay's standard plan; roughly 2% plus 18% GST per payment (check the current pricing page). Razorpay can see who paid, and the pay panel and privacy page say so.

**2. UPI QR code.** Set `SACH_UPI_ID` (and `SACH_UPI_NAME`, which must match the name your bank shows for that UPI ID; optionally `SACH_UPI_ID_ALT`, a second UPI address for the same bank account that payers can switch to with "Code not working? Try code B"). The QR is drawn on the server (PNG and SVG), the payer scans it inside their own UPI app (or, on a phone, saves the PNG and scans it from the gallery), and the money goes straight to your account with no fee. Your UPI ID never appears in the page's HTML or text.

**Why there are no "open my UPI app" buttons for a personal UPI ID.** In real testing, payment links (`upi://`, `gpay://`, `phonepe://`...) pointing at a personal UPI ID were rejected by the payer's bank or app (Google Pay showed "bank limit exceeded" even for ₹20), while scanning the same ID's QR worked. The cause is NPCI circular OC-76A (12 March 2024, effective 1 April 2024), which tells payer apps to disallow person-to-person payments started from a link ("intent" mode); QR payments are a different, allowed flow, and QR images saved to a gallery are capped at ₹2,000. This is a rule of the UPI network, not a bug in Sach, and no site code can get around it. So for a personal UPI ID the app buttons are hidden, `/?go=tip` and `/?view=pay` redirect to the tip section, and a short note explains why. Link payments only work for a **verified merchant** UPI ID (or through a payment gateway, which is what route 1 is). If you have a verified merchant ID, set `SACH_UPI_MERCHANT=1` to bring the app chooser (`/?view=pay`, with the apps' real icons and a custom-amount box) back.

Tips never affect verdicts (covered by tests), IDs and keys are read from the environment and never committed, and invalid values simply hide that route. Payers' UPI apps do show them your name and UPI ID before they confirm (that is UPI's own safety check).

**Policy pages.** `/?view=terms`, `/?view=privacy`, `/?view=refund` and `/?view=contact` (linked from every footer) are what payment gateways ask to see on a site. Edit the wording in `sach/legal.py`. Set `SACH_CONTACT_EMAIL` to show an email address; without it people are pointed to GitHub issues.

The app logos in the chooser (Google Pay, PhonePe, Paytm, BHIM) are the apps' own App Store icons, shown only so people can recognise which app a button opens. They are trademarks and copyrighted works of their owners, **not** covered by this repository's MIT license, and Sach is not affiliated with those companies; see `sach/assets/app_icons/NOTICE.md`. If an owner objects, delete that file and the tile falls back to a generic icon.

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
Optional env (copy `.env.example` to `.env`): AI judge keys, tried in order with **automatic failover**: `GEMINI_API_KEY` (Google AI Studio free tier; several keys may be comma-separated), then `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY` (free tiers), then `ANTHROPIC_API_KEY` (paid, last resort). A key that runs out of quota is skipped for 5 minutes. `BRAVE_API_KEY` enables live search, and `TAVILY_API_KEY` adds a second provider that takes over when Brave fails (Brave answers HTTP 402 once its prepaid credit runs out). Tavily's free plan gives 1,000 credits a month with no card ([source](https://docs.tavily.com/documentation/api-credits)); a basic search costs 1 credit. `SACH_SEARCH_ORDER=tavily,brave` changes the order. A provider that answers 402/401/403 is skipped for 6 hours, one that answers 429 for its `Retry-After` (5 to 600 s); timeouts and 5xx just move on to the next provider. **Search is never lost silently:** every result carries `search_status` (`ok`, `partial`, `down`, or `off` when no search key is set; `degraded` still means only "AI judge unavailable"). When search was `down` or `partial` the page says so, the result is not cached, `scripts/run_eval.py` marks the run as fallback and does not overwrite the headline numbers, and `scripts/red_team.py` prints the status. Run `python scripts/check_search.py` to test each search key with one small query and `python scripts/check_llm.py` to verify every key and model with a live call and a quality probe. With no keys it still runs in a conservative heuristic mode: high precision, low recall, mostly UNVERIFIED.

Deploy: `vercel --prod` (entry point `api/index.py`, config in `vercel.json`); set the two keys as Vercel environment variables.

**Site address.** Set `SACH_SITE_URL` (for example `https://sach.example.org`: https only, host only, no path or query; a trailing slash is ignored) when you move to a custom domain. It is used for canonical links, share previews (`og:` and Twitter tags), `robots.txt`, `sitemap.xml`, the report text and the scripts' default URL. Unset, Sach uses the request's own `Host` header, and falls back to `https://sach-check-lilac.vercel.app`. The old `*.vercel.app` address keeps working, so set `SACH_SITE_URL` to make the custom domain the canonical one.

## Layout
```
sach/extract.py   claim splitting + domain tags      sach/verdict.py   hard verdict rules
sach/retrieve.py  PIB + Brave retrieval              sach/stance.py    quote/number/denial validation
sach/llm.py       Gemini/Claude judge + translate    sach/pipeline.py  orchestration with hard deadlines
sach/i18n.py      EN/HI/TE card strings              sach/site.py      website
sach/web.py       HTTP handlers, JSON API            tests/            60+ tests, no live web
```

- **Check a screenshot.** `sach/ocr.py` + `POST /?api=ocr`: the browser shrinks an uploaded image, Gemini reads its text, and the text is only placed in the box for the person to edit before pressing Check (4 per minute per IP; the image and text are never stored or logged).

## Known gaps
- **Free-tier quota.** The AI judge runs on free tiers, which can run out under heavy use. With several keys or providers configured it fails over automatically; when every one is out, Sach shows a "Limited mode" notice and only reports FALSE for a clear PIB debunk (never TRUE or MISLEADING).
- **Hindi and Telugu strings are human-written templates but have not been reviewed by a native speaker.** Do that before relying on them publicly.
- Live checks usually take 10 to 30 seconds. Every check has a 48-second budget inside Vercel's 60-second limit; a claim that runs out of time is reported as unverified, never guessed.
- The live ledger on Vercel is ephemeral (resets between instances); it ships with a starter set, and the repository is the permanent record.
- Translation for non-English claims can drift; numbers and quotes are still verified against the English page, but a mistranslated claim could be matched to the wrong source.
- **Tips are not recorded by Sach.** Razorpay's dashboard is the record of who paid what; the webhook only logs a non-personal line, because the free Vercel deployment has no persistent storage. A "total raised" counter or thank-you wall would need a small database first.
- Sach is not a government service and does not speak for PIB or any ministry.
