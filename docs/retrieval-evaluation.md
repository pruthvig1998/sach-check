# Retrieval evaluation (no LLM involved)

For 26 eval claims whose source PIB page is known: does retrieval put that exact page in front of the judge?

- **Brave live search only** (no local knowledge): **23/26**
- **Local PIB seed + harvested index** (351 indexed releases): **14/26** (partly circular: the index was built from searches on the same topics)
- **Combined (what the app uses): 24/26**
- Items whose page is in neither the seed nor the index (11): Brave found 10/11, combined 10/11

| Claim | PRID | Brave | Local | In seed | In index |
|---|---|---|---|---|---|
| Central Government will reduce the retirement age of employees to 50 years. | 1618590 | no | yes | yes | yes |
| Government has ordered the closure of Ministries. | 1616896 | yes | yes | yes | yes |
| Air India passengers from Chicago were made to pay three times the fare. | 1622056 | yes | yes | yes |  |
| WHO doctors are advising against wearing masks and social distancing. | 1616527 | no | no | yes | yes |
| PIB Fact-Check Unit has issued over 2,900 fact checks. | 2247720 | yes | yes | yes | yes |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to r | 1618314 | yes | yes | yes | yes |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | 2216041 | yes | yes | yes | yes |
| A Health Ministry office memorandum on state holidays has been issued. | 1606395 | yes | yes | yes | yes |
| Railways has issued a recruitment notification for 19,800 Constable posts in RPF. | 1890076 | yes | yes |  | yes |
| RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors. | 2246142 | yes | no |  |  |
| The Cabinet Secretariat has advertised recruitment for 1,736 Field Assistant posts. | 2130875 | yes | yes |  | yes |
| The Centre has removed 55 lakh ration card holders from Punjab. | 2160367 | yes | yes |  | yes |
| Ration cards of people who do not provide Aadhaar numbers will be cancelled. | 1623051 | yes | yes |  | yes |
| The Railway Recruitment Board introduced a new method of result preparation for Level 1 re | 1567621 | yes | no |  |  |
| India Post is offering subsidies and prizes to people who complete an online survey or qui | 1819189 | yes | yes | yes | yes |
| The Union Cabinet has approved a scheme for coal and lignite gasification projects with an | 2260621 | yes | no |  |  |
| The Union Cabinet has approved a scheme to replace old trucks and buses in the Delhi-NCR a | 2268342 | yes | no |  |  |
| The Union Cabinet has approved Nutrient Based Subsidy rates for Rabi 2026-27 on phosphatic | 2334972 | yes | no |  |  |
| The Union Cabinet has approved modernization of Command Area Development and Water Managem | 2120362 | no | no |  |  |
| The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021  | 1742290 | yes | no |  |  |
| The Union Cabinet has approved integration and continuation of two schemes under SARTHAK-P | 2265788 | yes | no |  |  |
| Railways has a recruitment process on for 1,20,579 vacancies notified in 2024 and 2025. | 2198345 | yes | no |  |  |
| Around 99.8% of ration cards have been seeded with Aadhaar. | 1988732 | yes | no |  |  |
| Railways plans to provide 50,000 jobs in financial year 2025-26. | 2143531 | yes | no |  |  |
| The Government has notified PIB's Fact Check Unit as a fact checker of the Central Governm | 2015792 | yes | yes |  | yes |
| Suspected fake news can be sent to the PIB Fact Check WhatsApp hotline 8799711259. | 2206735 | yes | yes | yes | yes |
