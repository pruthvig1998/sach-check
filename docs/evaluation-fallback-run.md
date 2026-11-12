# Evaluation (fallback mode)

> **This run was degraded; it does not measure the full system.** It is saved separately and does not replace `docs/evaluation.md`.

Measured on commit `ce3f4e94eb8d1e6658d3c6b8b126bb171b313576` (clean tree), 2026-11-12 (UTC).

Mode: FALLBACK: the LLM failed on 200 source judgements (quota/outage), so those sources fell back to the safe PIB-debunk-only check; retrieval: PibRetriever, BraveRetriever; judges: gemini-Tgvw (ready), gemini-DE3Q (ready), groq (ready), openrouter (ready).

- Claims: **50** (see limitations)
- Exact-match accuracy: **11/50**
- **Overclaimed FALSE (the unforgivable failure): 0**
- **Overclaimed TRUE (also an overclaim): 0**
- Wrong verdicts other than overclaims (e.g. MISLEADING where a TRUE/FALSE label stands): 0
- Label FALSE: 3/21 correct; 18 abstained as UNVERIFIED
- Label TRUE: 0/21 correct; 21 abstained as UNVERIFIED
- Label UNVERIFIED: 8/8 correct; 8 abstained as UNVERIFIED
- Seeded (the source's PRID is in data/seed_debunks.json or data/pib_index.jsonl; retrieval is partly circular): 3/20 correct
- Unseeded (retrieval had to find the page itself): 0/22 correct

## By language

| Language | n | Exact match | Abstained | Overclaimed FALSE | Overclaimed TRUE |
|---|---|---|---|---|---|
| en | 33 | 8 | 25 | 0 | 0 |
| hi | 6 | 1 | 5 | 0 | 0 |
| te | 6 | 1 | 5 | 0 | 0 |
| hinglish | 3 | 1 | 2 | 0 | 0 |
| tinglish | 2 | 0 | 2 | 0 | 0 |

Abstained = Sach said UNVERIFIED where the label was not UNVERIFIED (safe but a miss).

## Every claim

| Claim | Lang | Label | Sach | Result |
|---|---|---|---|---|
| Central Government will reduce the retirement age of employees to 50 years. | en | FALSE | FALSE | ok |
| Government has ordered the closure of Ministries. | en | FALSE | UNVERIFIED | miss (abstained) |
| Air India passengers from Chicago were made to pay three times the fare. | en | FALSE | UNVERIFIED | miss (abstained) |
| WHO doctors are advising against wearing masks and social distancing. | en | FALSE | UNVERIFIED | miss (abstained) |
| PIB Fact-Check Unit has issued over 2,900 fact checks. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Cabinet has approved declaring the 14th of every month as National Mango Day. | en | UNVERIFIED | UNVERIFIED | ok |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register. | en | FALSE | UNVERIFIED | miss (abstained) |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | en | FALSE | UNVERIFIED | miss (abstained) |
| A Health Ministry office memorandum on state holidays has been issued. | en | FALSE | UNVERIFIED | miss (abstained) |
| Railways has issued a recruitment notification for 19,800 Constable posts in RPF. | en | FALSE | FALSE | ok |
| RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Cabinet Secretariat has advertised recruitment for 1,736 Field Assistant posts. | en | FALSE | UNVERIFIED | miss (abstained) |
| The Centre has removed 55 lakh ration card holders from Punjab. | en | FALSE | FALSE | ok |
| Ration cards of people who do not provide Aadhaar numbers will be cancelled. | en | FALSE | UNVERIFIED | miss (abstained) |
| The Railway Recruitment Board introduced a new method of result preparation for Level 1 results. | en | FALSE | UNVERIFIED | miss (abstained) |
| India Post is offering subsidies and prizes to people who complete an online survey or quiz. | en | FALSE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved a scheme to replace old trucks and buses in the Delhi-NCR area. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved Nutrient Based Subsidy rates for Rabi 2026-27 on phosphatic and potassic fertilizers. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved modernization of Command Area Development and Water Management under Pradhan Mantri Krishi Sinchayee Yojana. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021 to March 2026. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved integration and continuation of two schemes under SARTHAK-PDS. | en | TRUE | UNVERIFIED | miss (abstained) |
| Railways has a recruitment process on for 1,20,579 vacancies notified in 2024 and 2025. | en | TRUE | UNVERIFIED | miss (abstained) |
| Around 99.8% of ration cards have been seeded with Aadhaar. | en | TRUE | UNVERIFIED | miss (abstained) |
| Railways plans to provide 50,000 jobs in financial year 2025-26. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Government has notified PIB's Fact Check Unit as a fact checker of the Central Government under the IT Rules 2021. | en | TRUE | UNVERIFIED | miss (abstained) |
| Suspected fake news can be sent to the PIB Fact Check WhatsApp hotline 8799711259. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Ministry of Culture has declared turmeric the national spice of India. | en | UNVERIFIED | UNVERIFIED | ok |
| The Union Cabinet has approved renaming all national highways after rivers. | en | UNVERIFIED | UNVERIFIED | ok |
| The government has declared the first monsoon rain day of each year a national holiday. | en | UNVERIFIED | UNVERIFIED | ok |
| Every household in India will receive a free solar-powered refrigerator next month. | en | UNVERIFIED | UNVERIFIED | ok |
| ⚠️ ज़रूरी सूचना: NTA ने NEET UG जुलाई 2020 की परीक्षा स्थगित कर दी है, नोटिस वायरल हो रहा है। सबको भेजो! | hi | FALSE | UNVERIFIED | miss (abstained) |
| खुशखबरी! केंद्र सरकार ने कर्मचारियों और पेंशनरों का महंगाई भत्ता 3% बढ़ा दिया है, 1 जुलाई 2026 से लागू। शेयर करें। | hi | TRUE | UNVERIFIED | miss (abstained) |
| सावधान! अब 2000 रुपये से ऊपर के UPI पेमेंट पर सरकार GST लगाने जा रही है। सबको फॉरवर्ड करो। | hi | FALSE | UNVERIFIED | miss (abstained) |
| रबी विपणन सत्र 2027-28 के लिए गेहूं का MSP बढ़ाकर 2610 रुपये प्रति क्विंटल कर दिया गया है, सरकार का बड़ा फैसला। | hi | TRUE | UNVERIFIED | miss (abstained) |
| बड़ी खबर: केंद्र सरकार ने 1 जनवरी से सभी साइकिल चलाने वालों को हर महीने 500 रुपये 'हरित यात्रा भत्ता' देने का फैसला किया है। | hi | UNVERIFIED | UNVERIFIED | ok |
| सेना के आधुनिकीकरण के लिए सरकार ने नया बैंक खाता खोला है, कैबिनेट का फैसला है और अक्षय कुमार ने शुरू किया है। सब दान करें। | hi | FALSE | UNVERIFIED | miss (abstained) |
| RBI గవర్నర్ గారి వీడియో వైరల్ అవుతోంది: RBI కొత్త పెట్టుబడి పథకం ప్రారంభించింది, అందులో డబ్బు పెడితే భారీ లాభాలు వస్తాయి. అందరికీ షేర్ చేయండి. | te | FALSE | UNVERIFIED | miss (abstained) |
| కేంద్ర మంత్రివర్గం PM-KISAN పథకాన్ని 2026-27 నుంచి 2030-31 వరకు కొనసాగించడానికి ₹3.15 లక్షల కోట్లు ఆమోదించింది. | te | TRUE | UNVERIFIED | miss (abstained) |
| కోవిడ్ వల్ల కేంద్ర ప్రభుత్వ ఉద్యోగుల LTC, లీవ్ ఎన్‌క్యాష్‌మెంట్, మెడికల్ అలవెన్సులు కట్ చేస్తారట. షేర్ చేయండి. | te | FALSE | UNVERIFIED | miss (abstained) |
| వృద్ధాప్య, వితంతు పింఛన్లు ఉన్న జాతీయ సామాజిక సహాయ కార్యక్రమాన్ని (NSAP) 2026-27 నుంచి 2030-31 వరకు ₹53,428 కోట్లతో కొనసాగించడానికి కేబినెట్ ఆమోదించింది. | te | TRUE | UNVERIFIED | miss (abstained) |
| కేంద్ర ప్రభుత్వం ప్రతి గ్రామంలో ఉచితంగా ఒక జత చెప్పులు ఇచ్చే 'పాదరక్ష యోజన' ప్రారంభించింది, రేపటి నుంచి నమోదు మొదలు. | te | UNVERIFIED | UNVERIFIED | ok |
| బేటీ బచావో బేటీ పడావో పథకం కింద ప్రతి ఆడపిల్లకు ప్రభుత్వం 2 లక్షల రూపాయలు ఇస్తుంది, ఈ ఫారం నింపి పంపండి. | te | FALSE | UNVERIFIED | miss (abstained) |
| Dhyan do! 1 January se RBI scribble ya likhe hue currency notes nahi lega, banks mana kar denge. Sabko forward karo. | hinglish | FALSE | UNVERIFIED | miss (abstained) |
| Sarkar ne kharif 2026-27 ke liye common paddy ka MSP 2441 rupaye per quintal tay kiya hai. | hinglish | TRUE | UNVERIFIED | miss (abstained) |
| Kal se sarkar har mobile user ko har mahine 5 kilo aam free dene wali hai, bas apna number register karo. | hinglish | UNVERIFIED | UNVERIFIED | ok |
| Petroleum ministry nunchi pettrol bunk dealership direct ga istunnaru ani newspaper lo ad vachindi, andaru apply cheyandi. | tinglish | FALSE | UNVERIFIED | miss (abstained) |
| UGC prakaram 2026 February list lo 32 fake universities unnayi ani prabhutvam cheppindi, andaru jagratta ga undandi. | tinglish | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet approved an incentive scheme for low-value BHIM-UPI person-to-merchant transactions with an outlay of Rs 1,500 crore for 2024-25. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Cabinet has fixed the MSP for milling copra at Rs 12,027 per quintal for the 2026 season. | en | TRUE | UNVERIFIED | miss (abstained) |

## Limitations (read before citing these numbers)
- The set is small (50 claims here). Every non-control row was checked by fetching the cited official page and reading it; rows are not bulk-scraped. PIB has no listing page for debunks and its RSS feed returns only the latest 20 items, so a real 100+ set needs more manual work or a crawl. Rows added in the v2 revision carry the fetch date in `verified_on`; the original 31 rows were verified in the original build and were not re-fetched.
- The Hindi, Telugu, Hinglish and Tinglish rows were written by an AI model and have not been reviewed by a native speaker. Real forwards are messier. Treat per-language numbers as a smoke test, not a measurement of how Sach does on real forwards in that language.
- Per-language groups are tiny (a handful of rows each), so one claim moves a percentage a lot.
- Rows marked `seeded` have their PIB page in the hand-seeded list or the harvested index, so retrieval for them is partly circular and their accuracy is optimistic. Many FALSE claims paraphrase PIB debunk titles for the same reason.
- Relabel disclosure: the first control ("free laptops to all students") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.
- Relabel disclosure 2: the RPF 4,208 Constable / 452 SI claim was first labelled FALSE (from PIB debunk 2009349), but that debunk was about a fake notice on one website; a genuine PIB release (PRID 2246142) lists those same vacancy numbers. Sach said TRUE; relabelled TRUE after inspecting the evidence. Two labels were changed after seeing results, so treat headline accuracy as indicative only.
- Retrieval varies run to run (live search results change), so single-run numbers move by a claim or two. The evaluation runs with the verdict cache switched off (`SACH_NO_CACHE=1`).
- Official-domain rule is *.gov.in / *.nic.in / who.int (plus a few listed hosts), so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.
- There are no true MISLEADING rows: PIB items tagged "misleading" are labelled FALSE, so a MISLEADING verdict on them counts as a wrong verdict here.
- The LLM failed on 200 source judgements during this run (quota/outage); those fell back to the safe PIB-debunk-only check.

## Previous runs

- None archived yet.
