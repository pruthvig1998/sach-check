# Measurement: how much of the 79-claim set works with no LLM

Run 14 Nov 2026 on commit `c9aebe3` (code identical to `faf3461`), full 79-claim set (`data/eval_set.json`: 34 FALSE, 34 TRUE, 11 UNVERIFIED controls), `scripts/run_eval.py --workers 3`. Every judge key was blanked, so Sach ran in its documented no-LLM mode: the match layer, plus the safe fallback that may only answer FALSE from a PIB debunk, never TRUE or MISLEADING.

| Configuration | Decisive claims answered correctly (of 68) | FALSE | TRUE | Answered wrongly | Abstained (UNVERIFIED) | Controls right |
|---|---|---|---|---|---|---|
| **B: pure local** (no LLM, no web search, no fact-check or translate API; only cache, local PIB index, stored debunks) | **5 (7%)** | 5 of 34 | 0 of 34 | **0** | 63 | 11 of 11 |
| **A: no LLM, web search and Google Fact Check API on** | **8 (12%)** | 8 of 34 | 0 of 34 | **0** | 60 | 11 of 11 |

Both runs: 0 overclaimed FALSE, 0 overclaimed TRUE. The script's own headline shows "1/79" for both because it never counts a claim that hit a search failure as correct (it marks them degraded); the table above counts the raw answers. Neither run touched the headline files, and the committed `docs/evaluation-fallback-run.md` was restored.

## What it shows
- **Without an LLM, Sach is safe but nearly silent.** It never answered wrongly and got every control right, but it could answer only 5 to 8 of 68 true-or-false claims, all FALSE (a PIB debunk page was found). It cannot answer TRUE at all in this mode, by design.
- **Web search adds a little (5 to 8).** Mostly English; non-English got 0 of 40 with no search and 3 of 40 with it.
- **Correction to what I said earlier:** I described the 16/79 degraded run as a "no-LLM floor of roughly 20%". That was wrong. In that run judges still worked for part of the sources. The measured no-LLM answer rate is **7 to 12%**.
- **For comparison:** with a healthy judge, the earlier live spot check got 4 of 5 unseeded English claims right, and the best saved degraded run answered 32 of 79.

## Caveat
The evaluation set is built mostly from PIB debunks and officially announced items, so it is friendlier to a no-LLM path than real user traffic is. The real-world share answerable without a model is probably no higher than this.
