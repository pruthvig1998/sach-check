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
