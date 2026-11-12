"""LLM-free retrieval evaluation: for every eval claim whose source PIB page is known, does retrieval surface that page?
Reports Brave-only (live search, no local knowledge) separately from PIB seed/index/RSS retrieval, because the local
index was harvested from the same kind of pages and is partly circular. Writes docs/retrieval-evaluation.md."""
import json, os, pathlib, re, sys
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
import sach  # noqa
from sach import index
from sach.retrieve import BraveRetriever, PibRetriever, canonical_key

rows = [r for r in json.load(open("data/eval_set.json", encoding="utf-8")) if re.search(r"PRID=(\d+)", r["source"]) and r["label"] != "UNVERIFIED"]
seed = {str(x["prid"]) for x in json.load(open("data/seed_debunks.json", encoding="utf-8"))}
indexed = {str(r["prid"]) for r in index.load()}
brave, pib = BraveRetriever(), PibRetriever(use_rss=False)
res = []
for r in rows:
    prid = re.search(r"PRID=(\d+)", r["source"]).group(1)
    want = "pib:" + prid
    try: eb = {canonical_key(e.url) for e in brave.search(r["claim"])}
    except Exception: eb = set()
    try: ep = {canonical_key(e.url) for e in pib.search(r["claim"])}
    except Exception: ep = set()
    res.append({"claim": r["claim"], "prid": prid, "brave": want in eb, "local": want in ep, "any": want in (eb | ep),
                "in_seed": prid in seed, "in_index": prid in indexed})
    print(f'{"B" if res[-1]["brave"] else "-"}{"L" if res[-1]["local"] else "-"}  {r["claim"][:70]}', flush=True)
n = len(res); pct = lambda k, g=res: f"{sum(x[k] for x in g)}/{len(g)}"
fresh = [x for x in res if not x["in_seed"] and not x["in_index"]]
L = ["# Retrieval evaluation (no LLM involved)", "",
     f"For {n} eval claims whose source PIB page is known: does retrieval put that exact page in front of the judge?", "",
     f"- **Brave live search only** (no local knowledge): **{pct('brave')}**",
     f"- **Local PIB seed + harvested index** ({len(indexed)} indexed releases): **{pct('local')}** (partly circular: the index was built from searches on the same topics)",
     f"- **Combined (what the app uses): {pct('any')}**",
     f"- Items whose page is in neither the seed nor the index ({len(fresh)}): Brave found {pct('brave', fresh)}, combined {pct('any', fresh)}",
     "", "| Claim | PRID | Brave | Local | In seed | In index |", "|---|---|---|---|---|---|"]
for x in res:
    L.append(f'| {x["claim"][:90]} | {x["prid"]} | {"yes" if x["brave"] else "no"} | {"yes" if x["local"] else "no"} | {"yes" if x["in_seed"] else ""} | {"yes" if x["in_index"] else ""} |')
open("docs/retrieval-evaluation.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L[:10]))
