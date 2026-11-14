# Sach at crore scale: check each claim once, serve it to everyone

Status: proposal, 14 Nov 2026. Nothing here is built. Numbers marked (assumption) are my estimates and have **not** been measured on real traffic; the "Measure first" section says how to replace them with data.

## 1. The idea in one paragraph
Today every question can trigger a paid check (about 8 AI calls and 2 to 4 searches). That cannot reach crores of people, and no amount of tuning will fix it. The fix is to change what a request *is*: a request becomes a **lookup in a public registry of checked claims**. A claim is checked **once**, the answer is stored with its evidence, and that same answer is served to everyone who asks, from a cache at the edge of the network, at almost no cost. Only claims the registry has never seen reach the expensive pipeline, and even then the most-asked claims go first. "Unlimited" is then true for what people actually ask, because viral claims are asked millions of times and checked once.

## 2. Why this works: viral misinformation is head-heavy
A forward that reaches crores of people is the *same text*, or a light edit of it, sent again and again. A few hundred claims account for most of the traffic on any given day; a long tail of one-off messages accounts for the rest. So the sensible spend is: **a lot of care on the few claims that matter, a cheap honest answer on the long tail.** (Assumption: the real distribution looks like this. Our ledger is too small and too contaminated by our own tests to confirm it, which is why section 7 starts with measurement.)

## 3. The architecture: a demand-driven funnel

```
request ─► 1. canonical claim id   (normalise, strip wrappers, same claims = same id; near-duplicates join one cluster)
          ├► 2. EDGE CACHE         answer page / JSON / share card for that id, served from the CDN. Cost: about zero. Never "busy".
          ├► 3. REGISTRY LOOKUP    checked before? serve it (verdict, evidence, date, who checked).
          ├► 4. FREE LAYERS        published fact-checks (PIB debunks incl. Telegram, ClaimReview store), official-pages panel,
          │                         scam-pattern and link checks. No AI call.
          └► 5. UNKNOWN CLAIM      answer instantly with what steps 3 and 4 found, say plainly "not checked yet", count this asker,
                                    and put the claim in the PRIORITY QUEUE.

PRIORITY QUEUE (works through unknown claims by how many people asked, not first-come):
   asked by 1 person      ─► nothing paid; free layers only (the long tail)
   asked by about 5       ─► one cheap model check, stored
   asked by about 50      ─► full check with the strong judge, stored with its evidence
   asked by about 5,000   ─► also sent to a human fact-checker (BOOM, Alt News, PIB tipline partners) before the answer is firm
```
Everything above step 5 is cheap and fast. Step 5 never blocks: a person always gets an answer immediately, and the answer improves as the claim gains attention. The word "busy" disappears.

## 4. The pieces, and what each buys
| Piece | What it does | Status |
|---|---|---|
| **Claim canonicalisation** | Greetings, "forwarded" lines and emoji no longer create a new claim. Near-duplicates (one word changed, a typo) join one cluster, with guards so a changed number or a "not" never merges. | Exact claim key is live (L0). Near-duplicate clustering is next. |
| **Public claim registry** | One record per claim cluster: verdict, evidence, ask-count, first and last seen, who checked, review date. Also the data behind a public feed others can use. | Partly: the cache stores answers, but it is a 6 h to 7 day cache, not a permanent registry. |
| **Edge cache** | Each answer has a stable address that a CDN caches, so a million views are one computation. Shared result cards and links are the viral path, and they are already cacheable in principle. | Not yet: results carry no cache headers. |
| **Priority queue** | Spends the AI budget on the claims the most people are asking about, using cheaper steps first. | Not built. |
| **Free layers** | PIB debunks, PIB Telegram, official-pages panel, scam checks. | Live (L1, L2, L5). |
| **Human escalation** | For claims asked thousands of times, a person confirms before the answer hardens. Already linked to tiplines. | Links exist; no workflow. |
| **Trend discovery** | Pre-check claims before people ask: new PIB Fact Check posts, fact-check feeds, seasonal scams (exam leaks, festival offers). | Not built. |

## 5. Cheaper fresh checks (the second lever)
Even with heavy reuse, fresh checks must cost far less than today's about ₹1 to ₹2.
- **One judge call per claim, not eight.** Give the judge the best three page excerpts in one request. This changes judging behaviour, so it must be measured against the red team and evaluation sets first (assumption: about 70% cheaper).
- **Use our own indexes before paid search.** PIB full-text index, PIB posts, ClaimReview store, then web search only if needed. Search is the tightest limit today.
- **Batch the non-urgent.** Google's batch tier is cheaper for work that can wait minutes, which fits the queue.
- **Cheaper model first, strong model only if it matters.** A small model screens; the strong judge handles the claims that reach 50 askers.
- Target: **about ₹0.10 to ₹0.30 per fresh claim** (assumption), versus ₹1 to ₹2 now.

## 6. What the numbers could look like at 1 crore requests a day (assumptions, not measurements)
| Design | Fresh claim-checks a day | Cost a day | Verdict |
|---|---|---|---|
| Today's design, every miss is a paid check | tens of lakhs | tens of lakhs of rupees | Impossible |
| Today's design, 95% reuse | 5 lakh | about ₹7.5 lakh | Too expensive |
| Redesign: 99% reuse by canonicalisation and demand-gating, ₹0.15 per fresh claim | about 1 lakh | about ₹15,000 (₹4.5 lakh a month) | Feasible with sponsorship |
| Redesign, plus the free layers answering 7 to 12% outright (measured with no model) | less than 1 lakh | less than ₹15,000 | Better still |

**Serving cost** is small if the edge does the work: 1 crore requests a day is about 30 crore a month. Vercel's free plan allows 1 million function calls a month (read in our scaling notes), so it cannot carry this. A CDN-first design on something like Cloudflare Workers plus KV is priced in hundreds of dollars a month at this volume (from memory, to be verified before relying on it).

## 7. Measure first (before building the big parts)
We do not know the real reuse rate, and the whole cost case depends on it. Cheap, privacy-safe instrumentation I can add now:
- A counter per canonical claim hash (no text stored, no user identity): how many asks, how many distinct days.
- Log of which layer answered (edge/cache, match, free layers, fresh check).
- From a week of real traffic: the share of requests served without a paid check, and the top claims by volume.
Then every number in section 6 can be replaced with a measured one.

## 8. A build order that does not risk the live site
1. **Now (days):** claim-hash counters and layer logging; cache headers on shared result links; a permanent registry store for decisive verdicts (long TTL, versioned); never return "busy": serve the free-layers answer and queue instead.
2. **Next (2 to 4 weeks):** near-duplicate clustering with guards; the priority queue with a daily budget; one-call judge and batch mode, each measured against the red team and evaluation sets before use; PIB daily harvest.
3. **Then (1 to 3 months):** move the answer-serving path to an edge platform; trend discovery; WhatsApp and Telegram bots as front doors (answers are cached cards, so shares carry the load); a human review workflow for the head claims; partner feeds.
4. **Throughout:** every change keeps the existing rules: no new route to TRUE or FALSE, a switch per layer, a differential test, no loosening of verdict rules to save money.

## 9. What this cannot do, honestly
- **A brand-new claim still costs money or time.** Nothing makes a model read a fresh official page for free. The design makes that rare and prioritised, not unlimited.
- **A stored wrong verdict is served to millions.** At this scale one bad answer is a big harm, so confident verdicts need human review for the head claims, an easy "report a wrong verdict" path (exists), and re-checks when sources change (stale-debunk guard exists).
- **Long-tail claims get an honest "not checked yet", not a verdict.** That is correct behaviour, and it must not read as "probably false".
- **Funding and governance are the real constraints at crore scale:** about ₹5 lakh a month for fresh checks plus infrastructure, and an owner for human review. A government, foundation or platform partner is likely needed.
- **Native-language quality, legal exposure and abuse (people gaming the ask-counter) need their own work:** rate limits per person, and counting distinct askers, not raw requests.

## 10. Decisions for the owner
- Do you want the "check once, serve many" registry as the direction? (It changes what Sach is: a public record of checked claims.)
- Are you open to a "not checked yet, queued" answer for rare claims, instead of always trying a full check?
- Who could fund or host this at scale (a foundation, a ministry, a platform), and should the plan be written for that audience?
- May I add the privacy-safe counters now so real numbers replace my assumptions?
