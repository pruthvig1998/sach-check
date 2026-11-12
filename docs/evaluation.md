# Evaluation

Mode: LLM stance; retrieval: PibRetriever, BraveRetriever.

- Claims: **9** (target was 100+; see limitations)
- Exact-match accuracy: **9/9**
- **Overclaimed FALSE (the unforgivable failure): 0**
- Label FALSE: 7/7 correct; 0 abstained as UNVERIFIED
- Label TRUE: 1/1 correct; 0 abstained as UNVERIFIED
- Label UNVERIFIED: 1/1 correct; 1 abstained as UNVERIFIED

| Claim | Label | Sach | Result |
|---|---|---|---|
| Central Government will reduce the retirement age of employees to 50 years. | FALSE | FALSE | ok |
| Government has ordered the closure of Ministries. | FALSE | FALSE | ok |
| Air India passengers from Chicago were made to pay three times the fare. | FALSE | FALSE | ok |
| WHO doctors are advising against wearing masks and social distancing. | FALSE | FALSE | ok |
| PIB Fact-Check Unit has issued over 2,900 fact checks. | TRUE | TRUE | ok |
| The Cabinet has approved declaring the 14th of every month as National Mango Day. | UNVERIFIED | UNVERIFIED | ok |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register. | FALSE | FALSE | ok |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | FALSE | FALSE | ok |
| A Health Ministry office memorandum on state holidays has been issued. | FALSE | FALSE | ok |

## Limitations (read before citing these numbers)
- The set is tiny: every item was hand-verified from a PIB page actually fetched, not bulk-scraped. PIB has no listing page for debunks, and the RSS feed returns only the latest 20 items.
- The FALSE claims are paraphrases of PIB debunk titles and the retriever indexes those same pages, so FALSE recall here is optimistic (circular).
- Stance was judged by Gemini when GEMINI_API_KEY is set; the heuristic alone cannot confirm TRUE claims and abstains.
- Relabel disclosure: the first control ("free laptops to all students") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.
- Official-domain rule is *.gov.in / *.nic.in / who.int, so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.
- A real 100+ evaluation needs a search provider (BRAVE_API_KEY) or a bulk crawl of PIB press releases.
