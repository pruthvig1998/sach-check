"""L4: the read-only SQLite full-text index of PIB releases. Offline: temporary databases and a fake fetcher, no network."""
import importlib.util, os, pathlib, sqlite3
import pytest
from sach import pibfts
from sach.retrieve import PibRetriever

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("harvest_pib_feeds", ROOT / "scripts" / "harvest_pib_feeds.py")
harvest = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(harvest)

COAL = {"prid": "2260621", "title": "Cabinet approves scheme for coal and lignite gasification projects", "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2260621",
        "body": "Posted On: 12 MAR 2026 4:00PM by PIB Delhi The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore."}
OTHER = {"prid": "2260700", "title": "Cabinet approves new railway line", "body": "The Union Cabinet approved a new railway line project in the north east."}
CLAIM = "The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore."


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "pib.sqlite")
    monkeypatch.setattr(pibfts, "DB_PATH", p)
    monkeypatch.delenv("SACH_PIB_FTS", raising=False)
    return p


def test_search_finds_the_matching_release_and_passes_the_same_gates_as_the_index(db):
    assert pibfts.upsert([COAL, OTHER], db) == 2 and pibfts.count(db) == 2
    hits = pibfts.search(CLAIM, 5, db)
    assert [h["prid"] for h in hits] == ["2260621"] and hits[0]["score"] > 0.8
    assert pibfts.search("Cabinet approves something about railways and coal mines in a far away state", 5, db) == []      # one shared word is not enough


def test_the_excerpt_loses_the_pib_dateline_and_is_capped():
    ex = pibfts.excerpt_of("t", COAL["body"])
    assert ex.startswith("The Union Cabinet has approved") and "Posted On" not in ex
    assert len(pibfts.excerpt_of("t", "word " * 500)) <= pibfts.EXCERPT_CHARS


def test_hostile_text_can_never_change_the_query(db):
    q = pibfts.query_for('coal AND "gasification" OR NOT * NEAR/3 (x) -y ^z col:val ; drop table releases;')
    assert all(t.startswith('"') and t.endswith('"') for t in q.split(" OR ")) and q.count(" OR ") < 12
    pibfts.upsert([COAL], db)
    for nasty in ('" OR 1=1 --', "coal NEAR(gasification, 2", "'; DROP TABLE releases; --", "*", "\x00 coal"):
        pibfts.search(nasty, 5, db)                                                    # never raises
    assert pibfts.count(db) == 1
    assert pibfts.query_for("") == "" and pibfts.query_for("a b") == ""


def test_missing_or_corrupt_files_mean_no_candidates_never_an_error(tmp_path):
    assert pibfts.search(CLAIM, 5, str(tmp_path / "nope.sqlite")) == [] and pibfts.count(str(tmp_path / "nope.sqlite")) == 0
    bad = tmp_path / "bad.sqlite"; bad.write_bytes(b"this is not a database" * 100)
    assert pibfts.search(CLAIM, 5, str(bad)) == [] and pibfts.count(str(bad)) == 0


def test_upsert_replaces_a_release_and_keeps_the_search_index_in_sync(db):
    pibfts.upsert([COAL], db)
    pibfts.upsert([{**COAL, "title": "Cabinet approves hydrogen mission", "body": "The Union Cabinet approved the national green hydrogen mission."}], db)
    assert pibfts.count(db) == 1
    assert pibfts.search(CLAIM, 5, db) == []
    assert pibfts.search("The Union Cabinet approved the national green hydrogen mission", 5, db)[0]["prid"] == "2260621"
    assert pibfts.upsert([{"prid": "abc", "title": "x"}, {"prid": "5", "title": ""}], db) == 0          # bad rows are skipped


def test_searching_never_writes_to_the_file(db):
    pibfts.upsert([COAL], db)
    before = (os.path.getmtime(db), os.path.getsize(db))
    pibfts.search(CLAIM, 5, db); pibfts.count(db)
    assert (os.path.getmtime(db), os.path.getsize(db)) == before
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("insert into releases(prid,title) values('1','x')")


def test_switch_defaults_off_and_candidates_only_ever_grow_when_it_is_on(db, monkeypatch):
    pibfts.upsert([COAL, OTHER], db)
    r = PibRetriever(seed_path="/nonexistent.json", use_rss=False)
    assert not pibfts.enabled()
    off = r.candidate_prids(CLAIM)
    monkeypatch.setenv("SACH_PIB_FTS", "1")
    on = r.candidate_prids(CLAIM)
    assert pibfts.enabled() and "2260621" in on and "2260621" not in off
    assert set(off) <= set(on)                                         # the new index adds candidates and never removes one
    assert len(on) <= r.top_n + 1


# ---- the harvester
class FakeFetch:
    def __init__(self, status=200, body=None, url="https://pib.gov.in/PressReleasePage.aspx?PRID=2260621"):
        self.rec = {"status": status, "body": body, "final_url": url, "fetched_at": "t"}
    def __call__(self, url): return self.rec


HTML = "<html><body><h2>Cabinet approves scheme for coal gasification</h2><div id='PdfDiv'>Posted On: 12 MAR 2026 4:00PM by PIB Delhi The Union Cabinet approved coal gasification.</div></body></html>"


def test_harvester_stores_releases_logs_misses_and_reports_blocks(db, monkeypatch):
    con = pibfts.open_rw(db)
    monkeypatch.setattr(harvest, "fetch", FakeFetch(200, HTML))
    assert harvest.fetch_one(con, "2260621") == "ok" and con.execute("select count(*) from releases").fetchone()[0] == 1
    monkeypatch.setattr(harvest, "fetch", FakeFetch(404, "", ))
    assert harvest.fetch_one(con, "2260622") == "miss" and con.execute("select status from fetch_log where prid='2260622'").fetchone()[0].startswith("miss")
    for blocked in (403, 429, 503):
        monkeypatch.setattr(harvest, "fetch", FakeFetch(blocked, ""))
        assert harvest.fetch_one(con, "2260623") == "blocked"
    monkeypatch.setattr(harvest, "fetch", FakeFetch(200, HTML, url="https://evil.example/PressReleasePage.aspx?PRID=1"))
    assert harvest.fetch_one(con, "2260624") == "miss"                  # a page that is not on PIB is never stored
    con.commit()
    assert "2260621" in harvest.known(con) and "2260622" in harvest.known(con) and "2260623" not in harvest.known(con)
