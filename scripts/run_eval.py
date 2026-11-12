"""Score Sach over data/eval_set.json and write docs/evaluation.md (failures included).

Usage:
  python scripts/run_eval.py --dry-run            # validate the set, print the plan; no network, no LLM calls
  python scripts/run_eval.py                      # full run (needs LLM keys in .env; spends free-tier quota)
  python scripts/run_eval.py --resume             # continue a run that stopped (e.g. on quota), same commit + same set
  python scripts/run_eval.py --only-lang hi,te    # partial run -> docs/evaluation-partial-run.md only
  python scripts/run_eval.py --limit 5            # partial run

Only a full, non-degraded run may replace docs/evaluation.md and data/eval_summary.json.
See docs/evaluation-method.md."""
import argparse, datetime, hashlib, json, os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SACH_LEDGER", "data/eval_ledger.json")
os.environ["SACH_NO_CACHE"] = "1"    # the evaluation must never read or write the verdict cache (set before importing sach)
from sach.pipeline import check_forward      # noqa: E402
from sach.retrieve import default_retrievers  # noqa: E402
from sach.llm import get_llm                  # noqa: E402

EVAL_SET = ROOT / "data" / "eval_set.json"
SEEDS = (ROOT / "data" / "seed_debunks.json", ROOT / "data" / "pib_index.jsonl")
SUMMARY = ROOT / "data" / "eval_summary.json"
DOCS = ROOT / "docs"
CHECKPOINT = ROOT / "cache" / "eval_progress.json"
LABELS = ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED")
LANGS = ("en", "hi", "te", "hinglish", "tinglish")
FIELDS = ("claim", "label", "source", "lang", "seeded", "verified_on", "note")


# ---------- data ----------
def load_rows(path=None):
    return json.load(open(path or EVAL_SET, encoding="utf-8"))


def validate_rows(rows):
    """Return a list of problems (empty if the set is well formed)."""
    errs, seen = [], set()
    for i, r in enumerate(rows):
        for f in FIELDS:
            if f not in r:
                errs.append(f"row {i}: missing {f}")
        if r.get("label") not in LABELS:
            errs.append(f"row {i}: bad label {r.get('label')!r}")
        if r.get("lang") not in LANGS:
            errs.append(f"row {i}: bad lang {r.get('lang')!r}")
        if not isinstance(r.get("seeded"), bool):
            errs.append(f"row {i}: seeded must be true/false")
        key = " ".join(str(r.get("claim", "")).lower().split())
        if key in seen:
            errs.append(f"row {i}: duplicate claim")
        seen.add(key)
    return errs


def eval_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def lang_counts(rows):
    out = {}
    for r in rows:
        out[r["lang"]] = out.get(r["lang"], 0) + 1
    return out


def git_info():
    """(commit hash or 'unknown', dirty flag). Dirty = uncommitted changes to tracked or untracked files."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip() or "unknown"
        st = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip()
        return commit, bool(st)
    except Exception:
        return "unknown", True


# ---------- scoring ----------
def outcome(r):
    """correct | abstained | overclaim_false | overclaim_true | wrong_other"""
    got, label = r["got"], r["label"]
    if got == label:
        return "correct"
    if got == "UNVERIFIED":
        return "abstained"
    if got == "FALSE":
        return "overclaim_false"
    if got == "TRUE":
        return "overclaim_true"
    return "wrong_other"       # e.g. MISLEADING where the label was TRUE/FALSE/UNVERIFIED


def by_lang(res):
    """{lang: {n, correct, abstained, overclaimed_false, overclaimed_true, wrong_other}}; only languages present."""
    out = {}
    for r in res:
        d = out.setdefault(r["lang"], {"n": 0, "correct": 0, "abstained": 0, "overclaimed_false": 0, "overclaimed_true": 0, "wrong_other": 0})
        d["n"] += 1
        o = outcome(r)
        d[{"correct": "correct", "abstained": "abstained", "overclaim_false": "overclaimed_false",
           "overclaim_true": "overclaimed_true", "wrong_other": "wrong_other"}[o]] += 1
    return out


def summarize(res):
    o = [outcome(r) for r in res]
    return {"n": len(res), "correct": o.count("correct"), "overclaimed_false": o.count("overclaim_false"),
            "overclaimed_true": o.count("overclaim_true"), "abstained": o.count("abstained"),
            "abstained_wrong": sum(x in ("overclaim_false", "overclaim_true", "wrong_other") for x in o)}   # name kept for the website: wrong TRUE/FALSE verdicts


# ---------- checkpoint ----------
def load_checkpoint(key):
    """Finished results for this (commit, eval-set hash, dirty) key, or a fresh state."""
    fresh = {"key": key, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    try:
        c = json.load(open(CHECKPOINT, encoding="utf-8"))
        if c.get("key") == key:
            return c
    except Exception:
        pass
    return fresh


def save_checkpoint(c):
    os.makedirs(CHECKPOINT.parent, exist_ok=True)
    tmp = str(CHECKPOINT) + ".tmp"
    json.dump(c, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, CHECKPOINT)


# ---------- running ----------
def run(rows, ret, llm, ckpt, log=False, out=print):
    """Check every row not already in the checkpoint; update + persist the checkpoint after each claim."""
    ckpt["no_llm"] = bool(ckpt.get("no_llm")) or llm is None
    base = ckpt.get("llm_failures", 0)
    start_fail = getattr(llm, "failures", 0)
    for i, r in enumerate(rows, 1):
        if r["claim"] in ckpt["results"]:
            out(f"[{i}/{len(rows)}] {r['label']:10} -> (resumed) {ckpt['results'][r['claim']]['got']}")
            continue
        res = check_forward(r["claim"], ret, llm, log=log)
        ckpt["results"][r["claim"]] = {"got": res["verdict"], "reasons": [v["reason_code"] for v in res["claims"]],
                                       "cites": [c["url"] for v in res["claims"] for c in v["citations"]]}
        ckpt["llm_failures"] = base + max(0, getattr(llm, "failures", 0) - start_fail)
        if res.get("search_status") in ("down", "partial"):
            ckpt["search_failures"] = ckpt.get("search_failures", 0) + 1       # web search lost for this claim: not a full run
        save_checkpoint(ckpt)
        out(f"[{i}/{len(rows)}] {r['label']:10} -> {ckpt['results'][r['claim']]['got']}")
    return [{**r, **ckpt["results"][r["claim"]]} for r in rows if r["claim"] in ckpt["results"]]


# ---------- report ----------
def _esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def history_files(docs=None):
    h = (docs or DOCS) / "evaluation-history"
    return sorted(p.name for p in h.glob("evaluation-*-superseded.md")) if h.is_dir() else []


def build_report(res, meta, degraded, partial, failed, docs=None):
    s = summarize(res); n = s["n"]
    bl = by_lang(res)
    title = "# Evaluation" + (" (partial run)" if partial else "") + (" (fallback mode)" if degraded else "")
    L = [title, ""]
    if partial:
        L += [f"> **This was a partial run ({partial}); it is not a measurement of the full set.** It is saved to `docs/evaluation-partial-run.md` and does not replace `docs/evaluation.md` or `data/eval_summary.json`.", ""]
    if degraded:
        L += ["> **This run was degraded; it does not measure the full system.** It is saved separately and does not replace `docs/evaluation.md`.", ""]
    L += [f"Measured on commit `{meta['commit']}`" + (" (working tree had uncommitted changes)" if meta["dirty"] else " (clean tree)") + f", {meta['date']} (UTC).", "",
          f"Mode: {meta['mode']}; retrieval: {', '.join(meta['retrievers'])}; judges: {', '.join(meta['judges']) or 'none'}.", "",
          f"- Claims: **{n}** (see limitations)", f"- Exact-match accuracy: **{s['correct']}/{n}**",
          f"- **Overclaimed FALSE (the unforgivable failure): {s['overclaimed_false']}**",
          f"- **Overclaimed TRUE (also an overclaim): {s['overclaimed_true']}**",
          f"- Wrong verdicts other than overclaims (e.g. MISLEADING where a TRUE/FALSE label stands): {s['abstained_wrong'] - s['overclaimed_false'] - s['overclaimed_true']}"]
    for l in ("FALSE", "TRUE", "UNVERIFIED"):
        g = [r for r in res if r["label"] == l]
        L.append(f"- Label {l}: {sum(r['got'] == l for r in g)}/{len(g)} correct; {sum(r['got'] == 'UNVERIFIED' for r in g)} abstained as UNVERIFIED")
    for tag, flag in (("Seeded (the source's PRID is in data/seed_debunks.json or data/pib_index.jsonl; retrieval is partly circular)", True),
                      ("Unseeded (retrieval had to find the page itself)", False)):
        g = [r for r in res if r["seeded"] == flag and r["label"] != "UNVERIFIED"]
        if g:
            L.append(f"- {tag}: {sum(r['got'] == r['label'] for r in g)}/{len(g)} correct")
    L += ["", "## By language", "", "| Language | n | Exact match | Abstained | Overclaimed FALSE | Overclaimed TRUE |", "|---|---|---|---|---|---|"]
    for lg in [x for x in LANGS if x in bl] + [x for x in bl if x not in LANGS]:
        d = bl[lg]
        L.append(f"| {lg} | {d['n']} | {d['correct']} | {d['abstained']} | {d['overclaimed_false']} | {d['overclaimed_true']} |")
    L += ["", "Abstained = Sach said UNVERIFIED where the label was not UNVERIFIED (safe but a miss).", "",
          "## Every claim", "", "| Claim | Lang | Label | Sach | Result |", "|---|---|---|---|---|"]
    for r in res:
        o = outcome(r)
        tag = {"correct": "ok", "abstained": "miss (abstained)", "overclaim_false": "OVERCLAIM (FALSE)",
               "overclaim_true": "OVERCLAIM (TRUE)", "wrong_other": "WRONG"}[o]
        L.append(f"| {_esc(r['claim'])} | {r['lang']} | {r['label']} | {r['got']} | {tag} |")
    L += ["", "## Limitations (read before citing these numbers)",
          f"- The set is small ({n} claims here). Every non-control row was checked by fetching the cited official page and reading it; rows are not bulk-scraped. PIB has no listing page for debunks and its RSS feed returns only the latest 20 items, so a real 100+ set needs more manual work or a crawl. Rows added in the v2 revision carry the fetch date in `verified_on`; the original 31 rows were verified in the original build and were not re-fetched.",
          "- The Hindi, Telugu, Hinglish and Tinglish rows were written by an AI model and have not been reviewed by a native speaker. Real forwards are messier. Treat per-language numbers as a smoke test, not a measurement of how Sach does on real forwards in that language.",
          "- Per-language groups are tiny (a handful of rows each), so one claim moves a percentage a lot.",
          "- Rows marked `seeded` have their PIB page in the hand-seeded list or the harvested index, so retrieval for them is partly circular and their accuracy is optimistic. Many FALSE claims paraphrase PIB debunk titles for the same reason.",
          "- Relabel disclosure: the first control (\"free laptops to all students\") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.",
          "- Relabel disclosure 2: the RPF 4,208 Constable / 452 SI claim was first labelled FALSE (from PIB debunk 2009349), but that debunk was about a fake notice on one website; a genuine PIB release (PRID 2246142) lists those same vacancy numbers. Sach said TRUE; relabelled TRUE after inspecting the evidence. Two labels were changed after seeing results, so treat headline accuracy as indicative only.",
          "- Retrieval varies run to run (live search results change), so single-run numbers move by a claim or two. The evaluation runs with the verdict cache switched off (`SACH_NO_CACHE=1`).",
          "- Official-domain rule is *.gov.in / *.nic.in / who.int (plus a few listed hosts), so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.",
          "- There are no true MISLEADING rows: PIB items tagged \"misleading\" are labelled FALSE, so a MISLEADING verdict on them counts as a wrong verdict here."]
    if failed:
        L.append(f"- The LLM failed on {failed} source judgements during this run (quota/outage); those fell back to the safe PIB-debunk-only check.")
    hist = history_files(docs)
    L += ["", "## Previous runs", ""]
    L += [f"- [{h}](evaluation-history/{h})" for h in hist] or ["- None archived yet."]
    return "\n".join(L) + "\n"


def archive_previous(commit, docs=None):
    """Move the current docs/evaluation.md into docs/evaluation-history/ with a superseded banner. Returns the new path or None."""
    docs = docs or DOCS
    cur = docs / "evaluation.md"
    if not cur.exists():
        return None
    text = cur.read_text(encoding="utf-8")
    m = re.search(r"Measured on commit `[^`]*`[^\n]*?(\d{4}-\d{2}-\d{2})", text)
    tag = m.group(1) if m else "v1"
    hist = docs / "evaluation-history"
    hist.mkdir(parents=True, exist_ok=True)
    dest, k = hist / f"evaluation-{tag}-superseded.md", 2
    while dest.exists():
        dest = hist / f"evaluation-{tag}-{k}-superseded.md"; k += 1
    banner = f"> **Superseded** by the run measured on commit `{commit}`. Kept for the record; the current report is `docs/evaluation.md`.\n\n"
    dest.write_text(banner + text, encoding="utf-8")
    cur.unlink()
    return dest


# ---------- main ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--resume", action="store_true", help="skip claims already checkpointed for the same commit and eval-set hash")
    ap.add_argument("--only-lang", default="", help="comma list, e.g. hi,te (partial run)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N rows (partial run)")
    ap.add_argument("--dry-run", action="store_true", help="validate and print the plan; no network calls")
    a = ap.parse_args(argv)
    rows = load_rows()
    errs = validate_rows(rows)
    if errs:
        print("eval set is invalid:\n  " + "\n  ".join(errs)); return 2
    langs = [x.strip() for x in a.only_lang.split(",") if x.strip()]
    bad = [x for x in langs if x not in LANGS]
    if bad:
        print(f"unknown language(s): {bad}; choose from {LANGS}"); return 2
    sel = [r for r in rows if not langs or r["lang"] in langs]
    if a.limit:
        sel = sel[:a.limit]
    partial = ", ".join(([f"languages {','.join(langs)}"] if langs else []) + ([f"first {a.limit} rows"] if a.limit else []))
    commit, dirty = git_info()
    if a.dry_run:
        lab = {}
        for r in sel:
            lab[r["label"]] = lab.get(r["label"], 0) + 1
        print(f"DRY RUN: no network or LLM calls. Eval set {len(rows)} rows (hash {eval_hash(rows)}); would check {len(sel)}.")
        print("by language:", dict(sorted(lang_counts(sel).items())))
        print("by label:   ", dict(sorted(lab.items())))
        print(f"commit {commit}{' (dirty)' if dirty else ''}; output: {'docs/evaluation-partial-run.md (partial: ' + partial + ')' if partial else 'docs/evaluation.md + data/eval_summary.json if the LLM-backed run is clean, else docs/evaluation-fallback-run.md'}")
        print(f"resume checkpoint: {CHECKPOINT} ({'will be used' if a.resume else 'ignored; a fresh run overwrites it'})")
        return 0
    ret, llm = default_retrievers(), get_llm()
    key = {"commit": commit, "eval_hash": eval_hash(rows), "dirty": dirty}
    ckpt = load_checkpoint(key) if a.resume else {"key": key, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    judges = [f"{n} ({s})" for n, s in llm.describe()] if llm is not None and hasattr(llm, "describe") else ([] if llm is None else [type(llm).__name__])
    res = run(sel, ret, llm, ckpt, log=bool(os.environ.get("SACH_SEED_LEDGER")))
    failed = ckpt["llm_failures"]
    sfailed = ckpt.get("search_failures", 0)
    degraded = ckpt["no_llm"] or failed > 0 or sfailed > 0
    if ckpt["no_llm"]:
        mode = "FALLBACK (no LLM key): clear PIB debunks only, never TRUE or MISLEADING"
    elif failed:
        mode = f"FALLBACK: the LLM failed on {failed} source judgements (quota/outage), so those sources fell back to the safe PIB-debunk-only check"
    else:
        mode = "LLM stance (with second-opinion consensus where more than one judge is configured)"
    if sfailed:
        mode = (mode if (ckpt["no_llm"] or failed) else "FALLBACK") + f"; web search failed for {sfailed} claims (out of credits or outage), so those claims only had the built-in PIB list"
    meta = {"commit": commit, "dirty": dirty, "date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(), "mode": mode,
            "retrievers": [type(x).__name__ for x in ret], "judges": judges}
    report = build_report(res, meta, degraded, partial, failed)
    if partial:
        target = DOCS / "evaluation-partial-run.md"
    elif degraded:
        target = DOCS / "evaluation-fallback-run.md"
    else:
        archive_previous(commit)
        report = build_report(res, meta, degraded, partial, failed)    # rebuilt so "Previous runs" lists the file just archived
        target = DOCS / "evaluation.md"
        json.dump({**summarize(res), "commit": commit, "dirty": dirty, "date": meta["date"], "by_lang": by_lang(res),
                   "eval_set_hash": key["eval_hash"], "retrievers": meta["retrievers"], "judges": judges},
                  open(SUMMARY, "w", encoding="utf-8"))   # read by the website
    target.write_text(report, encoding="utf-8")
    print("\n".join(report.split("\n")[:14]))
    print(f"\nwrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}"
          + ("  (headline files NOT touched)" if partial or degraded else ""))
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
