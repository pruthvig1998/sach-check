"""Score Sach over data/eval_set.json and write docs/evaluation.md (failures included)."""
import json, os, sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
os.environ.setdefault("SACH_LEDGER", "data/eval_ledger.json")
from sach.pipeline import check_forward
from sach.retrieve import default_retrievers
from sach.llm import get_llm

rows = json.load(open("data/eval_set.json", encoding="utf-8"))
ret, llm = default_retrievers(), get_llm()
seed_ids = {str(x["prid"]) for x in json.load(open("data/seed_debunks.json"))}
res = []
for r in rows:
    out = check_forward(r["claim"], ret, llm, log=bool(os.environ.get("SACH_SEED_LEDGER")))
    print(f"[{len(res)+1}/{len(rows)}] {r['label']:10} -> ", end="", flush=True)
    res.append({**r, "seeded": any(("PRID=" + i) in r["source"] for i in seed_ids), "got": out["verdict"], "reasons": [v["reason_code"] for v in out["claims"]], "cites": [c["url"] for v in out["claims"] for c in v["citations"]]})
    print(res[-1]["got"], flush=True)
n = len(res); ok = sum(r["got"] == r["label"] for r in res)
false_pos = [r for r in res if r["got"] == "FALSE" and r["label"] != "FALSE"]
lab = lambda L: [r for r in res if r["label"] == L]
L = ["# Evaluation", "", f"Mode: {'LLM stance' if llm else 'heuristic stance (no ANTHROPIC_API_KEY)'}; retrieval: {', '.join(type(x).__name__ for x in ret)}.", "",
     f"- Claims: **{n}** (target was 100+; see limitations)", f"- Exact-match accuracy: **{ok}/{n}**",
     f"- **Overclaimed FALSE (the unforgivable failure): {len(false_pos)}**"]
for l in ("FALSE", "TRUE", "UNVERIFIED"):
    g = lab(l); L.append(f"- Label {l}: {sum(r['got']==l for r in g)}/{len(g)} correct; {sum(r['got']=='UNVERIFIED' for r in g)} abstained as UNVERIFIED")
for tag, flag in (("Seeded (PIB page was in data/seed_debunks.json; retrieval is partly circular)", True), ("Unseeded (retrieval had to find the page itself)", False)):
    g = [r for r in res if r["seeded"] == flag and r["label"] != "UNVERIFIED"]
    if g:
        L.append(f"- {tag}: {sum(r['got']==r['label'] for r in g)}/{len(g)} correct")
L += ["", "| Claim | Label | Sach | Result |", "|---|---|---|---|"]
for r in res:
    tag = "OVERCLAIM" if r in false_pos else ("ok" if r["got"] == r["label"] else "miss (abstained)" if r["got"] == "UNVERIFIED" else "WRONG")
    L.append(f"| {r['claim']} | {r['label']} | {r['got']} | {tag} |")
L += ["", "## Limitations (read before citing these numbers)",
      "- The set is tiny: every item was hand-verified from a PIB page actually fetched, not bulk-scraped. PIB has no listing page for debunks, and the RSS feed returns only the latest 20 items.",
      "- The FALSE claims are paraphrases of PIB debunk titles and the retriever indexes those same pages, so FALSE recall here is optimistic (circular).",
      "- Stance was judged by Gemini when GEMINI_API_KEY is set; the heuristic alone cannot confirm TRUE claims and abstains.",
      "- Relabel disclosure: the first control (\"free laptops to all students\") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.",
      "- Relabel disclosure 2: the RPF 4,208 Constable / 452 SI claim was first labelled FALSE (from PIB debunk 2009349), but that debunk was about a fake notice on one website; a genuine PIB release (PRID 2246142) lists those same vacancy numbers. Sach said TRUE; relabelled TRUE after inspecting the evidence. Two labels were changed after seeing results, so treat headline accuracy as indicative only.",
      "- Retrieval varies run to run (Brave results change), so single-run numbers move by a claim or two.",
      "- Official-domain rule is *.gov.in / *.nic.in / who.int, so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.",
      "- A real 100+ evaluation needs a search provider (BRAVE_API_KEY) or a bulk crawl of PIB press releases."]
open("docs/evaluation.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L[:9]))
