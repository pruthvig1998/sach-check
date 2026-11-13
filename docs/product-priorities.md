# Product priorities

Based on Astra's code review on 13 November 2026. These are hypotheses to validate with users, not findings from a user study.

The accompanying patch implements the reliability and reporting work marked **Now** below. The source-sentence, freshness, privacy and feedback features remain proposed follow-up work.

## The job to make easier

A person receives a worrying forward, wants to understand whether to trust it, and needs a clear, courteous reply they can send to their family. The useful journey is: paste or review screenshot text → check → understand the evidence and uncertainty → choose whether to share.

Text input, editable OCR, speech, multilingual output, read-aloud, PWA history, Telegram, link checking and share cards already exist. Adding those again would not address the largest gaps.

| Priority | Improvement | User benefit | Acceptance test |
|---|---|---|---|
| Now | Correct source trust, second opinions and public metrics | Fewer unjustified confident answers and clearer product claims | Deterministic safety regressions pass; incomplete benchmarks display as pending everywhere |
| Next | Show the exact validated source sentence beside the claim | A person can understand and independently inspect the reason | Every excerpt has an inspected source/span; no excerpt when unavailable; long text remains readable on mobile |
| Next | Distinguish published date, checked date and present applicability | Old scheme notices and deadlines are less likely to mislead | Historical, missing-year and shifted-jurisdiction fixtures safely abstain or ask for needed context |
| Next | Private checking with a deliberate share/publication choice | People can check sensitive messages without accidentally publishing them | An unshared check is absent from public ledger/feed/report surfaces; retention and deletion behavior are tested |
| Next | Optional structured feedback after the result | Learn whether explanations help people | Consent is optional; test/pilot/organic responses are separate; duplicate submissions are bounded; report every denominator |
| Next | Native-speaker review in the pilot's main languages | Uncertainty and corrections sound natural and remain accurate | Review the core verdict/reason/share wording and messy real-world examples with consent |
| Later | Source-backed amount/date/authority comparison | Makes a changed detail easier to spot | Show only explicit source-supported differences; conflicting, stale or noisy evidence gives comparison unavailable |

The next feature to build is the **source sentence**, because it is useful alone and enables a defensible comparison feature later. Keep the explanation short, show the source link, and distinguish an existing publisher's verdict from Sach's own live check. Do not generate a plausible replacement amount or date when the source does not establish one.

## Reduce distraction

Keep one primary check action. Place the link checker, impact page, donations and developer details below the main journey. Preserve useful existing capabilities while measuring whether people can finish the basic task.

Defer more providers, new bot channels, native-app rewrites, extra payment flows, accounts, phone-number collection, leaderboards and viral rewards. They add maintenance or privacy costs without evidence that they solve the next user problem. Deepfake detection and broad medical/legal advice would require a different evidence and validation strategy.

## Validate the priorities

After privacy safeguards are ready, run a small consented pilot in the languages participants actually use. Observe whether they can paste a forward, correct OCR, distinguish FALSE from UNVERIFIED, open the source and choose a suitable reply. Record recruitment and completion counts, friction, language and exact feedback wording. Ask separately whether they understood, changed belief and shared a correction; these are self-reports, not verified downstream impact.

Success is improved task completion and understanding with no increase in overclaims. Extra feature count, page views and synthetic checks do not establish that.
