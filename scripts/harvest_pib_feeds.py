"""Build and grow data/pib.sqlite (L4: retrieval-only full-text index of PIB releases; see sach/pibfts.py).

  python scripts/harvest_pib_feeds.py --seed                 # load the existing index + seed debunks (no network)
  python scripts/harvest_pib_feeds.py --rss                  # newest items from PIB's RSS feeds (English, Hindi)
  python scripts/harvest_pib_feeds.py --prids 2336211-2334711 --max 1500   # walk a PRID window, newest first (resumable)

Polite by design: one request every 2 seconds through sach/fetch.py (the project's honest User-Agent), a hard cap per run, a fetch log so a
release or a miss is never requested twice, and an immediate stop if PIB starts refusing (HTTP 403/429/5xx streak). It never tries to get around a
block. Each run commits every 25 rows, so an interrupted run loses nothing."""
import argparse, os, pathlib, sys, time
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
import sach  # noqa: loads .env
from sach import index as pib_index, pibfts
from sach.fetch import fetch
from sach.lang import detect_language
from sach.pib import PR_URL, is_pib, parse_release, rss_index
import json
from datetime import datetime, timezone

def _now(): return datetime.now(timezone.utc).date().isoformat()

def seed(con) -> int:
    rows = []
    for r in pib_index.load():
        if str(r.get("prid", "")).isdigit() and r.get("title"):
            rows.append({"prid": r["prid"], "title": r["title"], "excerpt": r.get("excerpt", ""), "date": r.get("posted_on", ""), "url": r.get("url", ""), "fetched": "seed"})
    try:
        for it in json.load(open("data/seed_debunks.json", encoding="utf-8")):
            if str(it.get("prid", "")).isdigit() and it.get("title"):
                rows.append({"prid": it["prid"], "title": it["title"], "fetched": "seed"})
    except (OSError, ValueError):
        pass
    have = {r[0] for r in con.execute("select prid from releases")}
    rows = [r for r in rows if str(r["prid"]) not in have]
    return pibfts.upsert(rows, con=con)

def known(con) -> set:
    return {r[0] for r in con.execute("select prid from releases")} | {r[0] for r in con.execute("select prid from fetch_log")}

def fetch_one(con, prid: str) -> str:
    """-> 'ok' | 'miss' | 'blocked'. Writes the release or a fetch-log entry."""
    rec = fetch(PR_URL.format(prid))
    st = rec.get("status")
    if st in (403, 429) or (isinstance(st, int) and st >= 500):
        return "blocked"
    url = rec.get("final_url", "")
    if st != 200 or not is_pib(url) or not rec.get("body"):
        con.execute("insert or replace into fetch_log values (?,?,?)", (prid, f"miss:{st}", _now())); return "miss"
    d = parse_release(rec["body"])
    if not d["title"]:
        con.execute("insert or replace into fetch_log values (?,?,?)", (prid, "empty", _now())); return "miss"
    pibfts.upsert([{"prid": prid, "title": d["title"], "body": d["body"], "date": d.get("posted_on", ""), "lang": detect_language(d["title"]), "url": url, "fetched": _now()}], con=con)
    con.execute("insert or replace into fetch_log values (?,?,?)", (prid, "ok", _now()))
    return "ok"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true"); ap.add_argument("--rss", action="store_true")
    ap.add_argument("--prids", default="", help="HIGH-LOW, walked downwards, for example 2336211-2334711")
    ap.add_argument("--max", type=int, default=200, help="hard cap on network fetches in this run")
    ap.add_argument("--reindex", action="store_true", help="rebuild the full-text table from the stored releases (no network)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between requests (minimum 1.0)")
    a = ap.parse_args()
    pause = max(1.0, a.sleep)
    if a.reindex:
        print("reindexed", pibfts.reindex(), "releases"); return
    con = pibfts.open_rw()
    if a.seed:
        print("seeded from the existing index and seed debunks:", seed(con), "rows")
    todo = []
    if a.rss:
        have = known(con)
        for it in rss_index(mods=(6,), langs=(1, 2), regs=(3,)):
            if it["prid"] not in have:
                todo.append(it["prid"])
        print("RSS: new releases to fetch:", len(todo))
    if a.prids:
        hi, lo = (int(x) for x in a.prids.split("-"))
        have = known(con)
        queued = set(todo)
        todo += [str(p) for p in range(max(hi, lo), min(hi, lo) - 1, -1) if str(p) not in have and str(p) not in queued]
    done = {"ok": 0, "miss": 0}; streak = 0
    for i, prid in enumerate(todo[: max(0, a.max)]):
        try:
            res = fetch_one(con, prid)
        except Exception as e:
            print("stopped on an error:", type(e).__name__); break
        if res == "blocked":
            streak += 1
            if streak >= 3:
                print("PIB is refusing requests (403/429/5xx three times in a row): stopping. Nothing was retried."); break
        else:
            streak = 0; done[res] += 1
        if (i + 1) % 25 == 0:
            con.commit(); print(f"  {i + 1}/{min(len(todo), a.max)} fetched: {done['ok']} releases, {done['miss']} misses", flush=True)
        time.sleep(pause)
    con.commit(); con.close()
    print(f"done: {done['ok']} releases added, {done['miss']} misses; database now holds {pibfts.count()} releases")

if __name__ == "__main__":
    main()
