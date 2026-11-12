# Evaluation

Mode: heuristic stance (no ANTHROPIC_API_KEY); retrieval: PibRetriever, BraveRetriever.

- Claims: **9** (target was 100+; see limitations)
- Exact-match accuracy: **5/9**
- **Overclaimed FALSE (the unforgivable failure): 0**
- Label FALSE: 4/7 correct; 3 abstained as UNVERIFIED
- Label TRUE: 0/1 correct; 1 abstained as UNVERIFIED
- Label UNVERIFIED: 1/1 correct; 1 abstained as UNVERIFIED

| Claim | Label | Sach | Result |
|---|---|---|---|
| Central Government will reduce the retirement age of employees to 50 years. | FALSE | FALSE | ok |
| Government has ordered the closure of Ministries. | FALSE | FALSE | ok |
| Air India passengers from Chicago were made to pay three times the fare. | FALSE | FALSE | ok |
| WHO doctors are advising against wearing masks and social distancing. | FALSE | UNVERIFIED | miss (abstained) |
| PIB Fact-Check Unit has issued over 2,900 fact checks. | TRUE | UNVERIFIED | miss (abstained) |
| Government will give free laptops to all students. | UNVERIFIED | UNVERIFIED | ok |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register. | FALSE | FALSE | ok |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | FALSE | UNVERIFIED | miss (abstained) |
| A Health Ministry office memorandum on state holidays has been issued. | FALSE | UNVERIFIED | miss (abstained) |

## Limitations (read before citing these numbers)
- The set is tiny: every item was hand-verified from a PIB page actually fetched, not bulk-scraped. PIB has no listing page for debunks, and the RSS feed returns only the latest 20 items.
- The FALSE claims are paraphrases of PIB debunk titles and the retriever indexes those same pages, so FALSE recall here is optimistic (circular).
- Heuristic stance cannot confirm TRUE claims, so TRUE items abstain. An LLM key is needed to test confirmation.
- A real 100+ evaluation needs a search provider (BRAVE_API_KEY) or a bulk crawl of PIB press releases.
