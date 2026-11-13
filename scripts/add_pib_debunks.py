"""Add verified PIB debunk releases to data/pib_index.jsonl from a list of PRIDs.

Every record is built from the live PIB page (https://pib.gov.in/PressReleasePage.aspx?PRID=N): title, date and body come from the page, nothing
is typed in by hand. A PRID is added only if the page loads (HTTP 200), has a title, has a "Posted On" date, and the title contains a strict
debunk word (the same test sach/match.py applies), so a record that the match layer would ignore is never added.
Polite: honest User-Agent (sach.fetch.UA), >= 1.1 s between requests, no retries, no bot-check evasion.
Usage: python scripts/add_pib_debunks.py 2118851 2163332 ... [--file prids.txt] [--dry-run]"""
import argparse, os, pathlib, sys, time
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
from sach import index
from sach.lang import detect_language
from sach.match import _STRICT, _pib_date
from sach.pib import get_release, DEBUNK_MARKERS

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("prids", nargs="*"); ap.add_argument("--file"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    prids = list(a.prids)
    if a.file:
        prids += [x.strip() for x in open(a.file, encoding="utf-8").read().split() if x.strip().isdigit()]
    known = {str(r.get("prid")) for r in index.load()}
    new, seen = [], set()
    for prid in prids:
        if prid in known or prid in seen:
            print(f"{prid}: already in index"); continue
        seen.add(prid)
        try:
            rel = get_release(prid)          # uses the cached fetcher; we add our own 1.1 s pause below
        except Exception as e:
            rel = None; print(f"{prid}: fetch failed ({e})")
        time.sleep(1.1)
        if not rel or not rel["title"]:
            print(f"{prid}: page not retrievable, skipped"); continue
        d = _pib_date(rel["posted_on"])
        ok = bool(d) and bool(_STRICT.search(rel["title"]))
        print(f'{prid}: {"ADD " if ok else "skip"} {d or "no-date"} | {rel["title"][:110]}')
        if ok:
            head = f'{rel["title"]} {rel["body"][:600]}'
            new.append({"prid": prid, "title": rel["title"], "ministry": rel["ministry"], "posted_on": rel["posted_on"], "url": rel["url"],
                        "fetched_at": rel["fetched_at"], "lang": detect_language(rel["title"]),
                        "debunk": bool(DEBUNK_MARKERS.search(head)), "excerpt": rel["body"][:1500]})
    n = 0 if a.dry_run else index.append(new)
    print(f"candidates={len(new)} added={n} index_size={len(index.load())}")

if __name__ == "__main__":
    main()
