"""Grow data/pib_index.jsonl by searching PIB (via Brave, site:pib.gov.in) for debunks, clarifications and announcements.
Polite: shares the app's 1 request/second Brave throttle and the cached 0.5 s page fetcher.
Usage: python scripts/harvest_pib.py [--max-queries 80] [--dry-run]"""
import argparse, os, pathlib, re, sys
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
import sach  # noqa: loads .env
from sach import index
from sach.lang import detect_language
from sach.pib import get_release, DEBUNK_MARKERS
from sach.retrieve import BraveRetriever
from sach.fetch import host_of

PHRASES = ["PIB Fact Check fake claim", "clarification fake message government", "misleading claim viral post busted", "fake notification recruitment clarification"]
TOPICS = ["Railways", "RBI bank", "ration card", "pension", "PM Kisan", "Ayushman Bharat", "Aadhaar", "income tax", "GST", "passport", "scholarship",
          "Indian Army", "Air Force", "EPFO", "LPG subsidy", "UPI payment", "COVID vaccine", "health myth cure", "CBSE exam", "NEET", "UPSC", "SSC recruitment",
          "India Post", "Ministry of Finance", "Ministry of Health", "Ministry of Home Affairs", "Ministry of Defence", "Department of Telecom SIM", "Election Commission",
          "currency note", "free laptop", "free scooty", "gas cylinder", "petrol diesel price", "mobile recharge free", "bank holiday", "retirement age",
          "DA hike salary", "8th pay commission", "UGC", "AICTE", "drone", "Digital India", "Jan Dhan", "PM Awas Yojana", "Mudra loan", "Ujjwala", "agniveer",
          "farmers loan waiver", "unemployment allowance", "women Rs per month scheme", "free ration", "Swachh Bharat", "e-Shram", "Sukanya Samriddhi"]

def build_queries():
    for t in TOPICS:
        for p in PHRASES[:2]:
            yield f"site:pib.gov.in {p} {t}"
    for t in TOPICS[:20]:
        yield f"site:pib.gov.in {PHRASES[3]} {t}"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--max-queries", type=int, default=80); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    b = BraveRetriever()
    if not b.key:
        sys.exit("BRAVE_API_KEY is not set (put it in .env)")
    known = {str(r["prid"]) for r in index.load()}
    new_entries, seen, n_q = [], set(known), 0
    for q in build_queries():
        if n_q >= a.max_queries:
            break
        n_q += 1
        try:
            urls = b._search(q, count=20)
        except Exception as e:
            print(f"[{n_q}] query failed: {e}", flush=True); continue
        found = 0
        for u in urls:
            if host_of(u) not in ("pib.gov.in", "www.pib.gov.in"):
                continue
            m = re.search(r"PRID=(\d+)", u, re.I)
            if not m or m.group(1) in seen:
                continue
            prid = m.group(1); seen.add(prid)
            if a.dry_run:
                found += 1; continue
            try:
                rel = get_release(prid)
            except Exception:
                rel = None
            if not rel or not rel["title"]:
                continue
            head = f'{rel["title"]} {rel["body"][:600]}'
            new_entries.append({"prid": prid, "title": rel["title"], "ministry": rel["ministry"], "posted_on": rel["posted_on"],
                                "url": rel["url"], "fetched_at": rel["fetched_at"], "lang": detect_language(rel["title"]),
                                "debunk": bool(DEBUNK_MARKERS.search(head)), "excerpt": rel["body"][:1500]})
            found += 1
        print(f"[{n_q}/{a.max_queries}] +{found} new  total_new={len(new_entries)}  | {q[:70]}", flush=True)
        if len(new_entries) and len(new_entries) % 25 < found:
            index.append(new_entries); new_entries = []          # save progress regularly
    added = index.append(new_entries) if not a.dry_run else 0
    print(f"done: queries={n_q} index_size={len(index.load())} (+{added} in last flush)")

if __name__ == "__main__":
    main()
