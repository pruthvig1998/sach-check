"""Run every case in data/red_team.json through the real pipeline and write docs/red-team.md.
Usage: python scripts/red_team.py [--limit N] [--only CATEGORY]
Exit code 1 if any case overclaimed (verdict in the case's must_not). Live: uses default_retrievers() and get_llm()."""
import argparse, datetime, inspect, json, os, pathlib, subprocess, sys
os.environ["SACH_NO_CACHE"] = "1"          # set before importing sach: a cached verdict would hide what the pipeline does today
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
os.environ.setdefault("SACH_LEDGER", "data/red_team_ledger.json")
from sach.pipeline import check_forward
from sach.retrieve import default_retrievers
from sach.llm import get_llm

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--only", default="", help="run only this category")
args = ap.parse_args()

cases = json.load(open("data/red_team.json", encoding="utf-8"))
if args.only:
    cases = [c for c in cases if c["category"] == args.only]
if args.limit:
    cases = cases[: args.limit]
ret, llm = default_retrievers(), get_llm()
kw = {"use_cache": False} if "use_cache" in inspect.signature(check_forward).parameters else {}

def show(s, n=70):
    s = " ".join(s.split())
    return (s[: n - 1] + "…" if len(s) > n else s).replace("|", "\\|")

res = []
for i, c in enumerate(cases, 1):
    print(f"[{i}/{len(cases)}] {c['id']:34} -> ", end="", flush=True)
    try:
        out = check_forward(c["text"], ret, llm, log=False, **kw)
        verdict, err = out["verdict"], ""
    except Exception as e:        # a crash is reported, never counted as a pass
        out, verdict, err = {"claims": []}, "ERROR", f"{type(e).__name__}: {e}"
    status = "FAIL" if verdict in c["must_not"] else ("UNEXPECTED" if verdict not in c["acceptable"] else "PASS")
    res.append({**c, "got": verdict, "status": status, "err": err, "degraded": bool(out.get("degraded")),
                "reasons": [v["reason_code"] for v in out["claims"]],
                "cites": [x["url"] for v in out["claims"] for x in v["citations"]]})
    print(verdict, status, flush=True)

n = len(res)
overclaims = [r for r in res if r["status"] == "FAIL"]
unexpected = [r for r in res if r["status"] == "UNEXPECTED"]
failed = getattr(llm, "failures", 0)
if llm is None:
    mode = "LIMITED MODE, no AI judge (no LLM key): rules only, clear PIB debunks can give FALSE, TRUE and MISLEADING are impossible. This run does not exercise the judge prompt, validation of judge replies, or consensus."
elif failed:
    mode = f"DEGRADED: the AI judge failed on {failed} source judgements (quota/outage), so those sources fell back to the safe PIB-debunk-only check. Not a full-LLM measurement."
else:
    mode = "FULL LLM: AI stance judge with code-level validation and second-opinion consensus"
try:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip() or "unknown"
except Exception:
    commit = "unknown"
retr = ", ".join(type(x).__name__ for x in ret)
when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

L = ["# Red team", "",
     f"Date: {when}. Commit: `{commit}`. Mode: **{mode}** Retrieval: {retr}." + (" Filter: " + (args.only or "") + (f", first {args.limit}" if args.limit else "") if (args.only or args.limit) else ""), "",
     f"**{n} cases, {len(overclaims)} overclaims** ({len(unexpected)} unexpected verdicts that were not overclaims).", "",
     "An overclaim is a verdict listed in the case's `must_not`: Sach said TRUE or FALSE (or MISLEADING) where nothing official supports it. "
     "UNEXPECTED means the verdict was not an overclaim but not in the case's `acceptable` list either (for example an error). Both are listed in full below.", "",
     "| Case | Category | Lang | Attack | Verdict | Result |", "|---|---|---|---|---|---|"]
for r in res:
    L.append(f"| {r['id']} | {r['category']} | {r['lang']} | {show(r['attack'], 90)} | {r['got']}{' (limited)' if r['degraded'] else ''} | {r['status']} |")
L += ["", "## Failures and unexpected results", ""]
if not (overclaims or unexpected):
    L.append("None in this run.")
for r in overclaims + unexpected:
    L += [f"### {r['id']}: {r['status']}", "", f"- Category: {r['category']}; language: {r['lang']}; attack: {r['attack']}",
          f"- Verdict: **{r['got']}**; must not be: {', '.join(r['must_not'])}; acceptable: {', '.join(r['acceptable'])}",
          f"- Reason codes: {', '.join(r['reasons']) or 'none'}; degraded run: {r['degraded']}",
          f"- Citations: {', '.join(r['cites']) or 'none'}"]
    if r["err"]:
        L.append(f"- Error: {r['err']}")
    L += ["- Full text of the forward:", "", "```", r["text"], "```", ""]
L += ["## What the tests cover offline", "",
      "`tests/test_redteam.py` runs every case in `data/red_team.json` through `check_forward` with fakes and no network, under 8 judge conditions "
      "(no AI; an obedient judge that always confirms; one that always contradicts; one that returns the injected instruction's requested quote; "
      "one that copies a real page sentence but picks the wrong label (confirms, contradicts, partial); one whose translation step obeys an injection) "
      "against 7 retriever conditions (nothing; an unrelated official page; the real page the case is based on; a hostile fact-checker page; "
      "hostile official pages with instructions only, with the claim plus instructions, and as a PIB debunk). The judges are built on the real `_Judge`, "
      "so reply parsing, `validate_stance` and consensus run for real; only the model's words are scripted. It also tests lookalike hosts "
      "(`is_official` / `is_factchecker`), claim extraction of instruction lines, and direct `validate_stance` attacks.", "",
      "## Limits of this exercise", "",
      "- A small hand-written set, written by the people who built Sach, not an outside red team: it finds the attacks we thought of.",
      "- Live results vary run to run (search results change; free-tier models answer differently, and quota failures push runs into limited mode).",
      "- The instruction-injection check on pages and claims is a blocklist of common phrasings. The hard defences are the verbatim quote, number, "
      "subject and qualifier checks, the debunk/negation rules, and the official-host rule.",
      "- An official-host page that really does assert a falsehood cannot be caught by Sach: the host is the trust root.",
      "- Pages in the offline tests marked as reconstructions are short rewrites of announcements (facts from `data/eval_set.json`), not verbatim copies.",
      ""]
open("docs/red-team.md", "w", encoding="utf-8").write("\n".join(L))
print(f"\n{n} cases, {len(overclaims)} overclaims, {len(unexpected)} unexpected. Wrote docs/red-team.md")
sys.exit(1 if overclaims else 0)
