"""Offline corpus of published fact-checks (data/claimreview.sqlite, built by scripts/harvest_claimreview.py from the public Data Commons
ClaimReview feed). Only reviews from the fact-checkers Sach already lists in sach/fetch.py are kept.

Show-only: under an UNVERIFIED result it lists up to three published fact-checks that look related, with the publisher's name, their own rating
words and a link. It is NOT the match layer: it never sets a verdict, never adds a citation, and says "may be related" because the gate here is
word overlap, not a reviewed match. Numbers must agree, so a fact-check about Rs 5,000 is never shown for a claim about Rs 50,000.
Switch off with SACH_CR_CORPUS=0. A missing or unreadable file means no results, never an error."""
from __future__ import annotations
import os, re, sqlite3
from .pibfts import ROOT, _connect_ro, query_for
from .stance import overlap, subject_coverage

DB_PATH = os.path.join(ROOT, "data", "claimreview.sqlite")
SCHEMA = """
create table if not exists reviews(url text primary key, claim text, rating text, publisher text, date text);
create virtual table if not exists fts using fts5(claim, content='reviews', content_rowid='rowid', tokenize="unicode61 tokenchars '%s'");
create trigger if not exists reviews_ai after insert on reviews begin insert into fts(rowid, claim) values (new.rowid, new.claim); end;
"""


def enabled() -> bool:
    return os.environ.get("SACH_CR_CORPUS", "1") != "0"


def _numbers(t: str) -> set:
    return set(re.findall(r"\d+", (t or "").replace(",", "")))


def search(claim: str, top_n: int = 3, path: str | None = None, pool: int = 40) -> list[dict]:
    """Published fact-checks whose reviewed claim is close to `claim`: [{claim, rating, publisher, url, date}], best first."""
    path = path or DB_PATH
    q = query_for(claim)
    if not enabled() or not q or not os.path.exists(path):
        return []
    try:
        con = _connect_ro(path)
        try:
            rows = con.execute("select r.claim, r.rating, r.publisher, r.url, r.date from fts join reviews r on r.rowid = fts.rowid "
                               "where fts match ? order by bm25(fts) limit ?", (q, pool)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    hits = []
    for c, rating, pub, url, date in rows:
        cov, ov = subject_coverage(claim, c or ""), overlap(claim, c or "")
        back = subject_coverage(c or "", claim)                      # both ways: each text must be mostly about what the other says
        if cov >= 0.8 and back >= 0.6 and ov >= 0.6 and _numbers(claim) == _numbers(c) and str(url).startswith("https://"):
            hits.append((round(0.5 * cov + 0.5 * ov, 4), {"claim": c, "rating": rating or "", "publisher": pub or "", "url": url, "date": date or ""}))
    hits.sort(key=lambda x: -x[0])
    return [h for _, h in hits[:top_n]]
