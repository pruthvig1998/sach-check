# Scaling Sach: what happens when more people use it

Plain answer to "what if users increase and our models hit limits": Sach already degrades in steps instead of falling over, and this
note says where each limit bites, what one check costs, which settings to turn, and what to switch on (and roughly what it costs) as
traffic grows. Figures from provider pages were read on **2026-11-13** and can change: re-check the linked page before you rely on a number.

**What has and has not been tested.** The code paths here are covered by offline tests (`tests/test_scale.py`) using fake stores and fake
AI judges. Sach has **not** been load-tested against real providers or at real traffic. Token and call counts below are counted from the
code (arithmetic shown), not measured from provider dashboards. Treat them as estimates.

## 1. The request path

```
forward arrives (website / API / Telegram)
 1. per-IP limit            8 checks/min per person (shared across instances when Upstash is set)
 2. cache lookup            same text answered before? -> serve it. Free. Never limited.
 3. match                   (coming from the MATCH work) known-hoax match? -> serve it. Free. Never limited.
 4. global live budget      SACH_MAX_LIVE_PER_MIN / SACH_MAX_LIVE_PER_DAY, counted in Upstash
        budget gone  -> honest "Sach is very busy right now" (no verdict), PIB links, try again in a few minutes
 5. live check              search (Tavily/Brave) + PIB + AI judges, validated against the page
        an AI provider is rate-limited -> that model pauses for the time the provider asked; the next one answers
        every AI provider is down      -> "Limited mode": only clear PIB debunks, otherwise UNVERIFIED (never a guess)
        search is down                 -> result says so and is NOT cached
```

Steps 2 and 3 are the biggest lever: a viral forward is mostly the same text sent thousands of times, so the more of the load the cache
and matcher absorb, the less any provider limit matters. Repeats cost roughly 10 store commands and no AI calls (counted from the code).

`/?view=status` shows, per provider, whether it is configured and ready or paused on this server instance, plus the budget used.

## 2. Where each limit bites

| Resource | Free limit (source, read 2026-11-13) | When hit | What Sach does |
|---|---|---|---|
| Vercel Hobby functions | 1,000,000 invocations, 4 h Active CPU, 360 GB-hours memory a month ([fair-use guidelines](https://vercel.com/docs/limits/fair-use-guidelines)) | Vercel warns, then may restrict the project | Waiting on AI/search calls is mostly idle time, not CPU, but this has not been measured. Watch the Vercel usage page |
| Upstash Redis (cache, counters, limits) | 500K commands a month, ~250 MB, 10 GB bandwidth ([pricing](https://upstash.com/pricing/redis)) | Commands fail | Every store call fails soft: cache misses, counters read 0, per-IP limits fall back to memory, the global budget falls back to a per-instance counter. Checks keep working |
| Tavily search | 1,000 credits a month; a basic search is 1 credit ([API credits](https://docs.tavily.com/documentation/api-credits)) | Tavily answers 432/433 or 429 | Provider paused 6 h (or its Retry-After). If no search works the result says "web search was unavailable" and is not cached. PIB retrieval still works |
| Brave search | Out of credits (owner's account) | 402 | Skipped for 6 h, Tavily takes over |
| Groq | The Groq page lists for `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`: 30 requests/min, 1K requests/day, 8K tokens/min, 200K tokens/day, labelled "base limits for the Developer plan"; check your own plan on [your limits page](https://console.groq.com/settings/limits) ([docs](https://console.groq.com/docs/rate-limits)) | HTTP 429 with `retry-after` | That model pauses for the Retry-After; the next model/provider answers |
| Google Gemini | Limits are per **project** (not per key) and daily limits reset at midnight Pacific; numbers per model are shown in AI Studio ([rate limits](https://aistudio.google.com/docs/rate-limits)). Flash-lite models are listed "free of charge" in the standard tier ([pricing](https://aistudio.google.com/docs/pricing)) | 429 | Model pauses, next answers. **Two keys from the same Google project share one quota**: make the second key in a different project |
| OpenRouter `:free` models | 20 requests/min, plus 50 or 1,000 requests/day depending on credits bought (10 credits raises it) ([limits](https://openrouter.ai/docs/api-reference/limits)) | 429 | Pause and fail over |
| Mistral | Check the provider's page (not re-read for this note) | 429 | Pause and fail over |
| Cloudflare Workers AI (new, optional) | 10,000 Neurons a day free, resets 00:00 UTC ([pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)); most text models default to 300 requests/min ([limits](https://developers.cloudflare.com/workers-ai/platform/limits/)). How many Neurons one Sach call uses: check the pricing page for your model | 429 or error | Pause and fail over |

**How the default budget was sized** (`SACH_MAX_LIVE_PER_MIN=6`, `SACH_MAX_LIVE_PER_DAY=100`, deliberately conservative):

- Per minute: Groq's 8K tokens/minute per model, at roughly 700 tokens per judge call (section 3), allows about 11 calls a minute per
  model, so about 33 across the three Groq models, about three typical checks a minute from Groq alone. Gemini, OpenRouter and the rest
  add to that. 6 leaves headroom and keeps a burst from tripping every provider at once.
- Per day: Groq's 200K tokens/day per model is 600K across three models, about 85 typical checks (7,000 tokens each). 100 is that plus
  what the other providers add, rounded down. Google's per-model daily numbers were not on the page I could read, so they are not used.
- **Search is the tighter limit.** Tavily's 1,000 credits a month is 2 to 4 searches per claim, so roughly 170 to 330 typical checks a
  month in total (about 6 to 11 a day on average). At 100 live checks a day the Tavily credits will run out in days, after which checks
  continue with PIB-only evidence and say so. If you want search to last the month, lower `SACH_MAX_LIVE_PER_DAY` or add a second
  search provider. Raising the budget beyond what providers allow does not add capacity, it only moves where the "busy" happens.

## 3. What one live check costs

Counted from `sach/pipeline.py`, `sach/retrieve.py` and `sach/llm.py`.

- Claims per forward: up to 5 (`MAX_CLAIMS`); a typical forward has 1 to 2.
- Per claim, search: PIB web query (1, a second one if nothing found), official-sites query (1), fact-checker query (1, only if no
  official page was found). **2 to 4 search credits.**
- Per claim, AI calls: translation 1 (only when the claim is not English); then up to 8 sources are judged, **1 call each**; a source
  with a decisive answer gets a second call from a different model, and a "none" the offline matcher disagrees with gets one more from
  another provider. Typical: 5 to 6 sources, mostly "none": **about 6 calls per claim**; worst case 8 sources x 2 = 16.
- Size of one call: the instructions are 1,024 characters; the claim ~120, title ~90, page excerpt at most 1,200 (`sach/excerpt.py`):
  about 2,500 characters, so **roughly 620 input tokens** (at about 4 characters a token) and **about 100 output tokens** (a label and a
  30-word quote; some reasoning models spend more).

| Check | AI calls | AI tokens | Search credits |
|---|---|---|---|
| 1 claim, typical | ~6 | 6 x (620 + 100) ~ 4,300 | 2 to 4 |
| 2 claims, typical | ~12 | ~8,600 | 4 to 8 |
| 5 claims, worst case | up to 80 | up to ~58,000 | up to 20 |

Before the token diet each call carried up to 6,000 characters of page text: about 7,300 characters, roughly 1,800 input tokens, about
three times the input. The excerpt measurement is in section 6.

## 4. Knobs

| Setting | Effect |
|---|---|
| `SACH_MAX_LIVE_PER_MIN`, `SACH_MAX_LIVE_PER_DAY` | The global live-check budget (default 6 and 100). `0` removes a limit. Needs the Upstash store to be shared across instances; without it each instance counts alone |
| `SACH_EXCERPT_CHARS` | Page text sent per source (default 1200). `0` restores the old 6,000-character prefix |
| `SACH_JUDGE_ORDER` | Which AI provider is tried first (default `groq,gemini,openrouter,mistral,cloudflare,claude`) |
| `SACH_<PROVIDER>_MODELS` | Models per provider, e.g. `SACH_GROQ_MODELS` |
| `SACH_LLM_MAX_CONCURRENT` | AI calls in flight at once (default 8) |
| `SACH_SEARCH_ORDER` | Search provider order |
| `SACH_CACHE_TTL_DECISIVE_S`, `SACH_CACHE_TTL_UNVERIFIED_S` | How long answers stay cached (7 days, 6 hours). Longer means fewer live checks |
| more keys | `GEMINI_API_KEY=k1,k2` (different Google projects), `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` |

Per-IP limit: 8 checks a minute per person; in the shared store when Upstash is set, otherwise per server instance.

## 5. Growth plan

**Stage 0, now ($0).** Verdict cache, match, provider failover with per-model pauses, token diet, the global live-check budget with an
honest "busy" answer, the status page. Capacity is roughly the lowest of: your AI free tiers (section 2), Tavily credits, and the budget you set.

**Stage 1, more free capacity (still $0).** Add keys: a second Gemini key from a *different Google project*, an OpenRouter key, a Mistral
key, Cloudflare Workers AI (token + account id). Add a second search provider if you can get one with a free plan. Raise the budget
only as far as the providers you added really allow (use the status page to see them). Watch Upstash commands: a live check is roughly
20 store commands and a cache hit roughly 10 (counted from the code), so 500K a month is about 25,000 checks; check the Upstash usage page.

**Stage 2, pay for one fast provider.** Cheapest step that removes the AI ceiling. Cost of one live check:

```
cost per check = claims x calls_per_claim x ( input_tokens x price_in + output_tokens x price_out ) / 1,000,000
               + search_credits x price_per_search_credit
typical:  1.5 x 6 x ( 620 x price_in + 100 x price_out ) / 1,000,000  + ~5 x price_per_search_credit
```

Plug in the current prices from your provider's page. Example with one price I confirmed on 2026-11-13: the Gemini API paid tier lists
`gemini-3.1-flash-lite` at $0.25 per 1M input tokens and $1.50 per 1M output tokens (output includes thinking) ([pricing](https://aistudio.google.com/docs/pricing)).
That gives 9 calls x (620 x 0.25 + 100 x 1.50) / 1,000,000 = about $0.0027 per typical check for the AI part, so about 0.27 US cents.
Search: use the paid price on Tavily's page (not read for this note). Thousands of checks a month stay in the tens of dollars on this arithmetic,
and the cache means repeats cost nothing. Then raise `SACH_MAX_LIVE_*`.

**Stage 3, spikes (described, not built).** A viral moment sends far more than any budget in a few minutes. Instead of refusing, take the
check into a queue and answer a little later: accept the forward, store a job, return "we're checking, come back to this link", and process jobs at the rate the
providers allow, with the cache answering the many duplicates once the first one finishes. Options: Upstash QStash (message queue that calls a function
with retries) or a background function. The existing shareable result link (`/?r=...`) is the natural "come back here" page. This needs
a job state, a polling page and Telegram/WhatsApp follow-up messages, so it is a real piece of work. Do it when "busy" answers become common.

## 6. Token diet measurement

`sach/excerpt.py` keeps the page title plus the sentences with the best word overlap with the claim, every sentence with one of the claim's
numbers, every sentence with denial wording, and the first sentence of PIB/official pages; in page order, at most about 1,200 characters.
Validation is unchanged: a model's quote is checked against the **full** page, so cutting what the model sees cannot make an invented
quote pass (`tests/test_scale.py` proves both directions).

Measured with a script over `data/pib_index.jsonl` (351 PIB releases, using the claim = the release headline, the best case for overlap):

| Input | Before (characters) | After | Saving |
|---|---|---|---|
| 351 stored excerpts (avg 1,437 characters, max 1,500) | 504,536 total | 361,415 total | 28% |
| 9 pages built by joining 4 real releases to ~5,800 characters (a stand-in for a long live page) | 5,824 avg | 1,125 avg | 81% |

The index only stores 1,500 characters per release, so the first row understates the saving on real live pages, which the old code
cut at 6,000. The second row is synthetic (real text, joined), not a measurement of real long pages; real savings on live pages will sit between the two rows.

## 7. Google Cloud trial credits (optional translator)

With `GOOGLE_TRANSLATE_API_KEY` set, Sach sends a non-English claim to the Google Cloud Translation API (Basic, v2) first and falls back
to the AI translator when Google is off, over budget, slow or errors. It uses Google's translator first and the AI model as fallback;
we have not measured whether this is more accurate, only that it saves the AI quota (one call per non-English claim) and that Google
reports the detected language. Latin-script text (English, Hinglish, Tinglish) never goes to Google.

**What uses credits.** Only characters sent to Google: at most 1,000 characters per claim, only for Indian-script text, only on a
cache miss (translations are cached 7 days under `gt:<sha256>`, so repeats cost nothing and are not counted). Language detection and
translation are one call and are billed as characters.

**Price and free allowance** (Google's pricing page, https://cloud.google.com/translate/pricing, read 2026-11-13): NMT text translation
and language detection, the first 500,000 characters per month are free ("applied as $10 credit every month"), then $20.00 per
1,000,000 characters. At the default cap of 150,000 characters per day the worst case is 4,500,000 characters in a 30-day month, which
would be about $80 outside a free trial; on trial credits there is no automatic charge. Lower the cap if you want it inside the free 500,000
characters (about 16,000 characters per day).

**The guard.** `SACH_TRANSLATE_MAX_CHARS_PER_DAY` (default 150000, 0 = unlimited) and `SACH_TRANSLATE_MAX_CHARS_PER_MIN` (default 20000)
are counted in the store per UTC day / minute (same pattern as the live-check budget; a failing store falls back to a per-instance
counter, so it can only loosen the guard, never block checks). When a budget is used up, Google is skipped silently and the AI translator
runs as before; the skip is counted on the status page, not logged as an error. After a 403 or 429 from Google Sach pauses Google for five minutes.

**When the trial ends.** Google suspends the account's billing-enabled services; calls start returning 403, Sach pauses Google, and the
AI translator takes over silently. Nothing breaks. There is no charge unless you upgrade the account to a paid one. Unset the key to switch it off.
The status page (`/?view=status`) shows whether it is configured and today's characters against the cap (never the key).

## 8. Vertex AI judge (optional, paid from Google Cloud credit)

With `GOOGLE_SA_JSON` set, Sach adds Gemini on Google Cloud Vertex AI as an AI judge and puts it **first** in the default order
(`vertex,groq,gemini,openrouter,...`). The free-tier Gemini quotas (section 2) are shared per project and run out; Vertex bills against
your Google Cloud trial credit instead and has real quota, so it removes that bottleneck. It uses the same prompt, parsing and
validation as the other Gemini judge; only the transport differs (an OAuth token from a service account, signed with a small RS256
implementation in `sach/vertex.py`, because the runtime has no third-party packages). Unset, it is simply off. `SACH_JUDGE_ORDER` overrides the position.

**Setup.** (1) In the Google Cloud project that holds the credit, enable the Vertex AI API. (2) Create a service account and give it the
single role `roles/aiplatform.user`, nothing else. (3) Create a JSON key for it and paste the whole file (or its base64) into the Vercel environment
variable `GOOGLE_SA_JSON`. Never commit it, never put it in `.env` files that are tracked. (4) Check with `python scripts/check_llm.py`.
Models default to `gemini-3.1-flash-lite,gemini-3.8-flash` (`SACH_VERTEX_MODELS`) at the `global` location only (regional locations do not serve them).

**The guard.** Every call is billed, so `SACH_VERTEX_MAX_PER_DAY` (default 4000, 0 = unlimited) caps calls per UTC day, counted in the shared
store like the live-check budget (a failing store falls back to a per-instance counter). Beyond the cap the provider is paused until 00:00 UTC
and the other judges answer; the skip is counted on the status page, not raised as an error. A 429 pauses that model, a 5xx moves to the next model,
a 401 or 403 pauses Vertex for 10 minutes. A failed token refresh is remembered for 30 seconds so a broken key does not hammer Google.
The status page (`/?view=status`) shows configured, ready or paused, and calls today of the cap (never the project, the account or any key).
Cost: estimate with the formula in section 5 using the current Vertex price of the model you use; not measured here.

## 9. Vercel AI Gateway judge (optional, free monthly credit)

**What.** With `AI_GATEWAY_API_KEY` set, Sach adds the Vercel AI Gateway (OpenAI-compatible, `https://ai-gateway.vercel.sh/v1`) as an AI judge. In the
default order it sits **after Vertex and Groq and before the free-tier Gemini keys and OpenRouter** (`vertex,groq,gateway,gemini,openrouter,...`),
because those free tiers are usually exhausted. `SACH_JUDGE_ORDER` still overrides. Unset, it is simply off. Same prompt, parsing and validation as the
other judges; the code is `GatewayJudge` in `sach/llm.py` and `sach/gateway.py`.

**Free credit.** Vercel gives each team a monthly free AI Gateway credit (about $5 at the time of writing; it starts at the first request, and
buying credits ends it). Check the AI Gateway page of your dashboard: Vercel's pricing page also says the free tier covers only a subset of models
and has lower per-model rate limits. Whether `openai/gpt-oss-120b` and `google/gemini-3.1-flash-lite` are covered by the free credit was **not verified**; if
they are not, calls return 402 and Sach simply pauses the provider until 00:00 UTC (nothing breaks; set `SACH_GATEWAY_MODELS` to models the dashboard marks free).

**The cap.** `SACH_GATEWAY_MAX_PER_DAY` (default 1500, 0 = unlimited) caps calls per UTC day, counted in the shared store like the Vertex cap
(a failing store falls back to a per-instance counter). Arithmetic: the credit lasts the month if `cap x 30 x cost per call <= $5`, i.e.
cost per call <= $5 / (1500 x 30) = about $0.00011. A judge call is roughly 1,500 input tokens (page excerpt plus prompt) and 100 to 700 output tokens
(an estimate, not measured). At list prices (gpt-oss-120b $0.35 in / $0.75 out per million tokens; gemini-3.1-flash-lite $0.25 / $1.50) that is
about $0.0005 to $0.001 per call, so $5 buys roughly 5,000 to 10,000 calls, or 170 to 330 a day. **Lower the cap to about 200 (or use
`openai/gpt-oss-20b` at $0.07 / $0.30) if you want the credit to last the whole month**; leave 1500 only if you accept it running out early
(a 402 then pauses the gateway until the next day, and the other judges answer). Prices change: check the model list in the dashboard.

**Failures.** 401 (bad key) or 403 pauses the provider 10 minutes; 402 (credit or budget used up) and the daily cap pause it until 00:00 UTC; 429 pauses that
model for the Retry-After seconds (a minute if absent); 5xx and timeouts use the normal model-by-model failover. The status page (`/?view=status`) shows a
`gateway` row (configured, ready or paused, calls today of the cap, never the key).

**Setup.** (1) Vercel dashboard, AI Gateway, API Keys, create a key named for Sach. (2) Add it to the project's environment variables as `AI_GATEWAY_API_KEY`
(never commit it, never put it in a tracked `.env`). (3) Optionally set `SACH_GATEWAY_MODELS` (comma list of `creator/model`) and `SACH_GATEWAY_MAX_PER_DAY`.
(4) Check with `python scripts/check_llm.py` (its probes spend a few calls of the credit). You can also set a budget on the key in the dashboard as a second guard.
