# Sach: toward unlimited checks, more official sources, fewer UNVERIFIED answers

Research date 14 Nov 2026. Method: search to find pages, then read primary pages through Obscura (v0.2.7). Where Obscura could not render a page (Google's Gemini docs, a JS single-page app; the Telegram web preview) I fell back to a plain HTTP fetch and say so. **Confidence key:** P = read from the primary source today; V = vendor or third-party blog, treat as a claim; M = measured by me on our own data or site today; I = my inference.

## 1. The three findings that change the plan

1. **Most "UNVERIFIED" on the live impact page is not real-user abstention (M).** The public ledger has 309 rows but only 139 unique claims. 120 rows are non-Latin-script (translated evaluation claims, our own test traffic), and 107 of those are UNVERIFIED. The 79% headline is dominated by repeats and tests. We cannot yet say what real users experience. The unmerged pilot branch already has the fix (traffic classes organic / pilot / test).
2. **When providers are healthy, the pipeline works far better than our evaluation numbers suggest (M).** Five unseeded English claims run live today: 4 correct, 1 UNVERIFIED. That one was a retrieval miss (the exact PIB release was never found). The 16/79, 29/79 and 32/79 runs were mostly degraded by judge and search failures on free tiers.
3. **Adding X or LinkedIn is not the main lever.** In the latest run, for the 68 claims labelled TRUE or FALSE, the expected source page was retrieved for 46 (68%). Misses were mostly retrieval, and **non-English claims do much worse**: on the 39 claims that completed without failures, English was correct on 7 of 21, every other language on 2 of 18 (M, small sample). LinkedIn is closed to us by its terms (section 3). X is possible but costly in effort and compliance, and PIB Fact Check's own Telegram channel is a simpler official feed.

## 2. "Unlimited checks": what it really takes

Truly unlimited and free is not possible for the live layer, because each live check calls AI judges and web search. What can be made effectively unlimited is the layers that need no AI call: the cache and the match layer.

**What a live check costs (I, from our prompt sizes and P prices).** Up to 8 sources are judged per claim in parallel (`sach/pipeline.py`). Each call is about 1,100 input and 300 output tokens (my estimate). That is about 10k in and 3k out per claim.
- Gemini 3.1 Flash-Lite, paid: $0.25 in / $1.50 out per 1M tokens (P, [Google pricing](https://ai.google.dev/gemini-api/docs/pricing)). About **$0.007 per claim** for the judges.
- Search: Serper about $1 per 1,000 queries (V), so roughly $0.004 per check. Grounded search via Gemini is $14 per 1,000 after 5,000 free a month, capped at 1,500 a day (P). Use Grounded sparingly.
- **About $0.01 to $0.02 (roughly ₹1 to ₹2) per live check.**

| Live checks per day | Approx. monthly cost | Note |
|---|---|---|
| 100 | $30 to $60 | within a small credit |
| 1,000 | $300 to $600 | needs real funding |
| 10,000 | $3,000 to $6,000 | only viable with 60%+ cache hits |

**Why the free tiers keep failing (P).** Groq's free plan gives `gpt-oss-120b` 30 requests a minute, 1,000 a day, and **200,000 tokens a day** ([Groq limits](https://console.groq.com/docs/rate-limits)). At about 13k tokens a claim that is roughly 15 claims a day. Cloudflare Workers AI's free allowance is 10,000 Neurons a day ([Cloudflare](https://developers.cloudflare.com/workers-ai/platform/pricing/)). Google no longer publishes per-model free-tier numbers on its rate-limit page (V: the page now points to AI Studio), and it says RPD limits reset at midnight Pacific time (P). Free tiers cannot carry a public site.

**What to do, in order of payoff:**
1. **Pay for one reliable judge.** Put Gemini 3.1 Flash-Lite on a billing account (Tier 1 needs only an active billing account, P) and keep free providers as fallbacks only. This alone should fix most "degraded" results.
2. **Cache and dedupe harder.** Our cache hit rate is 8%, but viral forwards repeat. Normalise the claim and cache the verdict. Semantic caching reportedly cuts LLM cost 40 to 73% (V, vendor blogs). For fact-checking the danger is serving a cached verdict for a claim that differs in one number or a negation, so use a strict similarity threshold, require the same figures and dates, and re-check high-stakes cases (I).
3. **Pre-fill the match layer** so common claims never reach an LLM (see section 3).
4. **Batch and per-IP limits.** Gemini's Batch tier is cheaper for non-urgent work (P, it has its own price row). Keep a per-IP and per-day fair-use limit so one visitor cannot drain the budget. "Unlimited for people, capped for abuse" is the honest framing.
5. **Funding.** The Google for Startups Cloud Program offers credits to eligible companies (V; it needs a company website and a matching email domain), and the India accelerator's 2026 applications are closed (V). We found no evidence of hackathon Gemini credits. Ask the Code for a Billion organizers directly.
6. **Reduce calls per claim only with evaluation.** Judging fewer sources per claim would cut cost about 60%, but it changes judging behaviour and must be measured against the red-team set first (I).

## 3. More official sources

| Source | Verdict | Why |
|---|---|---|
| **PIB Fact Check Telegram channel** (`t.me/PIB_FactCheck`) | **Best new feed** | Official PIB channel. A plain HTTP fetch of `t.me/s/PIB_FactCheck` returned 19 posts spanning 4 weeks, with paging back in time (M). Needs a polite poller and a check of Telegram's terms. |
| **PIB releases at scale** | **Biggest retrieval lever** | Our local index holds only 358 releases (M). PIB has RSS feeds by region, module and language but **no official API** (P/V, [PIB RSS](https://www.pib.gov.in/ViewRss.aspx)), and an archive at archive.pib.gov.in. Harvesting RSS daily plus a backfill would multiply coverage. |
| **Google Fact Check Tools API** (already used) | Keep, expand queries | I tested 20 Indian-claim topics in English and Hindi: 20 of 40 queries returned results from Alt News, The Quint, Factly, NewsMeter, BOOM, NewsMobile, India Today, Vishvas (M). **All 63 reviews were English**, so Indian-language coverage is thin. |
| **X (Twitter)** | Possible, not first | Pay-per-use: reads about $0.005 each (V; the official page says rates are in the Developer Console, P). Watching 10 official accounts is cheap in dollars. The cost is compliance: the Developer Policy requires stored posts to be kept current and deleted when deleted on X, and redistribution is limited to Post IDs (P, [X policy](https://docs.x.com/developer-terms/policy)). **Note:** our current X-post ingest uses a third-party reader (fxtwitter), which is outside X's official API (`sach/pibposts.py`). Low volume, but worth moving to Telegram or the official API. |
| **LinkedIn** | **No** | The User Agreement prohibits scrapers, crawlers and bots, including copying profiles and other data (P, [LinkedIn user agreement](https://www.linkedin.com/legal/user-agreement)); the API is partner-gated (V). Government accounts there post little that PIB does not already publish. |
| **myScheme** (scheme facts) | Cautious yes | Official portal of 4,000+ schemes (V). **No official API**, and its copyright page asks for authorization to reproduce material (V). Ask NeGD (support address on the portal) before ingesting. |
| **Regulator advisories** (RBI, NPCI, TRAI, CERT-In, I4C) | Yes, curated | Scam forwards are a large share of what people paste. A small hand-checked set of official advisories ("RBI never asks for..." type guidance) lets Sach answer scam patterns with a citation instead of UNVERIFIED. `.gov.in` and `.bank.in` hosts are already trusted (`docs/sources.md`). Needs a per-item review. |
| **Parliament Q&A (sansad.in)** | Maybe | Authoritative for numbers, but no API found. Defer. |

**Two things that do not work:** Google's Custom Search JSON API is closed to new customers and shuts down 1 Jan 2027 (V, [Firecrawl](https://www.firecrawl.dev/blog/google-search-json-api-alternative)). And Vertex AI Search **website** data stores need domain verification, which we cannot do for pib.gov.in (P, [Google docs](https://docs.cloud.google.com/generative-ai-app-builder/docs/domain-verification)). That is why our experimental data store stayed at 0 documents. We deleted it.

## 4. Reducing UNVERIFIED (ranked)

Do not loosen the verdict rules: an overclaimed FALSE is the failure we refuse to ship. The honest levers are evidence, retrieval and reliability.

1. **Reliability first (cheap).** Pay for one judge (section 2). Re-run the 79-claim evaluation after, to get a real baseline.
2. **Grow the local PIB index** from 358 to tens of thousands of releases (RSS plus archive), keyed by title and excerpt. Retrieval misses were the clearest failure in the unseeded claims (M). The RPF recruitment claim failed this way.
3. **Fix the non-English path.** Add an evaluation slice per language, and test translate-to-English-then-search against searching in the original language. Research suggests strong English embeddings on translated text often beat multilingual models, and lexical baselines stay competitive on a small budget (V, SemEval 2025 Task 7 papers, [overview](https://arxiv.org/pdf/2505.10740v1)). Try BM25 plus a translated query first; it costs little.
4. **Add the PIB Fact Check Telegram feed and curated scam advisories** to the match layer, which answers with no AI call.
5. **Separate real users from tests** (traffic classes) so the public numbers mean something, then report abstention on organic traffic only.
6. **Embeddings for claim matching** against all collected fact-checks (the SemEval task is exactly this: finding previously fact-checked claims across languages). Bigger build, do after 1 to 5.

Many forwards have no official source at all (opinions, local events, rumours). For those UNVERIFIED is the correct answer, and no source expansion will, or should, change it.

## 5. Suggested order

1. Paid Gemini judge plus one clean evaluation run (days, low risk).
2. Traffic classes, so public numbers separate organic from test.
3. PIB RSS harvester and larger local index.
4. Telegram PIB Fact Check poller into the match layer.
5. Per-language evaluation and the translated-query experiment.
6. Curated scam advisories.
7. X official API only if budget and compliance appetite exist. LinkedIn: no.

## Sources
- Gemini pricing and rate limits (P): https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/rate-limits
- Groq rate limits (P/V): https://console.groq.com/docs/rate-limits
- Cloudflare Workers AI pricing (P): https://developers.cloudflare.com/workers-ai/platform/pricing/
- X API pricing page (P) https://docs.x.com/x-api/getting-started/pricing and Developer Policy (P) https://docs.x.com/developer-terms/policy
- LinkedIn User Agreement (P): https://www.linkedin.com/legal/user-agreement
- Vertex AI Search domain verification (V/P): https://docs.cloud.google.com/generative-ai-app-builder/docs/domain-verification
- Custom Search JSON API closure (V): https://www.firecrawl.dev/blog/google-search-json-api-alternative
- PIB RSS (P/V): https://www.pib.gov.in/ViewRss.aspx
- Google Fact Check Tools API (P): https://developers.google.com/fact-check/tools/api
- SemEval-2025 Task 7 overview (V): https://arxiv.org/pdf/2505.10740v1
- Third-party pricing and market roundups (V): search-API and X-API comparison blogs surfaced by search; treat their figures as unverified.
