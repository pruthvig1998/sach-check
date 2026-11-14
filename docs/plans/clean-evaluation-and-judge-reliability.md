# Plan: a clean 79-claim evaluation, and keeping the paid judge reliable

Status: proposed 14 Nov 2026, nothing executed. Owner decisions are marked **[you]**.

## Facts this plan rests on (all measured today)
- Production already judges with Vertex Gemini first (`gemini-3.1-flash-lite`), then Groq, Gemini free keys and OpenRouter as fallbacks. Vertex today: 148 calls of a 4,000 a day cap, 0 failures, all providers ready.
- Production admits at most 300 live checks a day and 6 a minute (`SACH_MAX_LIVE_PER_DAY`, `SACH_MAX_LIVE_PER_MIN`). At about 8 judge calls per claim that stays under the Vertex cap.
- The four saved evaluation runs were all run from a Mac with only free-tier judges, because the extra Vertex key was revoked. The runs scored 16, 29 and 32 out of 79 with 0 overclaims, and the AI judge failed on up to 32 claims.
- A healthy-provider spot check of 5 unseeded English claims: 4 correct, 1 retrieval miss.
- Cost of one full 79-claim run (my estimate from prompt sizes and Google's published Flash-Lite price of $0.25 / $1.50 per 1M tokens): about $0.60 for judging and under $0.50 for search, so **under $1 (about ₹85)**.

## Goal
1. A run that finishes with no judge or search failures, so `docs/evaluation.md` and `data/eval_summary.json` are written as the headline for the first time.
2. A production judge that does not silently fall back to free tiers when credit runs out.

## Part A: the clean evaluation run (about 45 minutes)
Chosen route: **same judge as production, with a short-lived key**.

| Step | Who | What |
|---|---|---|
| A1 | you | Create a new service-account key for the existing `sach-vertex` account into a file outside the repo (command below). |
| A2 | me | Run `scripts/run_eval.py --workers 2` with the key loaded from that file, local cache and store only (no Upstash variables, so production counters and the public ledger are not touched). I never print the key. |
| A3 | me | Read the run's summary. **Clean** means mode is not FALLBACK, 0 judge problems, 0 search failures. |
| A4 | you | Revoke the key and delete the file immediately after the run (commands below), whatever the result. |
| A5 | me | If clean: the script writes the headline files. Run the full test suite, update `docs/evaluation-runs.md`, `README.md` and the submission draft with the real numbers, and commit. |
| A6 | you | Approve the edit to issue #126 (one sentence replacing "no clean run"). I draft it, you say go. Push and deploy are separate approvals. |

If the run is degraded again, I stop after one more attempt, save it to the index as before, and report why. I will not loosen any verdict rule to improve the number.

Alternative if you prefer not to create a key: a paid Gemini API key (billing enabled on an AI Studio project). It works but differs slightly from production (Gemini API instead of Vertex), so I would record that in the run's header.

## Part B: keep production reliable (about 20 minutes, mostly checks)
- **[you] Check the credit.** In Google Cloud Billing, Credits: how much trial credit is left and when it expires. When it ends, Vertex either bills your card or fails, and the site drops to the free providers, which is the failure we saw in evaluation.
- **[you] Confirm the ₹1,000 budget alert** sends email at 50, 90 and 100%.
- **[me] Add a small status line** (strings only on the status page, no verdict logic) showing "paid judge: ready / paused / over cap" so a quiet fall-back is visible. Optional, needs your approval to deploy.
- **Decision when credit ends [you]:** (a) pay at roughly ₹1 to ₹2 a live check and keep the 300 a day cap, about ₹9,000 to ₹18,000 a month at full cap; or (b) lower the cap and let more checks answer from cache and the match layer; or (c) leave it and accept fallbacks. I recommend (b) first, then (a) if people actually use it.

## Risks and how each is handled
| Risk | Handling |
|---|---|
| Key leaks | New key, file outside the repo, never printed, revoked right after. The previous key was handled the same way. |
| Evaluation touches production | Local store and cache only; no Upstash variables set; no calls to sachcheck.in. |
| Spend overrun | Run is capped by `SACH_VERTEX_MAX_PER_DAY`; expected cost under ₹100. |
| Run degraded again | Saved and indexed honestly; at most one retry; headline files stay untouched. |
| A "clean" run still scores low | Reported as is. The 0-overclaim record is the point; the abstention rate is stated. |

## Commands for step A1 and A4 (you run these)
Create the key (replace nothing; the file lives outside the repo):
`gcloud iam service-accounts keys create ~/sach-eval-key.json --iam-account=sach-vertex@elite-garden-514607-q4.iam.gserviceaccount.com`

List keys to find the new key's ID (it is the one created today):
`gcloud iam service-accounts keys list --iam-account=sach-vertex@elite-garden-514607-q4.iam.gserviceaccount.com`

After the run, revoke it and delete the file:
`gcloud iam service-accounts keys delete <KEY_ID> --iam-account=sach-vertex@elite-garden-514607-q4.iam.gserviceaccount.com`
`rm ~/sach-eval-key.json`

## Done when
- The evaluation summary says mode is not FALLBACK with 0 judge and 0 search failures, or one honest extra degraded run is saved with its cause.
- The key is revoked and the file is gone.
- `docs/evaluation-runs.md`, README and the submission text match the record, and the full suite passes.
