# Sources: what counts, and why

All evidence below was checked on 2026-11-12. Code: `sach/fetch.py` (lists), `sach/retrieve.py` (search), `sach/factcheck_api.py` (Google Fact Check Tools).

## The three tiers

| Tier | Who | What it can do to a verdict |
|---|---|---|
| `pib_debunk` | A PIB release whose title is a debunk (PIB Fact Check) | Can produce FALSE, MISLEADING or TRUE |
| `official` | Government, statutory or regulator bodies, and bodies whose own site is authoritative about themselves | Can produce FALSE, MISLEADING or TRUE |
| `factchecker` | Verified fact-checking outlets | Shown as a labelled citation. **Can never produce TRUE or FALSE.** With no authoritative evidence the result is UNVERIFIED (`factchecker_only`) |

That asymmetry is the safety property: widening the official list raises the risk of an overclaim, so every official entry needs evidence. Widening the fact-checker list is low risk.

Matching is exact host or true subdomain (`evilrbi.org.in` and `rbi.org.in.evil.com` never match). URLs with a backslash, `%` or whitespace in the host part are rejected, because `https://evil.com\@rbi.org.in/` parses as `rbi.org.in` in Python but goes to `evil.com` in a browser. The older `who.int` suffix matched `notwho.int`; it is now dot-anchored.

## Official list

### Suffixes and original hosts

| Entry | Body | Evidence |
|---|---|---|
| `.gov.in`, `.nic.in` | Indian government (registry-restricted zones) | Long-standing; covers `ssc.gov.in`, `upsc.gov.in`, `uidai.gov.in`, `india.gov.in`, `cybercrime.gov.in`, `sancharsaathi.gov.in`, `digilocker.gov.in`, `indiapost.gov.in`, `eci.gov.in`, `voters.eci.gov.in`, `isro.gov.in`, `mausam.imd.gov.in`, `pmjay.gov.in`, `pmkisan.gov.in`, `incometax.gov.in`, `gst.gov.in`, `cbic.gov.in`, `sebi.gov.in`, `irdai.gov.in`, `trai.gov.in`, `nhai.gov.in`, `epfo.gov.in`. Loaded or resolved on 2026-11-12: upsc, cybercrime, sancharsaathi, digilocker, indiapost, mausam.imd, voters.eci, gst, epfindia (redirects to epfo.gov.in), india, sebi, irdai, trai, nhai, uidai, incometax. No change needed |
| `who.int` | World Health Organization | Treaty-organisation TLD, health claims |
| `pib.gov.in`, `factcheck.pib.gov.in`, `icmr.gov.in` | PIB, PIB Fact Check, ICMR | Original entries |
| `rbi.org.in`, `mygov.in`, `npci.org.in`, `sansad.in`, `nta.ac.in`, `irctc.co.in`, `epfindia.gov.in` | RBI, MyGov, NPCI, Parliament, NTA, IRCTC, EPFO | Original entries (`epfindia.gov.in` is redundant with `.gov.in`; left alone) |

### Added in this change

| Entry | Body | Why it qualifies | Evidence (checked 2026-11-12) |
|---|---|---|---|
| `.bank.in` (true subdomains only, not the bare zone) | Banks regulated by RBI | RBI made it the exclusive domain for banks; IDRBT, authorised by NIXI/MeitY, is the sole registrar. Covers `sbi.bank.in`, `hdfc.bank.in`, etc. | RBI circular RBI/2025-26/28, 22 Apr 2025, "Migration to '.bank.in' domain": https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=12837&Mode=0 . Bank sites sbi.bank.in, onlinesbi.sbi.bank.in, federal.bank.in load. Limit: I could not read IDRBT's registration prerequisites, so "only banks can register" rests on the RBI circular ("exclusive ... for banks") and bank/IDRBT statements |
| `sbi.co.in` | State Bank of India (legacy domain) | Own site; now redirects to the `.bank.in` site | https://sbi.co.in/redirect/ meta-refreshes to https://sbi.bank.in/ |
| `onlinesbi.sbi` | SBI net banking (legacy; `.sbi` is SBI-only) | Redirects to `onlinesbi.sbi.bank.in` | HTTP redirect observed |
| `licindia.in` | Life Insurance Corporation of India (statutory corporation, regulated by IRDAI) | Listed by the regulator as LIC's web address | IRDAI insurer listing: https://irdai.gov.in/life2 (also IRDAI "Life Insurers" list). `licindia.com` also appears in LIC material and is NOT added |
| `aiims.edu` | AIIMS New Delhi (Institute of National Importance) | Government portals point to it | https://www.india.gov.in/website-all-india-institute-medical-sciences-delhi and National Health Portal AIIMS entry (nhp.gov.in). Other AIIMS campuses use other domains and are not covered |
| `pfrda.org.in` | Pension Fund Regulatory and Development Authority (statutory regulator, NPS) | Regulator | Linked from irdai.gov.in; site loads |
| `aicte-india.org` | All India Council for Technical Education (statutory regulator) | Regulator | Linked from https://www.ugc.gov.in/ . Site reset my connection on 2026-11-12 but the link is from a gov.in page |
| `ugc.ac.in` | University Grants Commission (older domain) | Regulator; redirects to ugc.gov.in | https://www.ugc.ac.in/ redirects to https://www.ugc.gov.in/ ; linked from ugc.gov.in |
| `rbiretaildirect.org.in` | RBI Retail Direct (RBI's retail government-securities portal) | Run by RBI | Linked from https://www.rbi.org.in/ ; site loads |
| `jansuraksha.in` | National portal for PMJJBY, PMSBY, APY (Department of Financial Services schemes) | Government scheme portal | Linked from irdai.gov.in; title "National Portal for Government's Social Security Insurance Schemes" |

### Considered and not added

| Candidate | Reason |
|---|---|
| `.fin.in` | The RBI circular only mentions it in a reference to a policy statement; no eligibility evidence found. Revisit with an RBI page that says who may register |
| `ibps.in` | Root site fails TLS verification from here (certificate chain), so I could not confirm it. Only the subdomain `cgrs.ibps.in` appears on RBI notices. IBPS is not a statutory regulator |
| `ihmcl.co.in` (FASTag) | Own site is NHAI-themed and PIB describes IHMCL as an NHAI-promoted company, but I found no gov.in page linking this exact domain. Re-propose with such a link |
| `nvsp.in` | Certificate failure; superseded by `voters.eci.gov.in` which is already covered |
| `un.org`, `unicef.org` | Huge sites that host many third-party documents (member-state statements, partner content, fundraising). Forwards about "UN says" are better left UNVERIFIED than confirmed by a stray page. `who.int` stays because health claims are its core remit |
| `nseindia.com`, `bseindia.com`, `nsdl.com`, `cdslindia.com`, `bsnl.co.in` | Companies, not regulators; the markets regulator `sebi.gov.in` is already covered |
| `ncfe.org.in`, `nism.ac.in`, `baanknet.com`, `unclaimedassetsportal.in`, `2025.coop` | Linked from regulator pages but not sources that forwards need decided |
| `thip.media` etc. | See fact-checkers below |

## Fact-checker list (secondary)

Evidence: the IFCN (Poynter) signatory list, read from the API behind https://ifcncodeofprinciples.poynter.org/signatories on 2026-11-12 (country code 356, India). Status is the IFCN status at that date.

### Whole-site entries

| Host | Outlet | IFCN status |
|---|---|---|
| `boomlive.in` | BOOM | Verified (2026-08-26) |
| `factly.in` | Factly (also publishes Telugu on `telugu.factly.in`) | Verified (2026-07-17) |
| `factcrescendo.com` | Fact Crescendo (language subdomains) | Verified (2026-07-17) |
| `newschecker.in` | Newschecker | Verified (2024-10-08) |
| `youturn.in` | Youturn | Verified (2026-01-14) |
| `vishvasnews.com` | Vishvas News (`factchecker.vishvasnews.com`) | Verified (2024-08-23) |

### Path-restricted entries (general news sites; only the fact-check section counts)

| Host and path | Outlet | IFCN status | Path evidence |
|---|---|---|---|
| `indiatoday.in/fact-check` | India Today Fact Check | Verified (2024-10-08), IFCN URL is this path | https://www.indiatoday.in/fact-check |
| `thequint.com/news/webqoof` | The Quint WebQoof | Verified (2024-12-05) | https://www.thequint.com/news/webqoof |
| `newsmeter.in/fact-check`, `/fact-check-health`, `/ai-deepfake` | Newsmeter | Verified (2025-11-04) | links on the site home page |
| `newsmobile.in/nm-fact-checker` | NewsMobile | Verified (2025-02-27) | article URLs of the form `/nm-fact-checker/fact-check-...` from search results |
| `telugupost.com/factcheck`, `/english-factcheck`, `/ai-factcheck` | Telugu Post | Verified (2026-01-14) | links on the site home page |
| `ptinews.com/factcheck` | PTI Fact Check | Verified (2026-07-17), IFCN URL is https://www.ptinews.com/factcheck/factcheck.aspx | The section page is a JavaScript app; article URL shape not confirmed, so the whole `/factcheck` prefix is accepted |

Path matching is segment-aware (`/fact-check` matches `/fact-check/x` but not `/fact-checker-fan`) and dot-segments and percent-encoding are resolved first, so `/fact-check/../sports` does not count.

### Not added

| Outlet | Reason |
|---|---|
| THIP (`thip.media`) | Verified signatory, but the site returned 403 to an honest-UA request, so I could not see its fact-check URL pattern |
| First Check (`firstcheck.in`) | IFCN status "In Renewal", not currently verified |
| DFRAC (`dfrac.org`), Logically Facts, FactChecker.in, The Logical Indian | IFCN "Expired Signatory" |
| Digiteye, Medical Dialogues, Manorama Online, The Lallantop | Verified signatories but general or niche sites whose fact-check URL patterns I did not confirm |

## Google Fact Check Tools retriever

Enabled only when `GOOGLE_FACTCHECK_API_KEY` is set. One GET to `https://factchecktools.googleapis.com/v1alpha1/claims:search` (`query`, `languageCode`, `pageSize=8`, `key`), 6 second timeout. Request and response shapes were read from Google's reference (developers.google.com/fact-check/tools/api/reference/rest).

- Every result is tier `factchecker`, always, even if the review is on an official domain. It can only add labelled citations, which turns a `no_evidence` UNVERIFIED into `factchecker_only`.
- Reviews are kept only if the URL is on the fact-checker list above, is HTTPS, and the reviewed claim plausibly matches ours (word overlap and subject coverage from `sach/stance.py`). At most 3 are returned.
- Evidence text: claim reviewed, claimant, rating, review date. `fetched_at` is the real UTC time of the call.
- Any error, quota response, non-200 or bad JSON returns an empty list. The key is never put in an Evidence, log or exception message.
- `search(query, language=None)` works for any language text; the language code is guessed from the script (Telugu, Devanagari, else English).
- Limits: Google's pages that I could read do not state whether the API is free or give a quota (checked 2026-11-12; confirm in the Google Cloud console under APIs and Services, Quotas); the index covers only publishers who mark up ClaimReview; Indian-language coverage is thin; and a result on a publisher outside our list is silently dropped.
- Latency: the pipeline calls retrievers in sequence and passes no state between them, so unlike Brave's fact-checker query this one cannot skip itself when authoritative evidence exists. It costs one HTTPS call (typically well under a second, 6 s cap) per claim.

## Brave query budget

Per claim today: PIB query (1), a second PIB keyword query only if the first found nothing (0 or 1), the official-domains query (1), the fact-checker query only if nothing authoritative was found (0 or 1): 2 to 4 calls. Calls are throttled to one per 1.1 s across all claims, and a check can have 5 claims, so the worst case is about 20 calls, roughly 22 s of throttling inside a 30 s retrieval deadline. This change adds no Brave calls: it only widens the `site:` lists inside the existing official and fact-checker queries. A state-government query was **not** added (see below).

State hints (not built): one more call per claim would raise the worst case to about 25 calls (27.5 s of pure throttle) against the 30 s deadline and 48 s total budget, leaving no room for request latency. The existing `site:gov.in` query already reaches state portals under `*.gov.in`.

## Proposing a new source

Open a pull request that adds the domain to `sach/fetch.py` and a row to this file with: what the body is, why its site is authoritative (statute, regulator, or its own site for claims about itself), and a URL you loaded plus the date. Acceptable evidence: the body's own site, a link to it from a `*.gov.in` page, a regulator's notice, or the IFCN signatory list for fact-checkers. Do not add a domain from memory. Add tests for the host, a subdomain, uppercase, a prefix lookalike and a suffix-append lookalike. When unsure, leave it out: an unlisted source only means UNVERIFIED, a wrong official source can mean a wrong TRUE or FALSE.

**Removed on 2026-11-12:** `altnews.in` (Alt News). IFCN lists it as an expired signatory (last approval 2019), so it no longer counts as a fact-checker source. Rows already in the public ledger that cite it are historical records and are left as they were.

## PIB debunk index: growth (INDEXGROW, 2026-11-13)

`data/pib_index.jsonl` now holds 359 PIB releases (351 + 8). The match layer (`sach/match.py`) uses only the records whose headline carries a strict debunk word and which have a release date: 82 records after this change (74 before).

**How a record is added.** `python scripts/add_pib_debunks.py PRID [PRID ...] [--dry-run]` fetches `https://pib.gov.in/PressReleasePage.aspx?PRID=N` with the app's honest User-Agent and at least 1.1 s between requests (no retries, no bot-check evasion; pib.gov.in/robots.txt returns an HTML page, not rules). Title, date, ministry and excerpt come from the page itself; nothing is typed in. A PRID is added only if the page loads, has a "Posted On" date and its title passes the same strict-word test as the match layer. Candidate PRIDs come from searching `site:pib.gov.in`; the script then verifies each on the live page.

**Added (all fetched 2026-11-13):** 1980375 (Airport Authority of India, fake recruitments), 2085532 (Railways, free Maha Kumbh travel reports "entirely baseless and misleading"), 1563836 (Food Corporation of India fake appointment letter), 2163332 (Labour, fake PMVBRY portals), 2104089 (Rural Development, fake NRDRM recruitment drive), 2009349 (Railways, fake RPF recruitment notification on RTUEXAM.NET), 1781247 (fake recruitments in AICTE's name), 1513134 (WCD, fake BBBP forms). Domain: pib.gov.in only.

**Why only 8.** Most PIB Fact Check debunks (the free-laptop scheme, free recharge, free scooty, fake RBI messages, morphed videos) are published as posts on X, Threads and Telegram and in the "Fact Check Done" PDF on static.pib.gov.in, not as `pib.gov.in` press releases with a PRID. The index format and `load_pib_records` need a PRID, a `pib.gov.in` URL and a headline date, so those cannot be recorded honestly without a new record type (tweet URL, date, tweet text). Searching `site:pib.gov.in` for debunk-style headlines returned mostly releases already in the index. Of the roughly 100 candidate releases examined, most were already indexed and many others lacked a strict debunk headline (for example "cautions against fraudulent..."), which the match layer would ignore.

**Free-laptop forward.** PIB Fact Check did debunk "Students Laptop Scheme 2026" / "National Student Laptop Scheme 2026" (search results show posts at https://x.com/PIBFactCheck/status/2048690628415148453 and a Threads post; relayed by newsonair.gov.in). I did not fetch the X posts and no `pib.gov.in` release exists, so it is not in the index and that forward still returns UNVERIFIED from the match layer. Supporting it needs a tweet-sourced record type, which is a code change to `load_pib_records` and was out of scope.

**Matching behaviour.** Matching is deliberately strict (two-way coverage 0.75, Jaccard 0.67, numbers, qualifiers, names, negation). A forward must repeat the debunked headline's distinctive words; loose rewordings fall through to the live layer. `tests/test_index_growth.py` pins 15 English and 10 multilingual rewordings that match and 27 near-misses that must not.

## PIB Fact Check posts on X (match layer)

Many of PIB Fact Check's best-known debunks (free laptop scheme, free recharge, fake RBI/bank messages, fake loan letters) exist only as posts on X, not as pib.gov.in press releases with a PRID, so the press-release index cannot see them. `data/pib_posts.jsonl` holds the ones Sach could verify; `sach/pibposts.py` loads them and `sach/match.py` offers them to the MATCH layer.

- **Attribution.** A match is shown as "PIB Fact Check (on X)", with the post's date and a link to the canonical `https://x.com/PIBFactCheck/status/<id>` page. It is PIB's verdict, never Sach's own, and it is never presented as a pib.gov.in release.
- **How a record is verified.** `scripts/add_pib_posts.py` re-fetches every post by id and accepts it only if: the author is exactly `PIBFactCheck`; the text carries #PIBFactCheck plus FAKE / FALSE / MISLEADING / "not announced" / "baseless"; it is not a reply, a quote of someone else's post, a repost, or a TRUE / partly-true confirmation; it states a concrete text claim (not video- or image-only); and the extracted claim is not garbled. Nothing is typed by hand. At most 3 posts are kept per near-identical claim family.
- **Discovery.** Post ids were found through fxtwitter's public search listing (`from:PIBFactCheck <topic>`), for ids only. The per-post fetch also goes through fxtwitter, a third-party reader. Links point to x.com. Risk: X or fxtwitter may change or restrict access; the records already on disk keep working, and refreshing needs the script to keep working.
- **Matching is stricter than for press releases.** Every `check_pair` rule applies unchanged, plus the distinctive wording must be near-identical (Jaccard >= 0.9, `POST_MIN_JACCARD`). A one-word difference ("tablets" for "laptops", "PM" for "National", a different year, a negation) therefore falls through to the live layer. The cost is that loosely worded forwards ("... register now") also fall through; that is deliberate: a wrong match is worse than a miss.
- **Coverage today:** 49 records (about 12 fake loan letters, 2 free-laptop, 2 recharge, 3 RBI/notes, 3 Income Tax, plus schemes, army and vaccine claims). No scooty, jobs or KYC records yet. The set is verified, not exhaustive.

### Excluded from the index: stale debunks (found by the 2026-11-13 evaluation)

A PIB debunk of a *fake notice* is time-bound: it can stop being a contradiction once the real announcement is made. PRID 2009349 (Feb 2024, fake notification for 4,208 RPF Constable and 452 Sub-Inspector posts on RTUEXAM.NET) was indexed by the index-growth run, and the evaluation then returned FALSE for the genuinely TRUE claim "RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors" (the real recruitment came later). That was one overclaimed FALSE, found and removed the same day; it is pinned out by `tests/test_index_growth.py`. Lesson: Sach has no notion of a debunk going stale. Until it does, prefer evergreen debunks (a scheme that does not exist, a rule that was not changed) over "fake recruitment/notice" releases.

## News tier, reference store and social signal (18 Nov 2026)

These three layers were added so that everyday questions and news events get an honest answer. **None of them can produce TRUE, FALSE or MISLEADING.** `sach/verdict.py` is unchanged and ignores the `news` tier; the test `tests/test_knowledge.py::test_news_evidence_can_never_decide_a_verdict` holds that line.

### Reference store (`data/reference.json`, `sach/refstore.py`, on by default, off with `SACH_REFSTORE=0`)
Dated facts copied by hand from government documents, each with its source link. Today: the central government holiday lists for 2026 and 2027.

| Year | Document read | Host |
|---|---|---|
| 2026 | DoPT O.M. F.No.12/2/2023-JCA dated 03.07.2025, in the copy circulated by Survey of India (gazetted and restricted lists for Delhi) | `surveyofindia.gov.in` |
| 2026 Bakrid | Change of the Id-u-Zuha holiday from 27 May to 28 May 2026 for offices in Delhi, in the copy circulated by ICMR on 25.05.2026 | `icmr.gov.in` |
| 2027 | DoPT O.M. No.12/2/2023-JCA dated 16.07.2026, in the copy circulated by the Department of Posts on 08.09.2026 | `utilities.cept.gov.in` |

Limits: the lists are for central government offices in Delhi. States choose three of their holidays locally and can move the four Moon-dependent dates, and the store says so on those rows. State holiday lists are not in the store yet. The PDFs are scans, so rows were typed by hand and checked against the text once; a wrong digit is possible and the source link is shown beside every date so a reader can check.

### News tier (`sach/news.py`, off by default, on with `SACH_NEWS_TIER=1`)
Used only when no official source was found for a claim. One extra web search that names fourteen outlets (`QUERY_HOSTS`), then the same fetch, quote check and AI judge as every other source. The first live test (18 Nov 2026) found the earlier unrestricted query returned nothing: the Google-grounded search provider answers first and returns only government and fact-checker pages. A query with `site:` names skips that provider. Only those fourteen outlets can be found; the longer owner list still decides what counts.

- **Outlets:** the list `NEWS_GROUPS` in `sach/news.py`: news agencies (PTI, ANI, UNI, Reuters, AP), national dailies and broadcasters, and large regional-language dailies. They are grouped by owner so two titles of one company count once (for example Times of India and The Economic Times). The list was written from general knowledge of the Indian press, not from a register; additions should name the owner.
- **Researched additions (19 Nov 2026):** `data/news_sources.json`, built by `scripts/build_news_sources.py` from a researched map of 1,560 official, news and fact-checker accounts across 16 languages, each verified from the organisation's own site, a verified badge or a government directory. It adds 80 news websites (about 60 owners, mostly regional-language TV and dailies) to the outlet list, 493 X/Instagram/Facebook/Threads handles of official bodies and news organisations to the social signal's "established accounts", and, per language, up to 8 outlets that a second, separate news query searches when the claim is not in English (a separate query because one naming every outlet would exceed Brave's 400 characters and Google's 32 words; their pages fill only the places the national outlets leave, since they are judged against the English translation and cannot confirm a claim yet). Left out: influencers and celebrities (a watch-list only, never a source), inactive accounts, rows without an evidence link, and government and fact-checker sites, which keep their own tiers. One company under several names is counted once (`ALIASES` in the script). The hand-written list always wins. A spot check of 20 handles against their evidence pages confirmed 14, found 2 missing and could not open 2; the map is good enough to count outlets, never to decide a verdict. Off with `SACH_NEWS_SOURCES=0`.
- **Public figures (19 Nov 2026):** `data/people.json`, built by `scripts/build_people.py` from a researched map of 1,498 accounts of 521 public figures most targeted by hoaxes (fake deaths, fake quotes, fake endorsements). Only rows with strong evidence are used (a verified badge, or a government, fact-checker, listed news, court or the person's own page): 581 own accounts of 396 people and 24 accounts named as fake in reports from 2019 on (an older suspended handle can be re-registered by someone else). About a third of the sheet cites fan sites, aggregators or Wikipedia and stays out, as do accounts of people who have died (a post there is not the person speaking) and impostor handles that are just the person's name (the real person may own it now). A private person (Sara Tendulkar) and a handle that is also a real person's name (`x:sonunigamsingh`) are left out by name. Use: the social signal says "from the person's own account" only when the claim names that person (a name word no other listed person shares, or the full name), and "from an account a fact-check or news report named as a fake account of" whenever one appears. Neither is evidence or changes a verdict. Off with `SACH_PEOPLE=0`.
- **REPORTED:** two independent owners report it. For a death: three, or two when one is a news agency.
- **Reported as not true:** two independent owners say it is not true (the usual shape of a death hoax).
- **No "no report" label.** An earlier version said NO RELIABLE REPORT when a claimed death was not found. It was removed on 18 Nov 2026: it was wrong in four different ways in one day (pages found but not confirmed, pages blocked, a search no provider could take, an unrecorded failure). Sach says nothing about news unless a listed outlet reports or denies the claim.
- **The news search yields news-tier evidence only.** An official page or a fact-check page it happens to find is dropped, so the extra search can never produce a verdict or add a citation (found by the independent review, 18 Nov 2026).
- **Known weak points:** many outlets reprint one agency story, so "two owners" can still be one original report; a news report can be wrong; an old article about an earlier event can be judged as support. The card says "reported", shows the outlets and says it is not an official confirmation.

### Social signal (`sach/news.py`, off by default, on with `SACH_SOCIAL_SIGNAL=1`)
X, Facebook and Instagram offer no free search API, and Sach does not log in to them or scrape them. One web search restricted to those three sites returns links to public posts. Sach counts the links by platform and names any that come from a short list of established accounts (`KNOWN_HANDLES`). It does not open or read the posts.

The count is shown as a signal and is never evidence. How many accounts post a claim does not show whether it is true: false forwards spread precisely because many genuine people share them. A verdict from post volume would turn popularity into truth, which is the failure this project exists to prevent, so that part of the request was deliberately not built.

### Whose death a news page reports (19 Nov 2026)
For a death claim, a news quote counts toward REPORTED only if the claim's person is the grammatical subject of a death verb in it: the name
directly before died / dies / passed away / is no more / breathed his last, with only an age, a comma, has/had or a "who ..." clause between,
and no "of" or possessive in front of the name. The same function (`stance.death_subjects`) reads the person from the claim; names match by
their last two words (one for a one-word name), spaces ignored. Also refused: "in a film / scene / serial", "in 1998" right after the verb,
and a page that says alive, recovering, hoax, rumour, fake, not true, denied or clarified. Everything fails closed: no person found, no count.
**Guaranteed:** "X's father/co-star died", "X mourns Y", "wife of X dies", "X said Y died", "X has not / nearly / reportedly died" never count.
**Not guaranteed:** a namesake's obituary, or a plain "X died" on a satire page; those rest on the three-owner threshold and the judge.
Measured on the four live pages that reported Giri Babu's death: all four owners still count. English only; claims in other languages reach
the news judge as their English translation.

### Public broadcaster as a news report (same switch as the news tier)
`newsonair.gov.in` (All India Radio) and `ddnews.gov.in` are on government hosts, but what they publish is news, not a government order. When the news search finds them they count as a news agency towards REPORTED. They are never upgraded to "official" by that search, so a broadcaster's report cannot produce TRUE through it.

### A published fact-check of the same claim (`sach/crcorpus.py`, `data/claimreview.sqlite`, on by default, off with `SACH_CR_CORPUS=0`)
- **Source:** the public Data Commons ClaimReview feed, `https://storage.googleapis.com/datacommons-feeds/claimreview/latest/data.json` (about 200 MB, refreshed daily; read on 18 Nov 2026: 94,295 feed items).
- **Kept:** 12,477 reviews dated 2023 or later from the fact-checker sites already listed above (`is_factchecker`), India editions only. Stored per review: the reviewed claim (300 characters at most), the rating words (kept in the file, never displayed), the publisher's site, the link, the date. No article text.
- **Use:** show-only, under an UNVERIFIED result, up to three links. It is not the match layer and cannot set a verdict or add a citation. **The publisher's rating word is not shown**: a "False" beside Sach's own UNVERIFIED would read as a verdict, so the reader opens the fact-check to see it.
- **Gate:** the reviewed claim must have exactly the same words (every word, counted, with nothing ignored) and the same numbers as the user's claim; only letter case, punctuation and word order may differ. Two independent reviews shaped this. With a word-overlap gate, 280 of 280 stored claims still matched after their city was swapped. With a gate that ignored short and common words, adding "not", swapping "old" for "new", a three-letter name or "India" for another country still matched. With the exact gate, 0 of 633 such edits match and 1,497 of 1,500 stored claims still find themselves. The price is low recall: it fires only when a forward is worded like the reviewed claim.
- **Publisher shown:** the fact-checker's site (for example `factly.in`). The feed's free-text author field is not used: it held reporters' bylines, one rating word and stray claim text.
- **Licence:** the feed records carry no `sdLicense` field. A search result on 18 Nov 2026 described the compilation as CC BY; the FAQ page that said so now redirects, so this was not read at the source. Sach stores short claim text and a link with the publisher named.
- **Refresh:** `python scripts/harvest_claimreview.py` rebuilds the file. Not scheduled.

### Recent official alerts (`sach/alerts.py`, off by default, on with `SACH_ALERTS=1`)
Opt-in: three reviews each found wrong matches from word matching (a place name that is also a person's name, "shower of praise"). It stays off until the area is read from each alert's own CAP record instead of its title.

The NDMA SACHET feed `https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml` (the feed marks itself "public domain"; 100 items when read on 18 Nov 2026, the oldest eleven days old). Read only when a claim mentions a hazard, with a 5 second timeout and a 10 minute copy in memory; a failed read shows nothing, never an old copy.

Hazard words match as whole words ("Train" is not rain, "Brainstorm" is not a storm). An alert is shown only when all three hold: it was issued in the last 24 hours; it is about the same kind of hazard as the claim (rain, storm, flood, earthquake, tsunami, heat, cold, landslide); and its area phrase ("... over Kamrup in next 3 hours") names a place the claim also names. The issuing office and common capitalised words are not places. The feed gives no expiry time, and many alerts last only hours, so the panel shows the issue time and disappears three hours after the check (for cached and shared results). About 30 of 100 feed items are written without an "over" phrase or in Hindi, Bengali or Telugu; those are never matched. Show-only; only links on the SACHET host are kept.
