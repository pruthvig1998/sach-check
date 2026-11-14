# Plan: L3 (fact-check corpus) and L4 (bigger PIB index)

Status: proposed 14 Nov 2026, nothing built. **[you]** marks a decision for the owner. Builds on `docs/plans/no-llm-layers.md`; the same fixed rules apply (no new route to TRUE or FALSE, one switch per layer, the permanent differential test, no changes to verdict, stance or judge code).

## What I checked today, and what it changes
| Check | Result | Consequence |
|---|---|---|
| PIB RSS feed | Works through our own fetcher: 200 and 20 items a feed. The same URL returned **403** to a custom-named client. | The feed is reachable but fragile: a firewall is sensitive to the client. Keep using `sach/fetch.py`; do not change its identity. |
| PIB API | None. Feeds exist by region, module and language; an archive exists at archive.pib.gov.in with no documented API. | Daily feeds give only the newest items. A backfill needs a polite crawler of the archive. |
| SQLite full-text search (FTS5) | Available in the local Python (SQLite 3.54). **Not yet confirmed on Vercel's runtime.** | First task is a preview deployment that checks it. If it is missing, fall back to a plain inverted index in a JSON file. |
| Deployment | `vercel.json` bundles `{sach,data}/**` into the function. Our PIB data is 0.66 MB today and `index.load` reads the whole file into memory. | A 50,000-record JSONL would cost roughly 90 MB of memory per instance. Use a read-only SQLite file instead (reads lazily from disk). |
| ClaimReview markup on publisher pages | Article pages from **Alt News, Vishvas News and NewsMeter** contain ClaimReview JSON-LD and loaded with our normal client. Factly's sample article had none. **BOOM and Factly returned 403** to a non-browser client. Newschecker's robots file mentions bots by name (not fully read). | Crawling works for three outlets, is blocked for two, and is unclear for one. Do not try to get around a block. |
| Google Fact Check API | Already returns these same records (claim, rating, publisher, URL), English only. Its storage terms I could not confirm (it points to Google's general API terms). | The cheapest corpus is not a crawl but **keeping what the API already returns**, once someone has read the terms. |

## L4: a bigger PIB index (the larger retrieval lever)
**Why:** in the latest evaluation the expected PIB page was retrieved for 18 of 39 unseeded claims (46%) and 28 of 29 seeded ones; our local index holds only 358 releases (`data/pib_index.jsonl`). The right page is often simply not found.

**Design**
1. **Two stores, strictly separated.** Keep `pib_index.jsonl` exactly as it is: it feeds the match layer, which only accepts debunk-titled records (`_STRICT`). Add a **new retrieval-only file `data/pib.sqlite`** holding all releases. It is never read by the match layer, so growing it cannot make an ordinary release count as a debunk.
2. **File:** table `releases(prid, date, lang, title, excerpt, url)` plus an FTS5 table over title and excerpt, ranked with BM25. Excerpt capped near 1,200 characters (title and first paragraphs), as the current index does.
3. **Build:** `scripts/harvest_pib_feeds.py` reads the RSS feeds (English, Hindi, regional), then fetches each release once through `sach/fetch.py` at one request every two seconds, and writes the file. A separate backfill pass walks the archive by month, resumable and capped per run.
4. **Use:** `PibRetriever.search` asks the SQLite file for candidate release numbers (replacing the word-overlap score), then fetches the live pages as it does today. Judging, stance checks and verdict rules are untouched.
5. **Size gate:** budget 60 MB for the file (about the latest 12 to 18 months of English and Hindi). If the first build exceeds it, shrink the window, not the safeguards.
6. **Refresh:** weekly rebuild and a commit only when the file changed. Because data is bundled, a new file needs a deploy. **[you]** choose: manual weekly deploy, or connect the repository to Vercel's auto-deploy.

**Measure:** run `scripts/eval_retrieval.py` before and after. Baseline: expected page retrieved for 18 of 39 unseeded claims. Target: at least 60% unseeded retrieval with no change to red-team results (53 cases, 0 overclaims) and no new wrong answers in the evaluation.

**Size and risk:** large (2 to 3 days), medium risk (bundle size, cold start, FTS5 on Vercel). Switch: `SACH_PIB_FTS=0`.

## L3: a local fact-check corpus (revised)
My earlier plan was to crawl the publishers. The research says that is the weaker option. Revised:

**L3a (recommended): keep what the API already returns.** Every ClaimReview the Google Fact Check API returns (claim, rating, publisher, review URL, date, language) is written to our store, then matched locally with the existing `check_pair` guards. Seed queries come from two places: about 100 evergreen scam and scheme topics, and the claims in our ledger that ended UNVERIFIED. Gains: survives an API outage or quota ceiling; matches beyond the top 10 results per query; no crawling and no etiquette issues. **Blocked on one thing: someone must read Google's API terms on storing results.** If they forbid it, L3a becomes "cache each answer for the short period the terms allow", which still helps but is smaller.

**L3b (only with permission): read the publishers' own markup.** Technically possible for Alt News, Vishvas News and NewsMeter. **[you]** I would email each outlet first (they are fact-checkers and welcome syndication of ClaimReview), and skip BOOM, Factly and anyone who blocks us. Never use a disguised client.

**Measure:** the number of claims in the 79-claim set (and in a held-out list of real ledger claims) that now match a stored fact-check, with 0 wrong answers; compare with the baseline of 8 of 68 answered with no model and search on.

**Size and risk:** L3a small (1 day). L3b medium (2 days plus outreach), higher risk. Switches: `SACH_CR_STORE=0`.

## Order
1. Preview deployment that proves FTS5 on Vercel (a one-hour spike). If it fails, change the L4 design before writing it.
2. L3a, once the terms are read.
3. L4 feeds first (small, daily), then the SQLite file, then the archive backfill.
4. L3b only after replies from the outlets.

## Decisions for you
- **[you]** Is anyone able to read Google's Fact Check API terms on storing results, or shall I summarise them for you to check?
- **[you]** Email Alt News, Vishvas News and NewsMeter for permission to read their ClaimReview markup?
- **[you]** Weekly manual deploy, or connect the repository to Vercel auto-deploy for data refreshes?
- **[you]** Is a 60 MB data file acceptable in the bundle?
