# Evidence and release notes — 13 November 2026

This review starts from commit `bc5e30c39138b5b4918f54ad16a36166f8074e7d`. The attached hackathon brief supplied project context; actual repository code and executed checks determine the claims below. The changes were bounded safety, evaluation and presentation work, each checked by running the commands recorded below.

## Evidence register

| Category | Result | Source and limits |
|---|---|---|
| Verified baseline | 4,462 deterministic tests passed on Python 3.13.1; pytest reported 179.80 seconds, command elapsed 180.82 seconds. | `.venv/bin/python -m pytest -q` on the unchanged baseline. This measures software regressions, not fact-check accuracy. |
| Baseline environment failure | Default Python 3.9 failed collection in `tests/test_sach.py` and `tests/test_search.py` with `KeyError: 'file'`. | Initial run exited 2 after 7.86 seconds. Use Python 3.13 for the recorded passing run. |
| Verified repository visibility | Repository is public. | [GitHub repository](https://github.com/pruthvig1998/sach-check), metadata read 13 November 2026. |
| Verified demo reachability | Both published hosts returned HTTP 200. | Read-only requests to [sachcheck.in](https://sachcheck.in) and [the Vercel host](https://sach-check-lilac.vercel.app). Reachability does not establish end-to-end checking quality. |
| Historical benchmark | Checked-in legacy summary records 26/31; it does not establish current accuracy. | `data/eval_summary.json` and `docs/evaluation.md`; missing current provenance, measured before later safety changes. Do not present it as a new result. |
| Current live benchmark | Incomplete: no configured AI-judge or web-search credentials were available in this checkout/session. | Checked presence of provider variable names only; no secrets inspected or printed. The application's provider keys (AI judge and web search) are configured separately from any developer-tool accounts. External facts in this file (repository visibility, HTTP status of hosts, the organizer issue search) were checked by hand on 13 Nov 2026 and must be re-checked before filing. |
| Pilot self-reports | None collected or verified in this work. | No recruited participants, responses, testimonials or outcomes are invented. |
| Usage impact | Existing counters count checks, including repeats, and do not distinguish all test traffic. | `sach/ledger.py`, `sach/impact.py`. Checks and ledger rows are not unique people, consented respondents or demonstrated benefits. |
| Eligibility evidence missing | No AgentFoundry usage proof located in inspected files or repository history. | Absence from this checkout is not proof it was never used; owner must supply authentic artifacts. |
| Submission evidence missing | Organizer issue search for Sach returned no results. | [Organizer issues](https://github.com/karlmehta/code-for-a-billion/issues), query `repo:karlmehta/code-for-a-billion is:issue sach`, 13 November 2026. A submission under another name may exist. |

The [published judging rubric](https://github.com/karlmehta/code-for-a-billion/blob/main/JUDGING.md) gives equal weight to problem size, severity, solution quality and proven impact. It separately requires AgentFoundry usage, a public repository, an accessible demo and a submission issue. This patch supplies neither missing historical proof nor a real-user study.

## Scope and remaining limitations

The change focuses on source trust after redirects, cited verdict prerequisites, independent second opinions, provider-name privacy, safer reuse of cached results, reproducible evaluation artifacts and consistent public reporting. See the final validation record below for checks actually executed.

| Code paths | Change |
|---|---|
| `sach/fetch.py`, `sach/pib.py`, `sach/retrieve.py`, `sach/verdict.py` | Record and check the actual destination, reject unusable citations, refetch old cache records without destination provenance, and write source cache entries atomically. |
| `sach/llm.py`, `sach/status.py` | Require a different second model or existing deterministic corroboration; remove Gemini API-key suffixes from provider names. |
| `sach/cache.py` | Mark current live verdict policy and recheck old live/mixed cached results without changing share IDs. |
| `sach/site.py`, `sach/impact.py` | Share benchmark eligibility validation, preserve missing data as unavailable and correct usage/limited-mode wording. |
| `scripts/run_eval.py`, `.github/workflows/evaluation.yml` | Export versioned results, preserve failures, count overclaims even during degradation, bind resume to actual code/configuration, and run separate offline fixtures in CI. |
| `tests/test_evidence_safety.py`, evaluation/impact tests and existing source/provider fixture tests | Add focused regression coverage and update fixtures for final-URL provenance and independent confirmation. |

The full prioritized product assessment is in [docs/product-priorities.md](docs/product-priorities.md); a truthful demo path is in [docs/demo-script.md](docs/demo-script.md).

Preserving a source's validated sentence, temporal applicability, private checking with explicit publication consent, optional outcome feedback and native-speaker review are the next product priorities. A complete claim-mutation feature is deferred until the source-span contract is preserved end to end. Existing public ledger and shared-report privacy behavior requires a coordinated follow-up; do not collect private forwards for a pilot on the assumption that this patch makes them private.

Historical shared reports remain historical records. Cache safety changes protect fresh live checks without changing share identifiers; they do not retract existing screenshots, published ledger rows or old shared reports. Legacy MATCH-only cache entries retain their publisher attribution. A successful fetch time also does not prove a scheme or deadline is currently applicable. Local archive matches need a future schema change to distinguish match time from an actual page retrieval.

## Reproduction and rollback

Use Python 3.13, install `requirements-dev.txt`, then run the commands recorded in the final validation section. No database migration or new third-party service is required. Local changes do not deploy the application.

Roll back by reverting this feature branch's changes and redeploying the prior approved revision through the owner's normal process. Restoring older safety code can restore the risks documented here; retain evaluation artifacts for audit. No production data was changed by this work.

## Owner follow-up

- Supply authentic AgentFoundry evidence and the actual organizer submission URL.
- Configure application provider credentials and run a clean, complete live benchmark; keep failures and fallback artifacts.
- Address private checking/publication consent before recruiting people with personal forwards; define retention and deletion.
- Recruit and document a real pilot, including languages, dates, completion counts, exact questions and selection bias. Report self-reports separately from accuracy and downstream behavior.
- Review the code and approve production release through the normal deployment process.

## Final validation

| Executed check | Result |
|---|---|
| `python -m pytest -q --junitxml=validation-junit.xml` | **4,502 passed**, no failures or skips, Python 3.13.1. Pytest reported 230.53 seconds; elapsed process time 231.19 seconds. Completed 13 November 2026 at 22:05 IST. |
| `.venv/bin/python -m pytest -q -p no:cacheprovider` on commit `e81b1cc` | **5,125 passed**, no failures, Python 3.13.1, pytest reported 236.68 seconds. Run on 14 November 2026; this supersedes the 4,502 figure above, which was taken earlier on 13 November before later changes added tests. |
| `python scripts/run_eval.py --offline` | **3/3 synthetic fixtures passed**, complete and non-degraded; [machine-readable artifact](evidence/offline-evaluation-2026-11-13.json). This is a deterministic regression check, not live accuracy. |
| `python scripts/run_eval.py --dry-run` | **79 rows validated**: 34 FALSE, 34 TRUE and 11 invented UNVERIFIED controls. No live evaluation calls. |
| `git diff --exit-code -- docs/evaluation.md data/eval_summary.json` after the offline run | Passed: published historical benchmark files were untouched. |
| `git diff --check` | Passed. |
| Full live benchmark / hosted GitHub Actions | Not executed. Provider credentials were absent; the workflow is supplied for a future GitHub run. |

Targeted safety validation also passed 3,623 tests in 88.39 seconds, including 32 new regressions. The final evaluation-focused run passed 175 tests in 5.63 seconds. These counts overlap the full suite and must not be added to it. The full suite has 40 more cases than the unchanged baseline, all passing; test-suite success is not benchmark accuracy.

macOS marked workspace dependency and source files as cloud-only during the work, so combined validation used an isolated local checkout containing the proposed changes with the same Python 3.13 dependency environment. No lint or type-check configuration was present in the baseline repository. The fixture artifact records the tested source-content hash and configuration, with a dirty baseline commit because the changes were validated before local commits.
