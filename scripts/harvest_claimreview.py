"""Build data/claimreview.sqlite from the public Data Commons ClaimReview feed (about 200 MB of JSON, refreshed daily by Google).

  python scripts/harvest_claimreview.py                 # download the feed to a temporary file, then build
  python scripts/harvest_claimreview.py --file feed.json  # build from a copy already on disk

Kept: only reviews published on the fact-checker sites Sach already lists (sach/fetch.py is_factchecker), with a claim, a rating and an
https link, dated SINCE or later. Stored per review: the reviewed claim (at most 300 characters), the publisher's own rating words, the
publisher's site, the link and the date. Never the article text. The file is rebuilt from scratch each run."""
import argparse, json, os, sqlite3, sys, tempfile, time, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sach import crcorpus
from sach.fetch import is_factchecker
from sach.pibfts import _MARKS

FEED = "https://storage.googleapis.com/datacommons-feeds/claimreview/latest/data.json"
SINCE = "2023-01-01"
# Fact Crescendo runs country editions on subdomains: only the India editions are kept.
NOT_INDIA = ("srilanka.", "cambodia.", "thailand.", "myanmar.", "afghanistan.", "bangladesh.")


def rows(feed: dict):
    seen, today = set(), time.strftime("%Y-%m-%d", time.gmtime())
    for el in feed.get("dataFeedElement") or []:
        for it in el.get("item") or []:
            url = str(it.get("url") or el.get("url") or "")
            claim = " ".join(str(it.get("claimReviewed") or "").split())
            rating = " ".join(str((it.get("reviewRating") or {}).get("alternateName") or "").split())
            date = str(it.get("datePublished") or "")[:10]
            host = url.split("/")[2] if url.count("/") >= 2 else ""
            if (not (url.startswith("https://") and claim and rating and SINCE <= date <= today and is_factchecker(url))
                    or host.startswith(NOT_INDIA) or url in seen):
                continue
            seen.add(url)
            yield url, claim[:300], rating[:80], host.removeprefix("www.")[:80], date     # the site itself: the feed's free-text author field held bylines, a rating word and stray text


def build(feed: dict, out: str) -> int:
    if os.path.exists(out):
        os.remove(out)
    con = sqlite3.connect(out)
    con.executescript(crcorpus.SCHEMA % _MARKS)
    n = 0
    for r in rows(feed):
        con.execute("insert or ignore into reviews(url, claim, rating, publisher, date) values (?,?,?,?,?)", r)
        n += 1
    con.commit()
    con.execute("vacuum")
    con.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--out", default=crcorpus.DB_PATH)
    a = ap.parse_args()
    path = a.file
    if not path:
        path = os.path.join(tempfile.mkdtemp(), "claimreview.json")
        print("downloading", FEED)
        urllib.request.urlretrieve(FEED, path)
    with open(path, encoding="utf-8") as f:
        feed = json.load(f)
    n = build(feed, a.out)
    print("kept", n, "reviews;", round(os.path.getsize(a.out) / 1e6, 1), "MB;", "feed dated", feed.get("dateModified"))


if __name__ == "__main__":
    main()
