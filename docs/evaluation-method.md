# How the evaluation set is built and run

## Choosing and verifying rows
Each row in `data/eval_set.json` is one claim, written the way it might appear in a forward, with a label and the official page that backs the label. A row is only added after someone fetched that page and read it, and the page has to say what the label needs: the amounts, dates and names in the claim must match the page. Every row records `verified_on` (the date it was fetched) and a one-line `note` naming the sentence that supports it. Rows from the first build (31) were verified then and have `verified_on: null` plus a note saying they were not re-fetched.

Claims whose truth changes quickly ("the last date is tomorrow") are avoided. Facts fixed by a dated press release are preferred.

## What the labels mean
- **FALSE**: PIB Fact Check or an official ministry/department page says the viral claim is fake, false or misleading. (PIB items tagged "misleading" are labelled FALSE, so Sach saying MISLEADING on them counts as a wrong verdict.)
- **TRUE**: an official page confirms the specific fact as stated.
- **UNVERIFIED**: an invented control. It sounds plausible, no official source addresses it, and it is written not to resemble a real scheme. Sach should say UNVERIFIED.

An overclaim is a TRUE or FALSE verdict where the label says something else. Overclaimed FALSE is the failure we care about most; overclaimed TRUE is counted separately and is also a failure. Saying UNVERIFIED when the label is TRUE or FALSE is a safe miss ("abstained").

## What "seeded" means
`seeded: true` means the source page's PRID is already in `data/seed_debunks.json` or `data/pib_index.jsonl`, so retrieval can find it from our own index. Those rows are partly circular and flatter the result. New source pages are never added to those two files. The report scores seeded and unseeded rows separately.

## Languages
`lang` is `en`, `hi`, `te`, `hinglish` or `tinglish`. The Hindi, Telugu, Hinglish and Tinglish claims were written by an AI model and have not been reviewed by a native speaker; each such note says so. `sach.lang.detect_language` returns `hi` and `te` for those rows, `tl` for Tinglish, and `hi` for Hinglish.

## How to run
```
python scripts/run_eval.py --dry-run      # validates the set, prints counts by language and label, no network calls
python scripts/run_eval.py                # full run; spends LLM quota, needs keys in .env
python scripts/run_eval.py --resume       # continue after a stop (quota); same commit, same set, same dirty state
python scripts/run_eval.py --only-lang hi,te   # partial run, written to docs/evaluation-partial-run.md
python scripts/run_eval.py --limit 5           # partial run
```
The run sets `SACH_NO_CACHE=1`, so the verdict cache is never read or written. Progress is checkpointed after each claim in `cache/eval_progress.json`; without `--resume` a run starts fresh. The report header names the commit measured (and whether the tree was dirty), the UTC date, the retrievers and the judges.

## Degraded and partial runs
A run is **degraded** if no LLM was available or the LLM failed on any source judgement (quota, outage). The failure count is stored in the checkpoint, so a resumed run that mixes healthy and failed claims is still degraded. A degraded run is written to `docs/evaluation-fallback-run.md`. A **partial** run (`--only-lang`, `--limit`) goes to `docs/evaluation-partial-run.md`. Neither can overwrite `docs/evaluation.md` or `data/eval_summary.json` (the numbers the website shows).

Only a full, non-degraded run replaces `docs/evaluation.md`. The old report is first moved to `docs/evaluation-history/` with a "superseded" banner, and the new report links to it under "Previous runs".

## Known weaknesses
- About 50 rows. Per-language groups have 2 to 6 rows each, so one claim swings a percentage a lot.
- The non-English rows are AI-written, so they are cleaner than real forwards. Real forwards have typos, mixed scripts, emoji and long chains.
- Seeded rows are partly circular; many FALSE claims paraphrase PIB debunk titles.
- Live search results vary between runs, so numbers move by a claim or two.
- Two labels in the original set were changed after seeing results (disclosed in the report).
- Several older FALSE sources are from 2015 to 2020. They are fixed historical debunks, but they are not a sample of what is circulating today.
- No true MISLEADING rows exist yet.
