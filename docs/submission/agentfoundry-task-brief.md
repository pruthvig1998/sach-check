# AgentFoundry: what the rules say, what we can and cannot claim, and a real bounded task

## What the organizer's own pages say (read 13 Nov 2026)
- Hackathon README (github.com/karlmehta/code-for-a-billion): participation steps are "Build your project in AgentFoundry"
  (the "official IDE"), publish a public repo with a README, record a demo (live URL or video), and file the submission issue.
  The checklist includes **"Built using AgentFoundry"**; the issue form asks "what you built and how you used AgentFoundry"
  and has a REQUIRED checkbox "Built using AgentFoundry (AF), the official IDE".
- JUDGING.md says nothing about proof of AgentFoundry use, about pre-existing work, or about whether starting now counts.
  The organizers point questions to the repository's Discussions.
- codeforindia.org/hackathon: sign up at AgentFoundry.me, create a project in the IDE (1M free tokens). Registration is
  separate (codeforindia.org/hackathon/register).

## What is true today
Sach was built before this hackathon's AgentFoundry requirement was checked, with other tools. The repository has no
AgentFoundry history and nothing in it shows any. **We must not write or imply that earlier work used AgentFoundry.** Whether
starting to use it now satisfies "built using AgentFoundry" is the organizers' decision: ask them in Discussions (below).

## What you (the owner) can honestly do
1. Sign up at AgentFoundry.me and register with Code for India (your own account; I cannot sign in for you).
2. Ask the organizers in the repository's Discussions: "Our project existed before the hackathon; we are now doing a real,
   bounded piece of work in the AgentFoundry IDE and will describe exactly that. Does that satisfy 'built using AgentFoundry'?"
   Keep their answer.
3. In the AgentFoundry IDE open the existing repository folder (their CodeNow guide describes opening a project folder) and
   give its agent the task below. Keep the session evidence: screenshots of the IDE session with the date, the generated diff,
   the commit it produced (branch `agentfoundry/judge-quote`), and the test run.
4. In the submission's "how you used AgentFoundry" field write only what happened, e.g. "On <date> we used the AgentFoundry
   IDE to implement <feature> (commit <hash>, tests <result>). The rest of the project was built before and outside it."
5. Tick the confirmation only if the organizers' answer and your own honest reading allow it. If not, file anyway with the
   unticked box and an honest note, or do not file: the decision and the risk are yours.

## The bounded task to give AgentFoundry's agent (real, useful, low risk)
Task: "Show the sentence the AI judge relied on, under each source in a Sach result."
Context: `sach/llm.py` judges one source page against one claim and returns a stance plus a verbatim quote; `sach/stance.py`
`validate_stance` verifies the quote is on the page and relates to the claim; today the quote is thrown away
(`Evidence` in `sach/models.py` keeps only `stance`). Build:
1. Carry the VALIDATED quote through: the judge returns (stance, quote) only when `validate_stance` accepted the stance
   (keep the old `stance()` API working); store it on `Evidence.quote` for the judge outcome that matches the FINAL stance;
   when several judges answer (consensus), keep a quote from a judge whose stance equals the final stance, else none.
2. Show it: in `site.result_block`, under the citation, "From the source (exact sentence):" in a `<blockquote>`, escaped,
   with the page title; never for stance 'none', never when the check was degraded; include it in the JSON `citations`
   entries; do NOT put it into the public ledger, ClaimReview feed or share record.
3. Do not change `sach/verdict.py` or any verdict rule. Add tests: verdict invariance on the existing scenarios, quote is a
   substring of the page, escaped HTML, absent for 'none' and degraded, and the full suite must keep passing (run `pytest -q` before you start and record the number).
4. Keep the commit small, with the test output pasted in the commit message or PR description.
Why this task: it makes the evidence visible to a judge, it is separable from the verdict logic, and an earlier heuristic
version (choosing a sentence ourselves) was rejected after independent review found it could show misleading sentences.
