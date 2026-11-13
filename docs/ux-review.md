# UX review and submission assessment (written 13 Nov 2026)

Scope: how useful Sach is to someone checking one forwarded message, what would make it more useful, and how each change could
affect the hackathon score. Research only: no feature code was changed, nothing was pushed or deployed, and the production site
and every paid or live API were left alone.

## 1. How this was done, and what it cannot show

- Read: `sach/site.py`, `web.py`, `share.py`, `match.py`, `card.py`, `report.py`, `i18n.py`, `extract.py`, `pipeline.py`, `verdict.py`,
  `linkcheck.py` (panel), `legal.py`, `impact.py`, `scamsigns.py` (outline), `README.md`, `docs/*.md`.
- Ran the app locally on port 8893 with no keys, and used a browser tab at phone width (375 px) and desktop width, in dark and light
  themes. Local data files were redirected to a scratch folder. The tab is closed and the server is stopped.
- **Limit that matters:** with no keys the app runs in "limited mode" (no AI judge, no web search, no translation). I saw the MATCH
  layer (local PIB index) and UNVERIFIED results. I could **not** see a live TRUE, MISLEADING, or a live FALSE judged by an AI, so
  anything about those paths comes from reading the code, and is marked "(code reading)". Non-English results I saw were limited-mode too.
- I did not re-run the test suite (README claims 4,012 passing; unverified by me).
- Nothing below uses real users. There are none in the repo.

## 2. The user's journey, stage by stage

Each finding is tagged: **[verified]** = I reproduced it locally; **[code]** = read in the code only.

### Stage 1. Receiving a forward and arriving at Sach

What works: "Paste and check" is the first control inside the box; the how-to block picks an Android/iPhone/desktop route; the share
target auto-checks after a visible 3-second countdown that can be cancelled; nothing is sent to anyone automatically.

Confusing or missing:
1. **The box is two screens down on a phone.** [verified] At 375 px the textarea starts about 1,520 px into a 10,641 px page. The hero
   (headline, language line, a note on "Sach/nijam", three buttons) comes first. Someone who taps a friend's "Share Sach on WhatsApp"
   invite lands on marketing, not on the box. The home page has 11 sections after the hero (checker, link checker, install, trending,
   how, rules, sources, evidence, tip jar if configured, languages, FAQ, API).
2. **The easy path (share sheet) needs an install on Android and does not exist on iPhone.** [code, `share.py` HOWTO_HTML] Most people
   will end up at long-press, Copy, open site, "Paste and check". That works, but there is no data on how many get that far.
3. **Telegram bot** [code]: a real channel, but not where WhatsApp-first users are. It adds a second surface to keep correct.
   There is no WhatsApp bot; the repo cannot honestly claim one.
4. **Install/PWA, trending, ledger, API, impact, tip jar all sit on the same page as the checker.** They serve judges and developers,
   not the person with a forward in hand.

### Stage 2. Entering or correcting the text

What works: screenshots go through OCR and the text is shown for editing before checking (`share.OCR_REVIEW`); voice input exists;
"Reply in" lets you pick the card language; call-to-action fragments are removed so "click the link" is not "checked".

Confusing or missing:
1. **A classic scam forward gets a grey "NO CLAIM" stamp.** [verified] "free recharge for all students click here" returns
   `no_claims` (6 words with "click" are dropped by `extract._BOILER`). The page says "Greetings, links, emoji and bare numbers are
   not factual claims". The scam-signs box does appear ("Promises a prize or free gift") but under a stamp that reads as "nothing here".
2. **Silent drops.** [verified] In "...will receive a free solar-powered refrigerator next month. Last date to register is tomorrow.
   Forward to 10 groups." the deadline sentence was dropped without a word; only the first sentence was judged. "PM Kisan 2000 rupees
   will be credited. Click here to claim" checks only the first sentence. Short sentences (< 4 words) and short call-to-action
   sentences (< 9 words) vanish. The user is never told which sentences were not checked.
3. **Silent claim cap.** [verified in `extract`; code in `pipeline.MAX_CLAIMS = 5`] A forward with 9 claim sentences returns a verdict
   on the first 5. Nothing says "we checked 5 of 9". "TRUE only if every claim is TRUE" then applies to the checked five.
4. **4,000-character limit is silent in the browser.** [code] The textarea has `maxlength=4000`, so a longer paste is cut by the
   browser, and "Paste and check" does `slice(0, maxlength)`. The friendly "too long" message in `web.py` is only reached by API
   callers. Real chain forwards can exceed 4,000 characters.
5. **"We understood the forward as..." is in English only and sits low on the page.** [code, `site.result_block`] For a Telugu
   sender the English rendering cannot be checked by the sender; it helps a bilingual reader or a judge. The original-language claim
   is in the claims table, which is the part the sender can actually verify.
6. **Non-English accuracy depends on translation being available.** [verified, limited mode] The English "Retirement age ... reduced"
   forward matched PIB's debunk; the same claim in Tamil returned UNVERIFIED locally because there was no translator. In production a
   translator and fallbacks exist (README), so I cannot say how often this bites live.
7. **Honesty inconsistency.** `site.py` line 765 says Hindi and Telugu wording is "human-written"; `i18n.py` line 1 says the templates are
   human-written; README and `docs/languages.md` say all non-English wording is AI-written and unreviewed. A reader who finds both
   will distrust the cleaner one. Fix the two lines.

### Stage 3. Understanding the verdict and the source

What works: verdict first, one plain line, citation link; "UNVERIFIED" wording says "Do not treat it as fact"; a MATCH stamp shows PIB's
own rating word ("Fake") and "Rated by PIB Fact Check" instead of Sach's own label; scam-sign advice never changes a verdict;
rate-limited and busy states are explicit.

Confusing or missing:
1. **A 2020 debunk looks current.** [verified] "Retirement age of Central Government employees has been reduced." (no year) is shown as
   "Already fact-checked by PIB Fact Check ... on 26 Apr 2020: rated Fake". The date is printed but nothing says it is six years old.
   `match.py` exempts PIB from the 5-year age limit (`_fresh(..., is_pib)`) and the matcher accepts a claim with no date or number. If
   the rule did change, the card would call a true new notice "Fake". There is no age or "may have changed" warning anywhere.
2. **The MATCH citation is mislabelled.** [verified] The citation row reads "accessed 2020-04-26". For a match, `date_accessed` is set
   to the PIB review date (`verdict_from_match`), so Sach looks like it accessed the page in 2020.
3. **No source sentence.** [verified] Citations show a name, tier and date. The sentence an AI judge relied on is validated in
   `stance.validate_stance` and then thrown away: `judge()` returns only a label string, and `build_trace` stores title and stance
   only. (For a MATCH the page shows PIB's headline as "What they checked", which is close to what (a) asks for.)
4. **Limited-mode and search-down notices are below the fold and not on the forwardable card.** [verified] On an UNVERIFIED result the
   order is: stamp, card, buttons, "Ask a human fact-checker", warning signs, then "Limited mode..." near the bottom. The card text and
   the WhatsApp message say "We found no official source", which is untrue when search was off and no AI ran: nothing was found because
   little was looked for. The tipline message Sach pre-fills (`match.escalation_text`) also says "no official source was found".
   (Telegram's reply does add a "my AI checker is busy" line; the web card does not.)
5. **Multi-claim cards misname the claim.** [verified] The text that is shared to WhatsApp and the downloadable image take
   `claims[0]` as "the claim checked" (`share.build_share_text`, `report.card_data`). With "Union Cabinet approved the coal gasification
   scheme..." (claim 1, UNVERIFIED) followed by the Corona Sahayata Rs 1000 forward (claim 2, FALSE), the share text is:
   "FALSE / PIB says this claim is false / Source: PIB ...PRID=1618314 / Claim checked: 'The Union Cabinet has approved a scheme for
   coal...'". A FALSE stamp is attached to a real-sounding announcement, and the cited debunk belongs to a different claim. The same
   shape (verdict from the worst claim, claim text from the first) is in the image. The PIB report flow uses the right claims.
   This is the one place where Sach could push a wrong "FALSE" into a family group, which the README says it refuses to do.
6. **Mixed cards do not say which claim is which.** [verified] A forward with one matched and four live claims produced a card that
   reads "Part of this message was already fact-checked by others ... Sach's own check of the rest: FALSE" without naming the FALSE
   claim, and the three UNVERIFIED claims are not on the card.
7. **Internal vocabulary leaks.** The trace says "Which layer answered: ESCALATED / MATCH / LIVE", "reason code", and stances such as
   CONFIRMS or NEITHER. A person reads "ESCALATED" as "sent to a human", which Sach does not do. The matchbox title ("A published
   fact-check matches this"), the stamp and the card say the same thing four times; one result is about 1,770 to 1,980 px tall on a phone.
8. **MATCH cards are English-only in 14 of 17 reply languages.** [verified, Tamil] `match.HEAD/LINE/NOTE` exist only for en, hi, te; `tr()` falls
   back to English. A Tamil reader asking for a Tamil reply gets the English MATCH card, the most common FALSE path. It cannot be
   fixed safely without a native reviewer; at minimum say so in `docs/languages.md`.
9. **"First checked on ... This is a stored result for a repeated message"** [verified] is shown to someone who never checked it
   before (the cache is global). It reads as if the user did something wrong.
10. **The link/number panel is English-only inside a Hindi or Telugu result** [code, `panel_html(text)` is called without a language].
11. **TRUE can be over-trusted** [code]. TRUE means "an official page confirms this sentence", not "this applies to you now". Live
    evidence has no publication date (`Evidence` holds only `fetched_at`), so an old announcement and a current one look the same, and
    the "apply by" sentence that came with it is usually dropped by item 2 above.

Strengths to keep: the scam-warning signs (deterministic, localised for hi/te, never touch the verdict) and the link checker are the
parts most useful to a non-technical person, because many harmful forwards are scam links and UPI traps with no checkable fact.

### Stage 4. Deciding whether to share a reply

What works: "Share on WhatsApp" opens a prefilled message; the PIB report flow only opens PIB's own channels and sends nothing; the
tipline buttons only open WhatsApp with a prefilled question and send nothing.

Confusing or missing:
1. **The loudest button is always "Share on WhatsApp"**, including on UNVERIFIED and on limited-mode results. An UNVERIFIED card in a
   family group can be read as "nobody knows, so maybe true".
2. **Shared text drops the caveat, the claim mapping (item 3.5), and the age of the source.** [verified]
3. **"Report a wrong verdict" opens a pre-filled GitHub issue.** [code] A non-technical WhatsApp user does not have a GitHub account.
   The only other route is an optional contact email that may not be configured (`legal.contact_email`).
4. **Escalation** lists PIB Fact Check, BOOM, Vishvas News and Newschecker with prefilled `wa.me` links. The numbers carry dated
   verification notes in `match.py`. It is shown for every live UNVERIFIED, including limited-mode and search-down ones (see 3.4).
5. **Tip jar** [code]: when UPI is configured a joke line ("Celebrate with a samosa for the desk") appears under a TRUE or FALSE result
   (`TIP_QUIPS`). On a serious verdict, this looks like monetisation next to a safety message.
6. **Privacy:** the permalink stores the full forward text for 6 hours to 7 days (`share.ensure_share`). `legal.py` says so, so this is
   disclosed, but the FAQ line "Only the individual claims ... go to the public ledger" leaves it out.

## 3. Ranked suggestions

Hours are for one person who knows the codebase, including tests; they are not padded or trimmed. "Safety risk if built" is the risk
that the change itself produces a wrong or misleading output. Criteria: problem size, severity, solution quality, proven impact.
The last column says which criterion a change could move, and in which direction, as my judgment; more features do not by themselves
raise any score, and several rows say "none".

| # | Suggestion | User benefit | Safety risk if built | Hours | Likely effect on the four criteria |
|---|---|---|---|---|---|
| 1 | **Fix share text and image to name the claim that drove the verdict** (and its citation); for mixed forwards add one line per claim (checked mark, cross, question mark) capped at 3 | H: removes the one path to a wrong "FALSE" in a group | L: it removes a wrong pairing; must be tested on mixed MATCH and live results | 2 to 3 | Solution quality: small plus (a reviewer who tries a two-claim forward will otherwise find it). Others: none |
| 2 | **Honest wording when the check was incomplete** (limited mode, search down, timed out): card and tipline text say "we could not finish the check" instead of "no official source found"; move the notice above the buttons; make "Share" quieter than "Try again later" | H | L: text only; stays UNVERIFIED | 2 | Solution quality: small plus. Others: none |
| 3 | **(c) A more useful UNVERIFIED**: one line saying what was looked at (PIB archive, official sites, how many pages judged, from the trace), what UNVERIFIED does not mean ("not 'probably true'"), what to do next (do not forward; ask PIB or a tipline; check any link in the link checker), and a scope note ("PIB covers Union government; for a state matter ask that state") | H: UNVERIFIED is the most common result (44 of 78 live claims in the fallback run abstained) | L: text only, verdict untouched; wording must not hint at a probability | 3 to 4 (English, Hindi, Telugu; other languages fall back to English until reviewed) | Solution quality: plus (UNVERIFIED handling is where users meet the product's limits). Severity: none. Proven impact: none |
| 4 | **(b) Old-notice warning, MATCH only**: if the matched review is older than 12 months, add "This is a debunk from <month year>. Rumours return; if the forward has new details, do not rely on it." Relabel "accessed" to "reviewed" for matches | H: the verified 2020 case shows the gap | L: only adds a caution; do not change the verdict or hide the match | 2 | Solution quality: small plus. Others: none |
| 5 | **(b) Passed-deadline warning**: find dates in the forward ("last date 31 March 2021", "31/03/2021") that are before today, and say "This date has passed; the forward may be old". English and numeric formats first | M to H: old deadlines are a common recirculating pattern | M: a regex can read the wrong date (a year of birth, an event date) and call a live notice old. Show it as "contains a date that has passed", never "expired", and never alter the verdict | 4 to 6 (8+ if Hindi/Telugu month names are included) | Solution quality: small plus. Others: none. Worth doing only after rows 1 to 4 |
| 6 | **(a) Show the exact validated source sentence, live path**: return the verified quote from `llm.stance`, keep it on `Evidence`/trace, show "From the page: '...'" under the citation | H: it is the clearest "why should I believe this" cue | M: touches the three judge providers and the consensus step; a quote can be a fragment and be misread as a statement about the claim; the degraded heuristic path has no quote. Show only quotes that passed `validate_stance`, with the page title, and never for stance "none" | 6 to 9 | Solution quality: plus, mostly as visible proof of the validation design. **Changes code the evaluation measures, so it must land before the final evaluation run** |
| 7 | **(a) for MATCH**: show the first sentence of the PIB release (the index already holds an excerpt) next to PIB's headline | M | L | 1.5 to 2 | Solution quality: small plus |
| 8 | **Multi-claim and dropped-sentence honesty**: "Checked 5 of 9 sentences", list sentences that were not checked ("Not checked: 'Last date is tomorrow'") | H | L: more text, no verdict change | 3 to 4 | Solution quality: plus (this removes silent behaviour) |
| 9 | **No-claim result for scam-shaped text**: if scam signs fire (prize, link, urgency) lead with the warning and say "No checkable fact, but this looks like a scam pattern", not a grey stamp | M to H | L | 1 to 2 | Severity: small plus (scam coverage is the severe part). Solution quality: small |
| 10 | **Visible truncation message** at 4,000 characters; "we checked the first 4,000 characters" | M | L | 0.5 to 1 | None |
| 11 | **Shorter phone path to the box**: shrink the hero, put the box (or a sticky "Paste and check") above the fold; move trending, API, tip jar lower or onto separate pages | M to H for a first visit | L | 1 to 2 | None directly; makes a judge's first try easier |
| 12 | **Fix "human-written" lines** in `site.py:765` and `i18n.py:1` to say AI-written, unreviewed | L for users, M for trust | L | 0.25 | Solution quality: avoids an honesty inconsistency |
| 13 | **(d) Optional anonymous, consent-aware feedback for a pilot** (see notes below the table) | M for the user; the only route to any impact figure | M: personal-data and consent handling; spam; small-N numbers can look weak | 5 to 7 for the in-app version; 1 to 2 for a no-code form | Proven impact: the only row that can move it. With no respondents: none. Others: none |
| 14 | **Replace the GitHub-only "Report a wrong verdict"** with a one-tap "This looks wrong" that stores verdict, language and a hash of the claim (no text unless the person adds it), plus a mailto fallback | M to H | L to M: it collects data; same consent text as row 13 | 2 on top of row 13; 0.5 for mailto only | Solution quality: small. Proven impact: only through row 13 |
| 15 | **Sourced problem-size and severity text** for the submission form and README (see section 4) | n/a | L: the risk is an unsupported number; use only figures that were opened and linked | 2 to 3 | **Problem size and severity** (together 50% of the score per the form): the largest expected effect per hour of anything here |
| 16 | **Clean full evaluation on the commit that is deployed** | n/a | none | 1 to 3 of work, plus waiting for quota | Solution quality: plus; Proven impact: partial (accuracy evidence, not usage). See section 4 |
| 17 | Remove the joke "tip" line from result pages; keep the tip section lower on the page | L to M (tone) | L | 0.3 | None |
| 18 | Plain-language trace: "Which layer answered" becomes "How this was checked: matched an existing PIB fact-check / checked live / could not finish" | M for curious users | L | 1 | None |
| 19 | Pass the result language to the link panel; reword "stored result for a repeated message" | L | L | 0.5 | None |
| 20 | Pilot with real people, no code (see notes) | n/a | L if consent is clear | hours of outreach, not coding | Proven impact: the only honest source of field evidence |

**Notes on the four already-chosen items**

- **(a) source sentence.** Real value, and the most invasive. The MATCH half is cheap and mostly exists. The live half changes the
  judge path, so it competes with the evaluation run for the same remaining time. If built, show nothing when the stance is "none" or the
  run was degraded, and show the page title and a link with the sentence so it is not read as PIB speaking about the user's claim.
- **(b) old notices and passed deadlines.** Do the MATCH-age part (row 4): the evidence is already on the page and the risk is
  low. The passed-deadline part (row 5) is real value but a regex can be wrong; keep it as a soft notice and English-first. Live
  sources have no publication date today, so "this source is old" for a live TRUE needs a date-extraction step I would not start now.
- **(c) useful UNVERIFIED.** Best value for its hours. Bundle with row 2: the same lines must change for "incomplete" vs "nothing found".
- **(d) feedback flow.** The code is the easy part. A flow with nobody using it produces no evidence, and a flow that stores text without
  clear consent is a privacy problem (India's Digital Personal Data Protection Act, 2023, may apply to anything that can identify a
  person; I am not giving legal advice, so keep it anonymous and ask someone qualified if unsure). Minimum version: an unticked
  consent box, then two taps ("Was this useful?", "Did you forward it?") and an optional note; store verdict, language, layer, the two
  answers and a date; no IP, no forward text, no cookie; show "n = ..." on the impact page; update the privacy page before it
  goes live. The cheaper alternative is an external form plus 5 to 10 short conversations, written up as a pilot note.

**Skip (do not build before 15 Nov):**
- More languages, or more translated strings without a native reviewer. A wrong word on a verdict card is worse than English.
- A WhatsApp Business bot (approval, cost, and cannot be finished and tested in time). Telegram polish.
- Widening the official-source list or adding fact-checkers to hit more claims: it raises overclaim risk (`docs/sources.md` says it grows slowly).
- Confidence percentages, "probably true/false" labels, or any score shown for UNVERIFIED. It implies a precision the system lacks.
- Streaks, badges, leaderboards, a bigger trending page, more dashboards, voice changes, new tip tiers.
- Any "send it for me" feature. "Sach sends nothing" is a safeguard.
- Re-labelling the stamp for multi-claim forwards ("contains a false claim") in 17 languages without review. Use row 1's
  per-claim lines instead.

## 4. Candid assessment against the four criteria (25 points each)

These are my estimates from the repo, not the organizers' numbers; I cannot see the rubric details, other entries, or the scores
judges would give. Ranges are wide on purpose. Ties are broken first by Proven impact, then by Size.

| Criterion | Current estimate (of 25) | Range |
|---|---|---|
| Problem size | 16 | 13 to 19 |
| Severity | 16 | 13 to 19 |
| Solution quality | 18 | 14 to 21 |
| Proven impact | 4 | 1 to 8 |
| **Total** | **about 54** | **about 41 to 67** |

The form says scale and severity together are 50% of the score and optional deployment and impact data 25%. That matches the weak
spots: the repo is strongest on build and weakest on evidence of use.

**Problem size.** Evidence in the repo: README "Why" (a plausible argument that corrections exist but do not reach WhatsApp groups);
`docs/languages.md` (coverage "about 90% of Indians by first language", Census 2011 cited); 17 language codes. Missing: no sourced
number for how many people receive forwards, how often, or how much misinformation is in scope. The "Why" section asserts the problem
without a figure or a link. Scope is also narrow by design (central-government claims; state and private-sector claims are mostly
UNVERIFIED, README Limitations), and the repo does not estimate what share of real forwards that covers. Realistic improvement in two
days: a short, sourced paragraph for the form with three to five statistics that someone has opened and linked (user counts, a
published study, PIB Fact Check's own volume), and a small coverage count from material already in the repo (for example how many
of PIB's own debunks in `data/pib_index.jsonl` are central-scheme, money, health). Do not paste a number from memory.

**Severity.** Evidence: the scam-warning signs, the link/number/UPI checker, the red-team set (`docs/red-team.md`, `data/red_team.json`),
the rule that a wrong FALSE is the unforgivable failure, and the debunks in the index (fake Rs 1000 scheme, fake retirement-age cut, fake
recruitment notices) which are real PIB pages. Missing: the repo never says what harm each category causes or to whom, and nothing
documents a person actually losing money or acting on a rumour. Improvement: a severity paragraph built from the real PIB debunks
already in the repo (with their PRIDs) arranged by harm type (money loss, health, public order), plus a candid note that Sach's most
severe-harm features are the scam signs and link checker, which need no source match. Do not suggest harm numbers that were not read
from a source.

**Solution quality.** Evidence: hard verdict rules in pure code (`sach/verdict.py`) with a rules table in the README; verbatim-quote and
number validation (`sach/stance.py`); a second model must agree; 53 adversarial cases (`data/red_team.json`) run offline in tests;
honest degraded modes; a MATCH layer that credits PIB by name; 17 language codes; PWA, Telegram, link checker. Weak spots I verified:
the share-text claim mismatch (3.5), silent sentence drops and claim cap (2.2, 2.3), old-debunk presentation (3.1), the incomplete-check
wording (3.4), English-only MATCH cards in 14 languages (3.8). Evaluation is not clean:
- `docs/evaluation.md` still holds an older run (26/31, 0 overclaims) marked "measured on earlier code";
- `docs/evaluation-fallback-run.md` (79 claims, commit `acb67af`, 13 Nov) is explicitly degraded: 33/79 exact, 0 overclaimed FALSE or TRUE,
  2 other wrong verdicts, 44 safe abstentions (22 FALSE-label and 22 TRUE-label claims), 21 judge failures and 9 search failures;
- the README says no accuracy figure is published until a clean full run, which is the right call;
- `data/eval_summary.json` is the old format, so the site shows "Evaluation pending";
- the red-team report in `docs/red-team.md` lists 35 cases (limited mode) while the README says 53;
- non-English rows are AI-written, 2 to 6 per language, and the rows paraphrase PIB titles (flatters recall).
So what the repo can defend is: "no overclaims found in the runs done, degraded runs say so, and the clean run is not yet in".
**AgentFoundry:** the form has a required confirmation "Built using AgentFoundry" and a field for how it was used. Nothing in the repo
mentions AgentFoundry, and the task statement says Sach has not used it. I do not know what AgentFoundry provides or how strictly
the confirmation is checked. Do not tick that box or describe a history that did not happen. The options are: ask the organizers
in the repo's issues or by the listed contact whether it is mandatory and what counts, or decide, with the real time left, whether any genuine use is
possible. If it cannot be honestly confirmed, the submission may be ineligible or may lose credibility; that is a larger risk than any
UX item here.

**Proven impact.** Evidence: the impact page and JSON endpoint (`sach/impact.py`), `scripts/snapshot_impact.py`, the evidence-snapshot format
(`evidence/README.md`), and the ledger. Missing: there is no snapshot file (the `evidence/` folder holds only its README), no
pilot, no named user, no outcome (did anyone stop a forward or change their mind), and the counters cannot tell testers from users. The
git history of this branch spans 12 to 13 Nov 2026, so there is also no long usage history. Default budgets (6 live checks per
minute, 100 per day, per the README) would also make a pilot of more than a few dozen people hit "very busy"; I could not see
what the deployed settings are. Realistic improvement before 15 Nov: (1) one clean evaluation run on the deployed commit, reported
as accuracy on a small set, not as usage; (2) a small, consented pilot with real people who receive forwards, reported with its
exact N and who they are (for example "9 relatives and colleagues"), including the checks that went badly; (3) a frozen snapshot via
the script with a line that says the counts include the team's own testing. A pilot of 10 to 30 people will not look large; it
will be real, and ties go to Proven impact first. Expect roughly +2 to +5 points here if it happens, and nothing if it does not.

**What matters more than any UX change.** In order: (1) settle the AgentFoundry confirmation honestly; (2) write the sourced scale and
severity text; (3) make the evaluation clean on the final commit; (4) get a few real people to use it and say what happened; (5) fix
the share-text mismatch and the incomplete-check wording, since a judge testing a two-claim forward would hit them.

## 5. Order of work

Today is 13 Nov and the plan file freezes on the evening of 14 Nov. Any change to `pipeline.py`, `llm.py`, `stance.py`, `match.py` or `verdict.py`
after the evaluation run makes that run a measurement of older code, so do code changes first, then run the evaluation, then take the
snapshot.

**Do now**
1. Share-text and image claim mismatch (row 1), incomplete-check wording (row 2), MATCH age notice and "reviewed" label (row 4).
2. A more useful UNVERIFIED (row 3), "human-written" lines (row 12), truncation message (row 10), multi-claim honesty (row 8).
3. Settle AgentFoundry with the organizers; write the sourced scale and severity text (row 15).
4. Recruit the pilot (row 20) with a consent text and a no-code form, since recruiting takes the longest.
5. Then: clean full evaluation on the final commit; snapshot the impact numbers with an honest caption.

**Do only if time**
- Phone layout (row 11) and scam-shaped no-claim result (row 9), both quick.
- MATCH release sentence (row 7); plain trace wording (row 18).
- In-app feedback (rows 13 and 14) if the form shows people are willing to use it. Otherwise keep the no-code form.
- Passed-deadline notice (row 5), English first.

**Skip**
- Live-path source sentence (row 6) unless there is a full day left and the evaluation can still be run after it.
- Everything listed under "Skip" in section 3.
