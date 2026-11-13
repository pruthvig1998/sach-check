# Code for a Billion: mandatory items and honest status (checked 13-14 Nov 2026)

Sources: codeforindia.org/hackathon; github.com/karlmehta/code-for-a-billion (README, JUDGING.md, the issue form submission.yml);
Internshala listing. Statuses are what the repository and live site show today; "OWNER" = only the owner can do or confirm it.
Nothing here asserts AgentFoundry use that has not happened.

| # | Requirement (as the organizer states it) | Status | Who |
|---|---|---|---|
| 1 | Register with Code for India (codeforindia.org/hackathon/register; "registration is separate") | UNKNOWN: confirm you registered | OWNER |
| 2 | "Sign up at AgentFoundry.me, create a project in the IDE, build there" (the form's required box says "Built using AgentFoundry (AF), the official IDE") | NOT DONE: no AgentFoundry use recorded; see agentfoundry-task-brief.md and agentfoundry-usage-record.md | OWNER |
| 3 | Public GitHub repo with a README that has setup steps | DONE: README "Run it yourself"; re-check on the day | verify |
| 4 | Demo: a 2-3 minute video or a live link judges can open | Live link exists (sachcheck.in). A video file made by Muse is not reviewed by us yet | OWNER reviews |
| 5 | "Deployed on any cloud" | DONE (Vercel). Production runs an earlier commit than local main until you approve a deploy | OWNER approves |
| 6 | Open source under Apache-2.0 or MIT | DONE (MIT, LICENSE). The FAQ also says projects are "released open-source ... to the Code for India GitHub organization": ask the organizers what they need (transfer, fork or mirror) and when | OWNER asks |
| 7 | Submission issue filed before 15 Nov 2026 (timezone not stated) | NOT DONE: use submission-draft-v2.md; file once | OWNER |
| 8 | Form fields: team, members, problem, what you built (incl. how you used AgentFoundry), repo, demo, scale and severity, optional impact data, track, contact email, three confirmations | Draft ready; placeholders only the owner can fill | OWNER |
| 9 | Track: Governance is an option on the form | DONE | - |

## How it is judged (JUDGING.md): four criteria, 25 points each, judges average
1. Size of the problem: how many citizens face it.
2. Severity: human suffering or economic loss.
3. Quality of the solution: design and real effectiveness.
4. Proven impact: "actual deployment data": users reached, outcomes, before and after. Ties break on proven impact first, then size.
The form says the "Scale & severity" box carries 50% of the score and the optional "Deployment & impact data" box 25%.

## What can honestly move each score before the deadline
- Size and severity: sourced figures only (docs/problem-evidence.md, owner approves each). Do not use unsourced "50 crore users".
- Quality: a clean, non-degraded 79-claim evaluation with abstentions, overclaims, failures and latency shown separately; the red team; the
  link checker; honest UNVERIFIED. Do not quote a number from a degraded run.
- Proven impact: only real field data. A pilot with consenting participants (docs/pilot-protocol.md, once merged and approved) reported
  with denominators and selection-bias language. If there is no pilot data, say "none yet": inventing or inflating it is the one thing
  that can sink the whole entry.
- AgentFoundry: the organizer lists a "Best Use of AgentFoundry Agents" sponsor award. Only a real, documented use can qualify.

## Ask the organizers (in the repo's Discussions, under the owner's account)
"Our project existed before the hackathon. We are doing a real, bounded piece of work in the AgentFoundry IDE and will describe exactly
that. Does that satisfy 'built using AgentFoundry'? Also, what does 'released to the Code for India GitHub organization' require?"
Keep their written answer with the submission evidence.
