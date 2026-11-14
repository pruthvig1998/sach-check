"""Does the L4 full-text index put the right PIB page among the candidates? No LLM, no page fetches: it compares PibRetriever.candidate_prids with
SACH_PIB_FTS off and on, for every evaluation claim (labelled TRUE or FALSE) whose source PIB page is known.
Reports the numbers split by (a) whether the expected release is in data/pib.sqlite at all (the circular part, because a release can only be
retrieved from the index if it was harvested) and (b) English versus other languages (non-English claims are translated before search in the live
pipeline, which this script does not do).
Usage: python scripts/measure_pib_retrieval.py [--write docs/research/l4-retrieval-measurement.md]"""
import argparse, json, os, pathlib, re, sqlite3, sys
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
import sach  # noqa
from sach import index as pib_index, pibfts
from sach.retrieve import PibRetriever

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", default=""); a = ap.parse_args()
    rows = [r for r in json.load(open("data/eval_set.json", encoding="utf-8")) if re.search(r"PRID=(\d+)", r["source"]) and r["label"] in ("TRUE", "FALSE")]
    seed = {str(x["prid"]) for x in json.load(open("data/seed_debunks.json", encoding="utf-8"))}
    in_jsonl = {str(r["prid"]) for r in pib_index.load()}
    con = sqlite3.connect(f"file:{pibfts.DB_PATH}?mode=ro", uri=True)
    in_db_new = {r[0] for r in con.execute("select prid from releases where fetched != 'seed'")}      # harvested after the seed
    total_db = con.execute("select count(*) from releases").fetchone()[0]
    ret = PibRetriever(use_rss=False)
    out = []
    for r in rows:
        prid = re.search(r"PRID=(\d+)", r["source"]).group(1)
        os.environ["SACH_PIB_FTS"] = "0"; off = ret.candidate_prids(r["claim"])
        os.environ["SACH_PIB_FTS"] = "1"; on = ret.candidate_prids(r["claim"])
        out.append({"lang": r.get("lang", "en"), "prid": prid, "off": prid in off, "on": prid in on,
                    "known_before": prid in seed or prid in in_jsonl, "harvested_new": prid in in_db_new})
    def rate(sel, k): s = [x for x in out if sel(x)]; return f"{sum(x[k] for x in s)}/{len(s)}"
    L = ["# L4 retrieval measurement", "", f"Database: {total_db} releases (of which {len(in_db_new)} harvested after the seed). {len(out)} evaluation claims labelled TRUE or FALSE with a known source page.", "",
         "Share of claims whose expected PIB release is among the candidates (no page fetches):", "",
         "| Group | Switch off | Switch on |", "|---|---|---|"]
    groups = [("All claims", lambda x: True), ("English claims", lambda x: x["lang"] == "en"), ("Other languages", lambda x: x["lang"] != "en"),
              ("Expected release already known before L4 (seed or old index)", lambda x: x["known_before"]),
              ("Expected release NOT known before L4 (the honest test)", lambda x: not x["known_before"]),
              ("...of which now present in the new database", lambda x: not x["known_before"] and x["harvested_new"]),
              ("...of which absent from the new database", lambda x: not x["known_before"] and not x["harvested_new"])]
    for name, sel in groups:
        L.append(f"| {name} | {rate(sel, 'off')} | {rate(sel, 'on')} |")
    L += ["", "A release can only be retrieved from the index if it was harvested, so the rows 'present' and 'absent' show the ceiling: this index helps for recent releases it holds and cannot help for pages it never saw. The window harvested was fixed before looking at these claims (the newest 1,500 press-release numbers)."]
    text = "\n".join(L); print(text)
    if a.write:
        pathlib.Path(a.write).write_text(text + "\n", encoding="utf-8"); print("wrote", a.write)

if __name__ == "__main__":
    main()
