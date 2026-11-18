"""Offline corpus of published fact-checks (data/claimreview.sqlite, built by scripts/harvest_claimreview.py from the public Data Commons
ClaimReview feed). Only reviews from the fact-checkers Sach already lists in sach/fetch.py are kept.

Show-only: under an UNVERIFIED result it lists up to three published fact-checks of the same claim, with the publisher's name and a link, and
without the publisher's rating words. It is NOT the match layer: it never sets a verdict and never adds a citation. The gate is exact on
purpose: the same key words and the same numbers, so a fact-check about another place or another amount is never shown.
Switch off with SACH_CR_CORPUS=0. A missing or unreadable file means no results, never an error."""
from __future__ import annotations
import os, re, sqlite3
from .pibfts import ROOT, _STOP, _WORD, _connect_ro, query_for

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


def _key_words(t: str) -> frozenset:
    """The words that carry a claim's meaning: every word of four or more characters that is not a stop word."""
    return frozenset(w for w in _WORD.findall((t or "").lower()) if len(w) >= 4 and w not in _STOP and not w.isdigit())


def search(claim: str, top_n: int = 3, path: str | None = None, pool: int = 40) -> list[dict]:
    """Published fact-checks of the SAME claim: [{claim, publisher, url, date}]. The reviewed claim must use the same key words as `claim`
    (so "crashed in Ahmedabad" never matches "crashed in Kerala") and the same numbers. The publisher's rating is deliberately not returned:
    a rating word beside Sach's own UNVERIFIED would read as a verdict. The reader opens the fact-check to see it."""
    path = path or DB_PATH
    q = query_for(claim)
    if not enabled() or not q or not os.path.exists(path):
        return []
    try:
        con = _connect_ro(path)
        try:
            rows = con.execute("select r.claim, r.publisher, r.url, r.date from fts join reviews r on r.rowid = fts.rowid "
                               "where fts match ? order by bm25(fts) limit ?", (q, pool)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    mine, hits = _key_words(claim), []
    for c, pub, url, date in rows:
        if len(mine) >= 3 and _key_words(c) == mine and _numbers(claim) == _numbers(c) and str(url).startswith("https://"):
            hits.append({"claim": c, "publisher": pub or "", "url": url, "date": date or ""})
    return hits[:top_n]
