# Evaluation

> **Measured on earlier code.** This LLM-backed run (26/31, 0 overclaims) was taken at commit `dfbdaf2`, before the later hardening (second-opinion consensus, subject-word matching, safe fallback). A fresh LLM-backed run is pending: Gemini's free-tier quota was exhausted by testing. A fallback-mode run is in [`evaluation-fallback-run.md`](evaluation-fallback-run.md) (0 overclaims, 0 wrong verdicts, 23 safe abstentions); the unsafe pre-fix fallback run is kept in [`evaluation-fallback-run-before-safety-fix.md`](evaluation-fallback-run-before-safety-fix.md).

Mode: LLM stance; retrieval: PibRetriever, BraveRetriever.

- Claims: **31** (target was 100+; see limitations)
- Exact-match accuracy: **26/31**
- **Overclaimed FALSE (the unforgivable failure): 0**
- Label FALSE: 10/13 correct; 3 abstained as UNVERIFIED
- Label TRUE: 11/13 correct; 2 abstained as UNVERIFIED
- Label UNVERIFIED: 5/5 correct; 5 abstained as UNVERIFIED
- Seeded (PIB page was in data/seed_debunks.json; retrieval is partly circular): 7/10 correct
- Unseeded (retrieval had to find the page itself): 14/16 correct

| Claim | Label | Sach | Result |
|---|---|---|---|
| Central Government will reduce the retirement age of employees to 50 years. | FALSE | FALSE | ok |
| Government has ordered the closure of Ministries. | FALSE | FALSE | ok |
| Air India passengers from Chicago were made to pay three times the fare. | FALSE | FALSE | ok |
| WHO doctors are advising against wearing masks and social distancing. | FALSE | UNVERIFIED | miss (abstained) |
| PIB Fact-Check Unit has issued over 2,900 fact checks. | TRUE | TRUE | ok |
| The Cabinet has approved declaring the 14th of every month as National Mango Day. | UNVERIFIED | UNVERIFIED | ok |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register. | FALSE | FALSE | ok |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | FALSE | UNVERIFIED | miss (abstained) |
| A Health Ministry office memorandum on state holidays has been issued. | FALSE | FALSE | ok |
| Railways has issued a recruitment notification for 19,800 Constable posts in RPF. | FALSE | FALSE | ok |
| RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors. | TRUE | UNVERIFIED | miss (abstained) |
| The Cabinet Secretariat has advertised recruitment for 1,736 Field Assistant posts. | FALSE | FALSE | ok |
| The Centre has removed 55 lakh ration card holders from Punjab. | FALSE | FALSE | ok |
| Ration cards of people who do not provide Aadhaar numbers will be cancelled. | FALSE | FALSE | ok |
| The Railway Recruitment Board introduced a new method of result preparation for Level 1 results. | FALSE | UNVERIFIED | miss (abstained) |
| India Post is offering subsidies and prizes to people who complete an online survey or quiz. | FALSE | FALSE | ok |
| The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore. | TRUE | TRUE | ok |
| The Union Cabinet has approved a scheme to replace old trucks and buses in the Delhi-NCR area. | TRUE | TRUE | ok |
| The Union Cabinet has approved Nutrient Based Subsidy rates for Rabi 2026-27 on phosphatic and potassic fertilizers. | TRUE | TRUE | ok |
| The Union Cabinet has approved modernization of Command Area Development and Water Management under Pradhan Mantri Krishi Sinchayee Yojana. | TRUE | TRUE | ok |
| The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021 to March 2026. | TRUE | TRUE | ok |
| The Union Cabinet has approved integration and continuation of two schemes under SARTHAK-PDS. | TRUE | TRUE | ok |
| Railways has a recruitment process on for 1,20,579 vacancies notified in 2024 and 2025. | TRUE | TRUE | ok |
| Around 99.8% of ration cards have been seeded with Aadhaar. | TRUE | TRUE | ok |
| Railways plans to provide 50,000 jobs in financial year 2025-26. | TRUE | TRUE | ok |
| The Government has notified PIB's Fact Check Unit as a fact checker of the Central Government under the IT Rules 2021. | TRUE | TRUE | ok |
| Suspected fake news can be sent to the PIB Fact Check WhatsApp hotline 8799711259. | TRUE | UNVERIFIED | miss (abstained) |
| The Ministry of Culture has declared turmeric the national spice of India. | UNVERIFIED | UNVERIFIED | ok |
| The Union Cabinet has approved renaming all national highways after rivers. | UNVERIFIED | UNVERIFIED | ok |
| The government has declared the first monsoon rain day of each year a national holiday. | UNVERIFIED | UNVERIFIED | ok |
| Every household in India will receive a free solar-powered refrigerator next month. | UNVERIFIED | UNVERIFIED | ok |

## Limitations (read before citing these numbers)
- The set is tiny: every item was hand-verified from a PIB page actually fetched, not bulk-scraped. PIB has no listing page for debunks, and the RSS feed returns only the latest 20 items.
- The FALSE claims are paraphrases of PIB debunk titles and the retriever indexes those same pages, so FALSE recall here is optimistic (circular).
- Stance was judged by Gemini when GEMINI_API_KEY is set; the heuristic alone cannot confirm TRUE claims and abstains.
- Relabel disclosure: the first control ("free laptops to all students") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.
- Relabel disclosure 2: the RPF 4,208 Constable / 452 SI claim was first labelled FALSE (from PIB debunk 2009349), but that debunk was about a fake notice on one website; a genuine PIB release (PRID 2246142) lists those same vacancy numbers. Sach said TRUE; relabelled TRUE after inspecting the evidence. Two labels were changed after seeing results, so treat headline accuracy as indicative only.
- Retrieval varies run to run (Brave results change), so single-run numbers move by a claim or two.
- Official-domain rule is *.gov.in / *.nic.in / who.int, so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.
- A real 100+ evaluation needs a search provider (BRAVE_API_KEY) or a bulk crawl of PIB press releases.
