# Blockers that need the owner, and the credentials picture (names only; no secrets are written here)

Checked 13 Nov 2026 by listing variable NAMES in the local `.env` and the Vercel production environment.

## Application credentials: present
| Purpose | Variable (name only) | State |
|---|---|---|
| AI judge (paid by Google Cloud trial credit via Vertex) | `GOOGLE_SA_JSON` (Vercel only) | present; works (tested live 13 Nov). Not in local `.env`: local evaluation needs a key file (see below). |
| AI judge (free tier) | `GROQ_API_KEY` | present; works but rate-limited at times |
| AI judge (free tier) | `GEMINI_API_KEY`, `GEMINI_API_KEY_2` | present; free quota was exhausted (HTTP 429) during testing |
| AI judge (free tier) | `OPENROUTER_API_KEY` | present; rate-limited (429) |
| Web search | `TAVILY_API_KEY` | present; plan credits roughly 891 of 1,500 used on 13 Nov |
| Web search | `BRAVE_API_KEY` | present; out of credits (HTTP 402) |
| Fact-check lookup / translation | `GOOGLE_FACTCHECK_API_KEY`, `GOOGLE_TRANSLATE_API_KEY` | present |
| Shared store (counters, cache, ledger) | `KV_REST_API_URL`, `KV_REST_API_TOKEN`, `KV_REST_API_READ_ONLY_TOKEN`, `KV_URL`, `REDIS_URL` | present (Vercel) |
| Payments / tips | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `SACH_UPI_ID`, `SACH_UPI_ID_ALT`, `SACH_UPI_NAME` | present (Vercel) |
| Limits / site | `SACH_MAX_LIVE_PER_DAY` (300), `SACH_SITE_URL` | present (Vercel) |

## Application credentials: missing or optional
| Variable | What it enables | Needed for the submission? |
|---|---|---|
| `AI_GATEWAY_API_KEY` | Vercel AI Gateway judge (code written, off until set) | No. Optional extra capacity; create a dedicated key in the Vercel dashboard. |
| `SACH_PILOT_CODES`, `SACH_TEST_TOKEN` | Pilot traffic labelling and test traffic (after the pilot build is verified, merged and deployed) | Only if you run the pilot. Never commit the codes. |
| `SACH_CONTACT_EMAIL` | A contact email for wrong-verdict reports (today the report button opens a GitHub issue) | Recommended. |
| `TELEGRAM_BOT_TOKEN` + webhook secret | The Telegram bot (off until set) | No. |
| `GOOGLE_SAFEBROWSING_API_KEY` | Extra link-checker signal (non-commercial terms) | No. |
| `MISTRAL_API_KEY`, `CLOUDFLARE_*`, `ANTHROPIC_API_KEY` | Extra judges (off) | No. |

## Things only the owner can do
1. **Review and approve a production deploy.** Nothing built on 13-14 Nov is deployed yet except what was already live.
2. **AgentFoundry**: sign up and do a real bounded task in the IDE, or ask the organizers (see agentfoundry-task-brief.md). I will not claim it.
3. **Approve the figures** in docs/problem-evidence.md before any appears in the submission.
4. **Recruit the pilot participants** and run the consent script yourself; the code only counts what people submit.
5. **Native-speaker review** of the Hindi/Telugu (and other) AI-written strings, or keep the "not reviewed" disclosure.
6. **Record the demo** and re-test every input on the day; confirm the deadline's timezone with the organizers.
7. **File the submission issue** yourself (it is a public post under your account).

## Housekeeping after the final evaluation
- Revoke the extra service-account key created for local evaluation (id `41c76facff9dceba4b54478737d6b59fc20c9c26`):
  `gcloud iam service-accounts keys delete 41c76facff9dceba4b54478737d6b59fc20c9c26 --iam-account=sach-vertex@elite-garden-514607-q4.iam.gserviceaccount.com`
  and delete the local file `vertex_eval_sa.json` in the session scratchpad.
- Untracked `package.json`, `package-lock.json`, `node_modules/` appeared after `npx vercel ai-gateway setup`; they are not part of Sach (stdlib Python): add to `.gitignore` or delete before the final clean evaluation run.
- A Google Cloud budget alert of 1,000 INR exists on the billing account (alert only; it does not stop spending).
