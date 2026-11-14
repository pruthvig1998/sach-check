"""L4: a retrieval-only, read-only SQLite full-text index of PIB releases (data/pib.sqlite), built by scripts/harvest_pib_feeds.py.

It only helps `retrieve.PibRetriever` find candidate pages. It is NOT the match layer's debunk list (data/pib_index.jsonl, which only accepts
debunk-titled records), so growing this file can never make an ordinary release count as a debunk. Every candidate is still re-fetched live and
judged exactly as before, and a candidate must pass the same word-coverage and overlap gates as `index.search`.
Switch: SACH_PIB_FTS=1 turns it on (default off until it has been measured). A missing or unreadable file means no candidates, never an error.

Table `releases(prid, date, lang, title, excerpt, url, fetched)` plus FTS5 table `fts` over title and excerpt (porter stemming, BM25 with the title
weighted above the excerpt). Pure stdlib."""
from __future__ import annotations
import os, re, sqlite3
from .stance import overlap, subject_coverage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "pib.sqlite")
EXCERPT_CHARS = 600
_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
_STOP = {"the", "and", "for", "that", "this", "with", "from", "will", "has", "have", "are", "was", "were", "been", "all", "any", "not", "its",
         "their", "they", "them", "who", "which", "under", "into", "per", "new", "government", "india", "indian", "central", "union", "ministry"}

SCHEMA = """
create table if not exists releases(prid text primary key, date text, lang text, title text, excerpt text, url text, fetched text);
create virtual table if not exists fts using fts5(title, excerpt, content='releases', content_rowid='rowid', tokenize='porter unicode61');
create trigger if not exists releases_ai after insert on releases begin
  insert into fts(rowid, title, excerpt) values (new.rowid, new.title, new.excerpt); end;
create trigger if not exists releases_ad after delete on releases begin
  insert into fts(fts, rowid, title, excerpt) values ('delete', old.rowid, old.title, old.excerpt); end;
create trigger if not exists releases_au after update on releases begin
  insert into fts(fts, rowid, title, excerpt) values ('delete', old.rowid, old.title, old.excerpt);
  insert into fts(rowid, title, excerpt) values (new.rowid, new.title, new.excerpt); end;
create table if not exists fetch_log(prid text primary key, status text, at text);
"""


def enabled() -> bool:
    return os.environ.get("SACH_PIB_FTS", "0") == "1"


def _connect_ro(path: str):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)


def query_for(claim: str) -> str:
    """An FTS5 MATCH expression from the claim's own words. Every term is double-quoted, so operator words (AND, OR, NOT, NEAR) and punctuation
    in a forward can never change the query's meaning. Returns '' when there is nothing to search on."""
    seen, terms = set(), []
    for w in _WORD.findall((claim or "").lower()):
        if w in _STOP or w in seen or w.isdigit() and len(w) < 3:
            continue
        seen.add(w); terms.append('"' + w.replace('"', "") + '"')
        if len(terms) >= 12:
            break
    return " OR ".join(terms)


def search(claim: str, top_n: int = 5, path: str | None = None, pool: int = 60) -> list[dict]:
    """Candidate releases for a claim, best first, each {prid, title, url, date, score}. The score uses the same formula and the same gates as
    `index.search` (word coverage >= 0.5 and overlap >= 0.3), so it is comparable with the other candidate lists."""
    path = path or DB_PATH
    q = query_for(claim)
    if not q or not os.path.exists(path):
        return []
    try:
        con = _connect_ro(path)
        try:
            rows = con.execute(
                "select r.prid, r.title, r.excerpt, r.url, r.date from fts join releases r on r.rowid = fts.rowid "
                "where fts match ? order by bm25(fts, 8.0, 1.0) limit ?", (q, pool)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    hits = []
    for prid, title, excerpt, url, date in rows:
        text = f"{title or ''} {excerpt or ''}"
        cov, ov = subject_coverage(claim, text), overlap(claim, text)
        if cov >= 0.5 and ov >= 0.3:
            hits.append({"prid": str(prid), "title": title or "", "url": url or "", "date": date or "", "score": round(0.6 * cov + 0.4 * ov, 4)})
    hits.sort(key=lambda h: -h["score"])
    return hits[:top_n]


# ------------------------------------------------------------------------------------------------ building (used by the harvester and tests)
def open_rw(path: str | None = None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def excerpt_of(title: str, body: str) -> str:
    """First ~600 characters of a release body, without the PIB dateline ('Posted On: ... by PIB ...'), for the index only."""
    b = re.sub(r"^.{0,160}?\bPosted On:?\s*\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s+by\s+PIB\s+(?:New\s+Delhi|\w+)\s*", "", " ".join((body or "").split()), flags=re.I)
    return b[:EXCERPT_CHARS].rsplit(" ", 1)[0] if len(b) > EXCERPT_CHARS else b


def upsert(rows: list[dict], path: str | None = None, con=None) -> int:
    """Insert or replace releases ({prid, title, excerpt?, body?, url, date?, lang?, fetched?}). Returns how many rows were written.
    Pass `con` (from open_rw) to write inside the caller's connection and transaction; otherwise a connection is opened and committed here."""
    own = con is None
    con = con or open_rw(path)
    n = 0
    try:
        for r in rows:
            prid = str(r.get("prid") or "")
            title = " ".join(str(r.get("title") or "").split())
            if not prid.isdigit() or not title:
                continue
            ex = r.get("excerpt") or excerpt_of(title, r.get("body", ""))
            con.execute("delete from releases where prid = ?", (prid,))
            con.execute("insert into releases(prid, date, lang, title, excerpt, url, fetched) values (?,?,?,?,?,?,?)",
                        (prid, str(r.get("date") or r.get("posted_on") or ""), str(r.get("lang") or ""), title, ex[:EXCERPT_CHARS],
                         str(r.get("url") or f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}"), str(r.get("fetched") or "")))
            n += 1
        if own:
            con.commit()
    finally:
        if own:
            con.close()
    return n


def count(path: str | None = None) -> int:
    path = path or DB_PATH
    if not os.path.exists(path):
        return 0
    try:
        con = _connect_ro(path)
        try:
            return con.execute("select count(*) from releases").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return 0
