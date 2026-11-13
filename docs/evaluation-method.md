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

## The 13 added Indian languages
`bn` Bengali, `as` Assamese, `mni` Manipuri (Meitei Mayek script), `mr` Marathi, `kok` Konkani, `ne` Nepali, `ta` Tamil, `gu` Gujarati, `pa` Punjabi (Gurmukhi), `or` Odia, `kn` Kannada, `ml` Malayalam and `ur` Urdu (right-to-left) each have two rows: one FALSE (a PIB or RBI debunk) and one TRUE (an official announcement). Three more rows (`mr`, `ta`, `ur`) are invented UNVERIFIED controls. These 29 rows take the set from 50 to 79.

No new fact was researched. Each translated row is the same claim as an already-verified Hindi, Telugu, Hinglish, Tinglish or English row, written as a casual forward in the new language. `translated_from` holds the original claim, and `label`, `source`, `seeded` and `verified_on` are copied from it, so the official page behind each row was fetched and read once, in the original. A test checks that every number in a translation (native digits converted) equals the numbers of its original. Different facts are used across languages where possible; sixteen facts (eight FALSE, eight TRUE) cover the 26 translated rows, so most facts appear twice.

All of these rows were written by an AI model and have not been reviewed by a native speaker. Manipuri in Meitei Mayek is the weakest and most in need of review. With two rows per language, a language's score is a smoke test, not a measurement. The red-team file has matching cases for several of these scripts (embedded instructions in English and in the language, fabricated PIB lines, altered numbers, rumour-reporting bait, Urdu bidi tricks).

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

## What each measure means
The report ("Measures, separately") and `data/eval_summary.json` (`measures`) give each number its own denominator. None is a score for another.

- **Accuracy (exact match)**: claims where Sach's verdict equals the label, over all claims (n). Abstentions and ERRORs count as misses.
- **Abstention rate**: UNVERIFIED answers on claims whose label is TRUE or FALSE, over those decisive-label claims only. The UNVERIFIED control rows are excluded, since abstaining is correct there.
- **Site card "abstained"** (`abstained` in `data/eval_summary.json`, the number shown on the home page): every UNVERIFIED answer where the label is not UNVERIFIED, whatever the label. It is a different count from the abstention rate above, which counts only TRUE/FALSE-labelled claims. The UNVERIFIED-labelled controls are correct when Sach says UNVERIFIED, so they are in neither count. The report's line for them reads "Label UNVERIFIED (controls): X/N answered UNVERIFIED as expected" and does not call them correct or abstained. The two agree today only because the set has no MISLEADING rows.
- **Overclaim FALSE** and **Overclaim TRUE**: FALSE or TRUE verdicts where the label says something else, each counted over all claims (n).
- **Wrong, not an overclaim**: any other wrong verdict (e.g. MISLEADING where the label is TRUE, FALSE or UNVERIFIED), over n. ERRORs are excluded here.
- **Failures**: claims with a judge problem (`degraded`: a judge timed out or failed), a search failure (web search down or partial), or an ERROR (the check raised an exception; the run continues and the claim is recorded as ERROR). Each kind is counted and listed by claim, and a run with any of them is written as a fallback run. The count of source judgements the LLM failed on is reported beside them.
- **Latency**: wall time per claim in seconds (p50, p90, p95, max, mean), using nearest-rank percentiles, over all claims with timing and per layer (`match`, `live`). The layers `mixed` (a match plus a live check) and `error` (the check raised an exception) also appear when they occur, so the per-layer rows are not only `match` and `live`. Claims from checkpoints written before timing was recorded are counted as untimed, not dropped.
- **Failed, abstained and wrong cases**: every claim whose result is not an exact match, with its label, Sach's answer, layer, reason codes, language and time. The "Why" column gives the reason(s): judge problem, search failure, error, wrong verdict, overclaim or abstained (a claim can have several). For an ERROR claim the "Error" column gives only the exception class name (for example `TimeoutError`).

**Error messages are never committed.** The committed reports (`docs/evaluation*.md`) and `data/eval_summary.json` contain no exception message text, only the class name. The local checkpoint (`cache/eval_progress.json`, git-ignored and never committed) keeps a best-effort-redacted message for debugging. Redaction there is three steps: (1) the value after a key or token name (`key=`, `api_key=`, `token:`, `password=`, `secret=`, `auth=`, `Authorization:`, `x-goog-api-key:` and similar), in plain, quoted, JSON and repr forms (`"password": "..."`, `{'api_key': '...'}`, `token "..."`) and of any length, is replaced; (2) a `Bearer` token is replaced; (3) a 20+ character key-like run (letters, digits, `_ - + / = . %`) is replaced when it has a digit, is 28+ characters long, or mixes upper and lower case with a symbol, and a symbol-bearing upper-only or lower-only 20 to 27 character token written straight after a key name is replaced too. The text is then made UTF-8 safe and cut to 160 characters.

The redaction has real limits, which is why no message reaches a committed file. A short secret with no key name, a token of under 20 characters, a token with no digit and no symbol that is not after a key name, a secret split across lines or encoded, and an unusual format of any kind can all get through the checkpoint. The checkpoint is local and is read only by the person running the evaluation.

## Running with `--workers`
`--workers` checks several claims at once (default 1, sequential). It is faster, and it stays inside the provider limits at 3. The speed-up was observed once: about 4.7 minutes for 79 claims at 5 workers, against an estimated 20+ minutes sequentially. It is not guaranteed, and it depends on provider load.

## Known weaknesses
- About 50 rows. Per-language groups have 2 to 6 rows each, so one claim swings a percentage a lot.
- The non-English rows are AI-written, so they are cleaner than real forwards. Real forwards have typos, mixed scripts, emoji and long chains.
- Seeded rows are partly circular; many FALSE claims paraphrase PIB debunk titles.
- Live search results vary between runs, so numbers move by a claim or two.
- Two labels in the original set were changed after seeing results (disclosed in the report).
- Several older FALSE sources are from 2015 to 2020. They are fixed historical debunks, but they are not a sample of what is circulating today.
- No true MISLEADING rows exist yet.
