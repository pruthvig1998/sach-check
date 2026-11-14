# L4 retrieval measurement

Database: 732 releases (of which 372 harvested after the seed). 61 evaluation claims labelled TRUE or FALSE with a known source page.

Share of claims whose expected PIB release is among the candidates (no page fetches):

| Group | Switch off | Switch on |
|---|---|---|
| All claims | 14/61 | 14/61 |
| English claims | 14/28 | 14/28 |
| Other languages | 0/33 | 0/33 |
| Expected release already known before L4 (seed or old index) | 14/29 | 14/29 |
| Expected release NOT known before L4 (the honest test) | 0/32 | 0/32 |
| ...of which now present in the new database | 0/0 | 0/0 |
| ...of which absent from the new database | 0/32 | 0/32 |

A release can only be retrieved from the index if it was harvested, so the rows 'present' and 'absent' show the ceiling: this index helps for recent releases it holds and cannot help for pages it never saw. The window was fixed before looking at these claims (the newest press-release numbers, walked downwards). The harvest was stopped after 372 of a planned 1,500 because 81% of those pages were not in English, and the live pipeline translates non-English claims to English before searching PIB.

Capability probe (not an accuracy measure): 65 recent English releases harvested after the seed, each queried with its own first sentence: page among the candidates **0/65 with the switch off, 65/65 on**. This shows the mechanism works for a recent announcement no other list contains; it says nothing about how often real forwards concern such announcements.
