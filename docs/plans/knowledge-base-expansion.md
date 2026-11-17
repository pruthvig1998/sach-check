# Knowledge base expansion: answer everyday India questions, not only government claims

Status: phases 1 and 3 built on 18 Nov 2026 (see section 8); the rest is plan. Items marked (unverified) come from memory or a secondary page and must be checked before use.

## 1. Why "Did actor Giri Babu pass away?" and "When is Diwali?" get no answer

Measured on production, 18 Nov 2026:

| Input | Result | What Sach searched |
|---|---|---|
| Did the actor Giri Babu pass away? | UNVERIFIED, no_evidence | a PIB PDF on fauna, a WHO file, a Karnataka GST PDF |
| Actor Giri Babu passed away today | UNVERIFIED, no_evidence | one PIB PDF |
| When is Diwali in 2026? | UNVERIFIED, no_evidence | six PIB releases |
| Diwali is on 8 November 2026 | TRUE, official confirmation | PIB releases |

Three causes, all by design, none a bug:

1. **Sach only reads government pages.** The search is restricted to `gov.in`, `nic.in`, WHO, RBI, MyGov, Parliament, plus fact-checker sites (`sach/retrieve.py`, `OFFICIAL_Q`). No government page records an actor's death, a match result, a film release or a company event. Those claims can never be confirmed or denied today.
2. **A question is treated as a claim.** "When is Diwali?" has nothing to confirm. The same fact worded as a statement got TRUE. Sach has no answer mode.
3. **There is no structured reference data.** Dates, holidays, office holders, schemes, districts and statistics are looked up by web search each time, which is slow, costs budget and often misses.

## 2. What "everything about India" can honestly mean

A copy of all knowledge is not possible and not needed. The workable target is: **for any claim or question about India, Sach knows which trustworthy source would hold the answer, can reach it, and says plainly how strong that source is.** That needs four things: more source tiers, an answer mode, a local reference store, and partnerships for what is not on the open web.

The verdict rules stay. TRUE and FALSE keep their current meaning (official confirmation, official contradiction, PIB debunk). New evidence gets new, separately labelled results, so a news report is never shown as an official fact.

## 3. Design changes

### 3.1 New result labels (owner decision needed)
- **REPORTED**: at least two independent established news organisations report it, no official source found. Shown with the outlets and times. Never called TRUE.
- **NO RELIABLE REPORT**: for an event that would be widely reported if real (a death of a public figure, a disaster, a ban), nothing was found in the news tier. Not called FALSE. The text says a real event of this kind is normally reported within hours.
- **ANSWER**: for a question, the fact and its source (for example a holiday date from the Government's holiday order).

### 3.2 Death and breaking-news safeguards
Death hoaxes are a top category of viral forwards, and news sites sometimes repeat them. Rules: two independent outlets at least, one of them a wire or public broadcaster (PTI, ANI, DD News, All India Radio) or a statement from the family or an official body; Wikipedia and Wikidata are never the sole basis because they can be edited by anyone; the card shows the report time and says "as reported".

### 3.3 Question mode
Detect a question (question mark, "when", "who", "kab", "ఎప్పుడు" and so on), turn it into a lookup, answer from the reference store first, then official search, then the news tier. If nothing is found, say so and show where to look. No guessing from the model's memory.

### 3.4 Local reference store
One SQLite file in `data/`, built by scripts, the same pattern as the PIB index. It holds facts with a source URL and a fetched date. It is the cheapest layer: no search call, no AI call.

## 4. Source catalogue

Access and licence are as found on 18 Nov 2026. "Checked" means a search result from the source or about it was read today; it does not mean the feed was tested from Sach.

### Tier A. Official, already reachable, used better
| Source | What it adds | Access | State |
|---|---|---|---|
| PIB and PIB Fact Check | central government announcements, debunks | in use | live |
| All India Radio news, `newsonair.gov.in` | daily national and regional news from the public broadcaster, on a `gov.in` host, includes deaths of public figures and disasters | already inside the official search pool, but rarely returned; add a direct query | to build |
| NDMA SACHET alerts | disaster and weather warnings by district (cyclone, flood, heatwave rumours) | public CAP RSS feed; address from a third-party listing: `sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml` (unverified) | to build |
| IMD | weather warnings and nowcasts | `api.imd.gov.in`; access appears to need a request and IP whitelisting (unverified) | needs owner request |
| eGazette, India Code | notified laws, rules, bans | public sites, search | to build |
| Parliament questions and answers, `sansad.in` | what a ministry told Parliament, with dates | site search and download; no documented public API; Rajya Sabha answers also appear per session on data.gov.in | to build |
| RBI, SEBI, ECI, UIDAI, NPCI, TRAI, CERT-In, I4C, EPFO, Income Tax, NTA, UPSC, CBSE, UGC, FSSAI, CDSCO, ICMR, DGCA, Railways | the bodies most often impersonated in forwards | public notices pages; add each host to the official list and to targeted queries by claim domain | to build |
| State governments and state information departments | state schemes, state holidays, local orders; most forwards are state-level | public sites; a list of the 36 state and UT press release pages must be compiled | to build |
| State police and state fact-check units | local rumour debunks | mostly on X and Telegram; same method as the PIB posts ingest | to build |

### Tier B. Structured reference data (the local store)
| Source | What it adds | Access and licence | State |
|---|---|---|---|
| DoPT holiday order and state holiday lists | festival and holiday dates. The 2026 central list comes from a DoPT order dated 3 July 2025 (from secondary pages; the order itself was not read) | PDF, public | to build first |
| Rashtriya Panchang, Positional Astronomy Centre | official basis for festival dates in future years (unverified) | published yearly | to check |
| data.gov.in | government datasets, many with an API | free API key; Government Open Data Licence India, reuse and commercial use allowed with attribution | needs owner key |
| myScheme | about 1,360 central and state schemes with eligibility (count from a secondary page) | site is public; an API through API Setu is likely but not confirmed | to check |
| Local Government Directory | every state, district, block and village name and code (unverified) | public downloads | to build |
| India Data Commons (IIT Madras) and Data Commons | census, RBI, health and other statistics as a graph | API key from `apikeys.datacommons.org`; compilation licensed CC BY | needs owner key |
| MoSPI, Census, NFHS, NITI Aayog NDAP, RBI DBIE | headline statistics people quote in forwards | public downloads | to build |
| Wikidata | people, office holders, places, dates; property P570 is date of death | free SPARQL endpoint, CC0 data, needs a proper User-Agent, about 60 seconds of query time per minute per client | to build, as a pointer only |
| Wikipedia | background and context | free API; CC BY-SA 4.0, attribution and share-alike; Wikimedia Enterprise has a free tier (5,000 on-demand requests a month per its blog) | to build, as a pointer only |

### Tier C. News, for events no government page records
| Source | What it adds | Access and licence | State |
|---|---|---|---|
| PB-SHABD, Prasar Bharati | text, audio, video and photos from DD and AIR reporters, reported as 800 to 1,000 stories a day in many Indian languages, free of copyright for registered outlets | free registration at `shabd.prasarbharati.org/register`; free access reported as extended to March 2027; print needs an RNI certificate, broadcast needs uplink papers, digital portals fill a form and are verified | needs owner to apply |
| GDELT | index of world news in 65 languages, searchable by keyword and country | free, no key; one request per 5 seconds; 250 results per query; about three months of history | to build |
| Outlet RSS feeds: The Hindu, Indian Express, Times of India, Hindustan Times, NDTV, Deccan Herald, Eenadu, Sakshi, Dainik Jagran, Dainik Bhaskar, Mathrubhumi, Anandabazar and others | national and regional coverage | public RSS; store headline, link, time only, never the article body | to build |
| PTI, ANI, UNI | the wires most outlets copy | paid subscription; price not public | owner decision |
| Paid news APIs (NewsData.io, NewsAPI.ai, mediastack and others) | one API over many outlets | paid plans with small free tiers | optional |

### Tier D. Other fact-checkers
| Source | What it adds | Access and licence | State |
|---|---|---|---|
| Google Fact Check Tools API | published fact-checks by claim | in use | live |
| Data Commons ClaimReview feed | daily bulk file of ClaimReview markup, the base for an offline corpus (this is the L3 layer) | compilation CC BY, each record has its own licence field; feed address from a third-party file, unconfirmed | to check, then build |
| IFCN signatories in India: BOOM, Factly, NewsMeter, Newschecker, Vishvas News, The Quint and others | Indian-language fact-checks | their sites and RSS; current badge status must be read from the IFCN directory (Factly's listing showed an expired badge) | to compile |
| Misinformation Combat Alliance, Deepfakes Analysis Unit | checks of audio and video for AI generation; WhatsApp tipline +91 9999025044 in English, Hindi, Tamil, Telugu | link from Sach for media claims; membership is by application | owner outreach |

### Tier E. Offline and real-world routes (only the owner can do these)
- **Register on PB-SHABD.** The biggest free gain. It needs Sach to qualify as a digital news portal, or a registered publisher as partner.
- **Partner with one fact-checker** (Factly and NewsMeter are both Hyderabad-based and work in Telugu) for a shared claim feed and human review of the most-asked claims.
- **Write to PIB Fact Check and to state fact-check units** asking for a machine-readable feed of their debunks.
- **Apply for keys and access**: data.gov.in, Data Commons, IMD.
- **A university journalism or library partner** for native-language review and for digitising state gazettes and local orders that are not online.
- **RTI requests** for datasets that exist but are not published.
- **Ask a wire for a non-profit or pilot rate** (PTI, ANI), once there is usage to show.

## 5. Build order

| Phase | What | Needs owner | Risk |
|---|---|---|---|
| 1 | Question mode plus the reference store seeded with holidays and festivals (central and state), measured on 50 everyday questions | no | low: answers come only from stored official documents |
| 2 | Wider official tier: All India Radio news, the regulator hosts, SACHET alerts, state press release pages | no | low: still official sources |
| 3 | News tier with the REPORTED and NO RELIABLE REPORT labels: GDELT plus outlet RSS, the death safeguards, a red-team set of 30 death hoaxes and 30 real deaths before it is switched on | yes: approve the new labels | medium: a wrong "reported" on a death hoax is a serious harm |
| 4 | Offline ClaimReview corpus from the Data Commons feed; Wikidata and Wikipedia as pointers | check feed terms | low |
| 5 | Schemes (myScheme), statistics (data.gov.in, Data Commons), places (Local Government Directory) | keys | low |
| 6 | Partnerships: PB-SHABD, a fact-checker, state units, a wire | owner outreach | none technical |

Every phase keeps the existing rules: a switch per layer, a differential test that no existing verdict changes, an independent review before deploy, no em dash characters in new strings.

## 6. Limits to state openly

- News can be wrong. REPORTED means "these outlets say so", not "this is true".
- Copyright: Sach stores facts, links and short quotes, never full articles. PB-SHABD content is the exception, under its registration terms.
- Wikipedia and Wikidata can be vandalised. They point to sources; they are not evidence.
- Search budget is the tightest limit. The news tier and question mode add queries, so the local store and feeds must answer first.
- Regional coverage will be uneven at first: English, Hindi and Telugu before the other languages.
- Several access details above are unverified and marked so. Each must be tested from Sach before it is relied on.

## 7. Decisions for the owner

1. Approve the three new labels (REPORTED, NO RELIABLE REPORT, ANSWER)? Without them the news tier cannot be shown honestly.
2. Should Sach apply to PB-SHABD as a digital news portal?
3. Which keys will you create: data.gov.in, Data Commons, IMD?
4. Is a paid wire or news API in budget, or free sources only for now?
5. Start with phase 1 (question mode and holidays)?

## 8. Build status (18 Nov 2026)

Owner decisions: all three labels approved; free sources only; social media to be included where possible.

**Built (branch `kb-phase1`)**
- Reference store with the central holiday lists for 2026 and 2027, read from three government PDFs. On by default.
- Question mode: a short question the store can answer gets an ANSWER card with the source, with no search and no AI call, and uses no live-check slot.
- A statement that names a festival keeps its normal result and gains an "official dates" panel.
- News tier with REPORTED, "reported as not true", "one outlet" and NO RELIABLE REPORT. Off until `SACH_NEWS_TIER=1`.
- Social signal: counts of public posts on X, Facebook and Instagram found by web search. Off until `SACH_SOCIAL_SIGNAL=1`.
- The verdict rules are unchanged. News and social findings sit in the claim trace and on the card as labelled lines.

**Changed from the plan**
- The ANSWER and REPORTED labels are shown to the reader, but the machine `verdict` field stays UNVERIFIED, so the ClaimReview feed, the ledger and every existing consumer keep their meaning.
- News search uses the existing search providers (one extra query), not GDELT, so there is no new service to depend on.
- A verdict from the number of social-media posts was not built: post volume measures popularity, not truth. See `docs/sources.md`.

**Not built yet**
- Phase 2: SACHET alerts, a direct All India Radio query, state press pages, state holiday lists.
- Phase 4: offline ClaimReview corpus; Wikidata and Wikipedia pointers.
- Phase 5: schemes, statistics, places. These need the owner's data.gov.in and Data Commons keys.
- Phase 6: PB-SHABD registration and the other partnerships.
- A live red-team set of real deaths and death hoaxes. The rules are tested offline with scripted judges only; no provider keys are on this machine.
