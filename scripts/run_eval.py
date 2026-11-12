"""Score Sach over data/eval_set.json and write docs/evaluation.md (failures included)."""
import json, os, sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
os.environ.setdefault("SACH_LEDGER", "data/eval_ledger.json")
from sach.pipeline import check_forward
from sach.retrieve import default_retrievers
from sach.llm import get_llm

rows = json.load(open("data/eval_set.json", encoding="utf-8"))
ret, llm = default_retrievers(), get_llm()
res = []
for r in rows:
    out = check_forward(r["claim"], ret, llm, log=False)
    res.append({**r, "got": out["verdict"], "cites": [c["url"] for v in out["claims"] for c in v["citations"]]})
n = len(res); ok = sum(r["got"] == r["label"] for r in res)
false_pos = [r for r in res if r["got"] == "FALSE" and r["label"] != "FALSE"]
lab = lambda L: [r for r in res if r["label"] == L]
L = ["# Evaluation", "", f"Mode: {'LLM stance' if llm else 'heuristic stance (no ANTHROPIC_API_KEY)'}; retrieval: {', '.join(type(x).__name__ for x in ret)}.", "",
     f"- Claims: **{n}** (target was 100+; see limitations)", f"- Exact-match accuracy: **{ok}/{n}**",
     f"- **Overclaimed FALSE (the unforgivable failure): {len(false_pos)}**"]
for l in ("FALSE", "TRUE", "UNVERIFIED"):
    g = lab(l); L.append(f"- Label {l}: {sum(r['got']==l for r in g)}/{len(g)} correct; {sum(r['got']=='UNVERIFIED' for r in g)} abstained as UNVERIFIED")
L += ["", "| Claim | Label | Sach | Result |", "|---|---|---|---|"]
for r in res:
    tag = "OVERCLAIM" if r in false_pos else ("ok" if r["got"] == r["label"] else "miss (abstained)" if r["got"] == "UNVERIFIED" else "WRONG")
    L.append(f"| {r['claim']} | {r['label']} | {r['got']} | {tag} |")
L += ["", "## Limitations (read before citing these numbers)",
      "- The set is tiny: every item was hand-verified from a PIB page actually fetched, not bulk-scraped. PIB has no listing page for debunks, and the RSS feed returns only the latest 20 items.",
      "- The FALSE claims are paraphrases of PIB debunk titles and the retriever indexes those same pages, so FALSE recall here is optimistic (circular).",
      "- Heuristic stance cannot confirm TRUE claims, so TRUE items abstain. An LLM key is needed to test confirmation.",
      "- A real 100+ evaluation needs a search provider (BRAVE_API_KEY) or a bulk crawl of PIB press releases."]
open("docs/evaluation.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L[:9]))
