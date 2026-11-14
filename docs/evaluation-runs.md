# Evaluation run index (79-claim set, final code)

Every complete run of `scripts/run_eval.py` on the final code (`e81b1cc`, and the strings-only commits after it) was degraded (a search or AI-judge failure on at least one claim), so none is a
headline result and `docs/evaluation.md` was not overwritten. Degraded runs are written to `docs/evaluation-fallback-run.md`, which each new run
replaces, so the only durable record of a run is the git commit that contains that file. To read one: `git show <commit>:docs/evaluation-fallback-run.md`.

| Exact match | Failures in that run | Saved artifact |
|---|---|---|
| 32/79 | web search failed for 3 claims | `git show 6e7efe6:docs/evaluation-fallback-run.md` |
| 29/79 | an AI judge timed out on 1 claim | `git show f482804:docs/evaluation-fallback-run.md` (the version in the repository today) |
| 16/79 | AI judge failed or timed out on 32 claims, 45 source judgements fell back, search failed on 4 claims | `git show 4fcb301:docs/evaluation-fallback-run.md`. Run on 14 Nov 2026 on commit `c9aebe3` from a machine without the Vertex judge (its extra key had been revoked), after hours of free-tier use. Lowest score because most claims never got a working judge. |
| 21/79 | AI judge failures on 10 claims, search failures on 6 claims | **None.** The results file for this run was overwritten by the next run before it was committed. Quote the figure only as an unsaved earlier run, or not at all. |

All four runs: 0 overclaimed FALSE and 0 overclaimed TRUE. Abstention (UNVERIFIED on a claim labelled TRUE or FALSE) was about 63% in the 32/79 run.
Earlier runs on older code (`docs/evaluation.md` and commits `34b2e4e` 33/79, `cd63650` 25/79) are not comparable to the final code.
