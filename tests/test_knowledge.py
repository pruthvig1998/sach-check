"""Reference store, question mode, news tier and social signal. Offline: no network, no real AI.
The rule under test throughout: none of these layers can produce or change TRUE, FALSE or MISLEADING."""
import json, re
from datetime import date
import pytest
from test_cache_trace import _fresh_store, FakeLLM, TS          # noqa: F401
from sach import news, refstore, verdict
from sach.models import Claim, Evidence, TIER_OFFICIAL, TIER_PIB, UNVERIFIED
from sach.pipeline import check_forward
from sach.site import result_block

DEATH = "Veteran actor Example Kumar passed away in Hyderabad today after a long illness."


def N(host, stance_word, n=1):
    return Evidence(host, f"https://www.{host}/story-{n}", news.TIER_NEWS, TS, f"{stance_word} actor Example Kumar", f"{stance_word} report about actor Example Kumar")


class NewsLLM(FakeLLM):
    """confirms a page whose title starts with CONFIRM, contradicts one that starts with DENY."""
    def stance(self, claim, title, text, tier=None):
        return "confirms" if title.startswith("CONFIRM") else "contradicts" if title.startswith("DENY") else "none"


class Run:
    status, providers = "ok", []
    def __init__(self, news_ran=True, social=()):
        self.news, self.social = news_ran, list(social)


class StatusRetriever:
    def __init__(self, ev, run=None):
        self.ev, self.run, self.calls = list(ev), run or Run(), 0
    def search(self, claim):
        return self.ev
    def search_with_status(self, claim):
        self.calls += 1
        return self.ev, self.run


def check(text, ev, run=None, **kw):
    r = StatusRetriever(ev, run)
    return check_forward(text, [r], NewsLLM(), **kw), r


# ---------------------------------------------------------------- reference store
def test_every_fact_is_dated_and_points_to_a_government_document():
    d = json.load(open(refstore._PATH, encoding="utf-8"))
    assert len(d["holidays"]) >= 90
    for f in d["holidays"]:
        y, m, dd = (int(x) for x in f["date"].split("-"))
        date(y, m, dd)                                                   # a real calendar date
        assert f["id"] in refstore.ALIASES or f["id"] in ("guru_ravidas_jayanti", "dayanand_jayanti", "jamat_ul_vida", "tagore_jayanti",
                                                          "parsi_new_year", "maha_ashtami", "maha_navami", "guru_teg_bahadur")
        assert re.match(r"https://[a-z.]+\.gov\.in/", d["sources"][f["source"]]["url"])


def test_dates_copied_from_the_official_lists():
    get = lambda t: [(f["date"], f["weekday"]) for f in refstore.lookup(t)]
    assert get("When is Diwali in 2026?") == [("2026-11-08", "Sunday")]
    assert get("diwali 2027 date") == [("2027-10-29", "Friday")]
    assert get("దీపావళి 2026 ఎప్పుడు?") == [("2026-11-08", "Sunday")]
    assert get("होली 2027 कब है") == [("2027-03-23", "Tuesday")]
    assert get("Bakrid 2026") == [("2026-05-28", "Thursday")]            # the corrected date, with its note
    assert "28 May" in refstore.lookup("Bakrid 2026")[0]["note"]
    assert [f["date"][:4] for f in refstore.lookup("when is holi", date(2026, 11, 18))] == ["2026", "2027"]
    assert refstore.lookup("The scholi programme starts in 2026") == []  # 'holi' inside another word is not Holi


def test_only_short_questions_are_answered_by_the_store():
    assert refstore.answerable("When is Diwali in 2026?") and refstore.answerable("diwali date") and refstore.answerable("होली 2027 कब है")
    for claim in ("Rakhi Sawant passed away", "When did Rakhi Sawant die?", "Holi special train cancelled", "Onam bumper lottery winner announced",
                  "Diwali bonus of Rs 5000", "Is Christmas a holiday?", "Christmas Kumar arrested", "diwali", "When is the Diwali bank strike?"):
        assert not refstore.answerable(claim), claim                     # says more than "when is X": goes through the normal check
    assert not refstore.answerable("Did the actor Giri Babu pass away?")              # nothing in the store
    assert not refstore.answerable("Government will give Rs 5000 to every woman on Diwali 2026 under a new scheme, apply before the festival ends "
                                   "and share with every family group you know right now today")


def test_a_question_gets_an_answer_without_any_search_or_verdict():
    res, r = check("When is Diwali in 2026?", [])
    assert r.calls == 0 and res["answer"][0]["date"] == "2026-11-08" and res["no_claims"] and res["verdict"] == UNVERIFIED
    assert "Sunday, 8 November 2026" in res["card"] and "gov.in" in res["card"] and "TRUE" not in res["card"] and "FALSE" not in res["card"]
    html = result_block(res)
    assert "ANSWER" in html and "8 November 2026" in html and "No claim" not in html


def test_the_answer_comes_before_the_cache():
    from sach import cache
    q = "When is Holi in 2027?"
    cache.save(q, None, {"verdict": "FALSE", "claims": [{"claim": {"text": q}}], "layer": "live", "_verdict_policy": 1})
    res, _ = check(q, [])
    assert res.get("answer") and res["verdict"] == UNVERIFIED


def test_the_store_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SACH_REFSTORE", "0")
    assert refstore.lookup("When is Diwali in 2026?") == [] and not refstore.answerable("When is Diwali in 2026?")


def test_a_statement_keeps_its_normal_result_and_gains_only_a_dates_panel():
    text = "Government has declared a five day bank holiday for Diwali 2026 across the country."
    res, _ = check(text, [])
    assert res["verdict"] == UNVERIFIED and not res.get("answer") and res["reference"][0]["id"] == "diwali"
    assert "Official dates" in result_block(res)
    for name_not_festival in ("Rakhi Sawant passed away in Mumbai this morning", "Vishu Reddy wins the election in Kerala today",
                              "Christmas Kumar was arrested by the police yesterday", "Holi special train cancelled by the Railways"):
        r2, _ = check(name_not_festival, [])
        assert "reference" not in r2, name_not_festival                 # a festival word that is a name, or no date talk: no dates panel


def test_past_dates_are_marked():
    from datetime import date as _d
    assert refstore.fmt_date("2026-11-08", _d(2026, 11, 18)).endswith("(already passed)")
    assert "passed" not in refstore.fmt_date("2027-10-29", _d(2026, 11, 18))


# ---------------------------------------------------------------- news tier: rules
def test_news_evidence_can_never_decide_a_verdict():
    c = Claim(DEATH)
    for st in ("confirms", "contradicts", "mixed"):
        ev = [N("thehindu.com", "CONFIRM"), N("ndtv.com", "CONFIRM", 2), N("ptinews.com", "CONFIRM", 3)]
        for e in ev:
            e.stance = st
        v = verdict.decide(c, ev)
        assert v.verdict == UNVERIFIED and v.reason_code == "no_evidence" and v.citations == []


def _ev(*pairs):
    out = []
    for i, (host, st) in enumerate(pairs):
        e = N(host, "X", i); e.stance = st
        out.append(e)
    return out


def test_reported_needs_two_independent_owners():
    claim = "Example Motors has launched a new electric scooter in Hyderabad this week."
    assert news.assess(claim, _ev(("thehindu.com", "confirms"), ("ndtv.com", "confirms")), True)["status"] == "reported"
    same_owner = _ev(("timesofindia.indiatimes.com", "confirms"), ("economictimes.indiatimes.com", "confirms"))
    assert news.assess(claim, same_owner, True)["status"] == "single_report"
    assert news.assess(claim, _ev(("thehindu.com", "confirms")), True)["status"] == "single_report"
    assert news.assess(claim, [], True) is None                          # not an event that silence says anything about


def test_a_death_needs_three_owners_or_a_news_agency():
    assert news.assess(DEATH, _ev(("thehindu.com", "confirms"), ("ndtv.com", "confirms")), True)["status"] == "single_report"
    assert news.assess(DEATH, _ev(("thehindu.com", "confirms"), ("ndtv.com", "confirms"), ("eenadu.net", "confirms")), True)["status"] == "reported"
    assert news.assess(DEATH, _ev(("ptinews.com", "confirms"), ("ndtv.com", "confirms")), True)["status"] == "reported"


def test_denials_conflicts_and_silence():
    assert news.assess(DEATH, _ev(("thehindu.com", "contradicts"), ("ndtv.com", "contradicts")), True)["status"] == "denied"
    assert news.assess(DEATH, _ev(("thehindu.com", "confirms"), ("ndtv.com", "contradicts")), True)["status"] == "conflicting"
    assert news.assess(DEATH, [], True)["status"] == "no_reliable_report"
    assert news.assess(DEATH, [], False) is None                         # the news search did not run or failed: silence means nothing
    for not_recent in ("Mahatma Gandhi died in 1948", "Actor Example Kumar killed it at the box office", "This phone is a rip off, buy the other one",
                       "There is no more time to submit the form", "Mobile phones will be banned in schools from next month",
                       "Free crash course for students this Sunday", "वह मौतों का सौदागर है", "मृत्युंजय नाम का लड़का जीता"):
        assert news.assess(not_recent, [], True) is None, not_recent      # silence says nothing about these
    official = Evidence("x", "https://example.gov.in/a", TIER_OFFICIAL, TS, "t", "t"); official.stance = "confirms"
    unlisted = Evidence("x", "https://random-blog.example/a", news.TIER_NEWS, TS, "t", "t"); unlisted.stance = "confirms"
    assert news.assess("Example Motors has launched a scooter this week.", [official, unlisted], True) is None    # only listed outlets count


# ---------------------------------------------------------------- news tier: through the pipeline
def test_pipeline_shows_reported_but_the_verdict_stays_unverified():
    ev = [N("ptinews.com", "CONFIRM"), N("thehindu.com", "CONFIRM", 2)]
    res, _ = check(DEATH, ev)
    c = res["claims"][0]
    assert res["verdict"] == UNVERIFIED and c["verdict"] == UNVERIFIED and c["reason_code"] == "no_evidence" and c["citations"] == []
    assert c["trace"]["reported"]["status"] == "reported" and {o["source"] for o in c["trace"]["reported"]["outlets"]} == {"PTI", "The Hindu"}
    assert "REPORTED by news outlets: PTI, The Hindu" in res["card"] and "TRUE" not in res["card"]
    html = result_block(res, text=DEATH)
    assert "REPORTED by news outlets" in html and "not an official confirmation" in html


def test_pipeline_death_hoax_is_shown_as_denied_never_false():
    res, _ = check(DEATH, [N("ptinews.com", "DENY"), N("ndtv.com", "DENY", 2)])
    assert res["verdict"] == UNVERIFIED and res["claims"][0]["trace"]["reported"]["status"] == "denied"
    assert "NOT true" in res["card"] and "FALSE" not in res["card"]


def test_an_official_source_still_decides_and_news_adds_nothing():
    off = Evidence("Ministry", "https://example.gov.in/note", TIER_OFFICIAL, TS, "CONFIRM official note", "CONFIRM official note")
    res, _ = check(DEATH, [off, N("ptinews.com", "DENY"), N("ndtv.com", "DENY", 2)])
    assert res["verdict"] == "TRUE" and "reported" not in res["claims"][0]["trace"] and "📰" not in res["card"]


def test_no_report_only_when_the_news_search_really_ran():
    res, _ = check(DEATH, [], Run(news_ran=True))
    assert res["claims"][0]["trace"]["reported"]["status"] == "no_reliable_report"
    res2, _ = check(DEATH + " ", [], Run(news_ran=False), use_cache=False)
    assert "reported" not in res2["claims"][0]["trace"]


# ---------------------------------------------------------------- switches and the retriever
def test_both_layers_are_off_by_default_and_the_retriever_then_sends_no_extra_query(monkeypatch):
    from sach.retrieve import BraveRetriever
    monkeypatch.delenv("SACH_NEWS_TIER", raising=False); monkeypatch.delenv("SACH_SOCIAL_SIGNAL", raising=False)
    assert not news.news_enabled() and not news.social_enabled()
    seen = []
    class Chain:
        configured = True
        def new_run(self): return Run(news_ran=False)
        def search(self, q, count, run=None):
            seen.append(q); return []
    r = BraveRetriever(key="k", chain=Chain())
    ev, run = r.search_with_status(DEATH)
    assert ev == [] and not run.news and not any("news" in q.split()[-1:] or "x.com" in q for q in seen)
    monkeypatch.setenv("SACH_NEWS_TIER", "1"); monkeypatch.setenv("SACH_SOCIAL_SIGNAL", "1")
    seen.clear()
    ev, run = r.search_with_status(DEATH)
    assert run.news is True and any("site:x.com" in q for q in seen)
    newsq = [q for q in seen if "site:ptinews.com" in q]
    from sach.search import grounded_accepts
    assert len(newsq) == 1 and not grounded_accepts(newsq[0])        # the grounded provider returns only official pages, so it must be skipped


def test_the_news_query_only_keeps_listed_outlets_and_official_pages(monkeypatch):
    from sach import retrieve
    r = retrieve.BraveRetriever(key="k", chain=type("C", (), {"configured": True})())
    pages = ("https://www.thehindu.com/a", "https://random-blog.example/a", "https://newsonair.gov.in/a",
             "https://pib.gov.in/PressReleasePage.aspx?PRID=999", "https://www.indiatoday.in/fact-check/story/x", "https://www.ptinews.com/factcheck/x")
    monkeypatch.setattr(retrieve, "fetch", lambda u: {"status": 200, "final_url": u, "body": "<title>Fake claim</title><p>text</p>", "fetched_at": TS})
    tiers = {u: getattr(r._evidence(u, news.TIER_NEWS), "tier", None) for u in pages}
    # the news query can only yield news-tier evidence: an official or fact-checker page found by it is dropped, so it opens no route to a verdict or a citation
    # the public broadcaster (newsonair.gov.in) is a NEWS report here: it can make a claim REPORTED but never TRUE through this search
    assert tiers == {pages[0]: "news", pages[1]: None, pages[2]: "news", pages[3]: None, pages[4]: None, pages[5]: None}
    assert news.group_of(pages[2]) == "All India Radio" and "All India Radio" in news.WIRES
    assert r._evidence("https://www.thehindu.com/a", TIER_OFFICIAL) is None      # a news page can never arrive as official


# ---------------------------------------------------------------- social signal
def test_social_signal_counts_posts_names_established_accounts_and_is_only_shown_as_a_signal():
    urls = ["https://x.com/PTI_News/status/1", "https://x.com/someone/status/2", "https://www.facebook.com/somepage/posts/3",
            "https://www.instagram.com/p/abc/", "https://x.com/hashtag/rip", "https://example.com/not-social"]
    s = news.social_signal(urls)
    assert s == {"posts": 5, "platforms": {"X": 3, "Facebook": 1, "Instagram": 1}, "established_accounts": ["PTI"]}
    assert news.social_signal([]) is None
    res, _ = check(DEATH, [], Run(news_ran=False, social=urls))
    assert res["verdict"] == UNVERIFIED and res["claims"][0]["trace"]["social"]["posts"] == 5
    html = result_block(res, text=DEATH)
    assert "Posts on social media" in html and "they are not evidence" in html


def test_panels_escape_everything_they_show():
    res = {"verdict": UNVERIFIED, "layer": "live", "language": "en",
           "claims": [{"trace": {"reported": {"status": "reported", "outlets": [{"source": "<script>x</script>", "url": "https://a.example/\"><b>", "says": "<i>"}]},
                                 "social": {"posts": 1, "platforms": {"<b>X": 1}, "established_accounts": ["<u>"]}}}]}
    html = news.panels_html(res)
    assert "<script>" not in html and "<b>X" not in html and "<u>" not in html and "<i>" not in html


def test_no_em_dash_in_new_strings():
    import inspect
    assert chr(8212) not in inspect.getsource(news) and chr(8212) not in inspect.getsource(refstore)
    assert chr(8212) not in open(refstore._PATH, encoding="utf-8").read()


# ---------------------------------------------------------------- related published fact-checks (offline corpus) and official alerts
def _corpus(tmp_path, rows):
    import sqlite3
    from sach import crcorpus
    from sach.pibfts import _MARKS
    p = str(tmp_path / "cr.sqlite")
    con = sqlite3.connect(p); con.executescript(crcorpus.SCHEMA % _MARKS)
    con.executemany("insert into reviews(url, claim, rating, publisher, date) values (?,?,?,?,?)", rows); con.commit(); con.close()
    return p


def test_related_fact_checks_need_the_same_words_and_numbers_and_show_no_rating(tmp_path):
    from sach import crcorpus
    p = _corpus(tmp_path, [("https://factly.in/a", "Government will give Rs 5000 to every woman under a new scheme", "False", "FACTLY", "2026-01-02"),
                           ("https://factly.in/b", "Video shows a pilot of Air India flight that crashed in Ahmedabad speaking to his mother", "False", "FACTLY", "2026-01-03"),
                           ("http://factly.in/c", "Plain http link is never shown for this exact claim text here", "False", "FACTLY", "2026-01-04")])
    hit = crcorpus.search("GOVERNMENT will give Rs 5,000 to every woman under a new scheme!", path=p)
    assert [h["url"] for h in hit] == ["https://factly.in/a"] and "rating" not in hit[0]              # their rating word is never carried
    assert crcorpus.search("Government will give Rs 50000 to every woman under a new scheme", path=p) == []      # a different amount
    assert crcorpus.search("Video shows a pilot of Air India flight that crashed in Kerala speaking to his mother", path=p) == []   # another place
    assert crcorpus.search("Government will give Rs 5000 to every man under a new scheme", path=p) == []         # one key word differs
    assert crcorpus.search("Government will not give Rs 5000 to every woman under a new scheme", path=p) == []   # the opposite statement
    assert crcorpus.search("Government will give Rs 5000.50 to every woman under a new scheme", path=p) == []    # a decimal is one number
    assert crcorpus.search("Government will give Rs 5000 to every woman under an old scheme", path=p) == []      # short and common words count too
    assert crcorpus.search("Plain http link is never shown for this exact claim text here", path=p) == []
    assert crcorpus.search("anything at all", path=str(tmp_path / "missing.sqlite")) == []


def test_the_shipped_corpus_holds_only_listed_indian_fact_checkers():
    import sqlite3, time
    from sach import crcorpus
    from sach.fetch import is_factchecker
    con = sqlite3.connect(crcorpus.DB_PATH)
    rows = con.execute("select url, claim, rating, date from reviews").fetchall()
    assert len(rows) > 5000
    today = time.strftime("%Y-%m-%d", time.gmtime())
    for url, claim, rating, date in rows:
        assert url.startswith("https://") and is_factchecker(url) and claim and rating and "2023-01-01" <= date <= today
        assert not url.split("/")[2].startswith(("srilanka.", "cambodia.", "thailand."))


NOW = 1794853400.0                       # 16 Nov 2026, about 18:23 GMT
FEED_XML = """<rss><channel>
<item><title>IMD Guwahati has issued forecast for Thunderstorm with Lightning which is very likely to occur at a few places over Kamrup and Kamrup Metropolitan in next 3 hours. Issued in Public Interest by ASDMA.</title>
<link>https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier=1</link><pubDate>Mon, 16 Nov 2026 17:42:52 GMT</pubDate></item>
<item><title>Heavy rain very likely over Chennai in next 3 hours.</title><link>https://sachet.ndma.gov.in/x?identifier=2</link><pubDate>Thu, 05 Nov 2026 10:35:27 GMT</pubDate></item>
<item><title>Very High Forest Fire Risk reported by Disaster Management Department</title><link>https://sachet.ndma.gov.in/x?identifier=3</link><pubDate>Mon, 16 Nov 2026 17:00:00 GMT</pubDate></item>
<item><title>Evil alert over Kamrup</title><link>https://evil.example/x</link><pubDate>Mon, 16 Nov 2026 17:42:52 GMT</pubDate></item>
</channel></rss>"""


def test_alerts_need_the_same_hazard_the_same_place_and_a_recent_issue_time():
    from sach import alerts
    import os
    os.environ["SACH_ALERTS"] = "1"
    items = alerts.parse(FEED_XML)
    assert len(items) == 3 and all(i["url"].startswith("https://sachet.ndma.gov.in/") for i in items)   # a link off the SACHET host is dropped
    rel = lambda text: [a["url"][-1] for a in alerts.related(text, items=items, now=NOW)]
    assert rel("Thunderstorm warning for Kamrup tonight, stay indoors") == ["1"]
    for wrong in ("Heavy rain: schools closed in Mumbai tomorrow",                 # another place
                  "Earthquake tremors felt in Kamrup this evening",                # another kind of hazard
                  "Heavy rain in Chennai, all schools closed tomorrow",            # that alert is eleven days old
                  "Storm damages houses, video from Guwahati",                     # Guwahati is the issuing office, not the area
                  "Hyderabad heavy rain, Department says roads closed",            # a common capitalised word is not a place
                  "Train derailed in Kamrup, passengers safe",                     # "Train" is not rain
                  "Brainstorm session on the Kamrup budget",                       # "Brainstorm" is not a storm
                  "Kamrup collector announces new ration scheme"):                 # no hazard at all
        assert rel(wrong) == [], wrong
    assert alerts.parse("<not xml") == []
    del os.environ["SACH_ALERTS"]
    assert alerts.related("Thunderstorm warning for Kamrup tonight, stay indoors", items=items, now=NOW) == []      # off by default


def test_alerts_and_related_fact_checks_are_show_only_and_alerts_expire(monkeypatch):
    import time
    from sach import alerts, crcorpus
    monkeypatch.setattr(crcorpus, "search", lambda q, **k: [{"claim": "<b>c</b>", "publisher": "FACTLY", "url": "https://factly.in/a", "date": "2026-01-02"}])
    monkeypatch.setattr(alerts, "related", lambda t, **k: [{"title": "Alert over <i>Kamrup</i>", "url": "https://sachet.ndma.gov.in/x", "published": "now"}])
    assert not alerts.enabled()                                       # opt-in
    monkeypatch.setenv("SACH_ALERTS", "1")
    res, _ = check("Cyclone will hit Kamrup district tomorrow and all schools are closed.", [], use_cache=False)
    c = res["claims"][0]
    assert res["verdict"] == UNVERIFIED and c["reason_code"] == "no_evidence" and c["citations"] == [] and "FACTLY" not in res["card"]
    html = result_block(res, text="x")
    assert "A published fact-check of this claim" in html and "Recent official alerts" in html and "<b>c</b>" not in html and "<i>Kamrup" not in html
    assert "False" not in html.split("related-fc")[1].split("</section>")[0]                         # no rating word in that panel
    old = {**res, "alerts": {**res["alerts"], "at": int(time.time()) - 4 * 3600}}                     # the same result served from a cache or a share link later
    assert "Recent official alerts" not in result_block(old, text="x")
    junk = {**res, "alerts": ["x"], "related_factchecks": ["y", 3]}                                   # malformed stored values never break the page
    assert "result" in result_block(junk, text="x")
    off = Evidence("Ministry", "https://example.gov.in/note", TIER_OFFICIAL, TS, "CONFIRM official note", "CONFIRM official note")
    res2, _ = check("Cyclone will hit Kamrup district tomorrow and all the schools are closed.", [off], use_cache=False)
    assert res2["verdict"] == "TRUE" and "related_factchecks" not in res2 and "alerts" not in res2                 # only under UNVERIFIED


def test_telegram_busy_reply_lists_related_pib_pages_but_never_a_verdict(monkeypatch):
    from sach import limits
    monkeypatch.setattr(limits, "related_pages", lambda text, n=3: [{"title": "PIB release on a scheme", "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=1"}])
    msg = limits.busy_text("day", "Government will give Rs 5000 to every woman")
    assert "PRID=1" in msg and "not a verdict" in msg and not any(w in msg for w in ("TRUE", "FALSE", "MISLEADING"))
    assert "PRID=1" not in limits.busy_text("flight", "Government will give Rs 5000 to every woman")     # being checked right now: no extras
    assert "PRID=1" not in limits.busy_text("day")                                                        # old call shape still works


def test_panels_never_raise_on_malformed_stored_values_and_link_only_https():
    base = {"verdict": UNVERIFIED, "layer": "live", "language": "en", "claims": []}
    for junk in (5, True, 1.5, "x", ["x", 3, None], {"at": 9e18, "items": 7}, {"items": "x"}, None):
        for key in ("alerts", "related_factchecks", "reference"):
            assert isinstance(news.panels_html({**base, key: junk}), str)
    assert isinstance(news.panels_html({**base, "claims": [{"trace": 5}, "x", None]}), str)
    assert isinstance(news.panels_html({**base, "language": ["en"]}), str)
    rep = {"status": "reported", "outlets": [{"source": "A", "url": "http://plain.example/x"}, {"source": "B", "url": "https://ok.example/y"}, "junk"]}
    html = news.panels_html({**base, "claims": [{"trace": {"reported": rep}}]})
    assert "https://ok.example/y" in html and "http://plain.example" not in html


def test_the_shipped_corpus_names_sites_never_people_or_rating_words():
    import sqlite3
    from sach import crcorpus
    pubs = [r[0] for r in sqlite3.connect(crcorpus.DB_PATH).execute("select distinct publisher from reviews")]
    assert pubs and all(re.fullmatch(r"[a-z0-9.\-]+\.[a-z]{2,}", p) for p in pubs), pubs[:5]


def test_the_news_search_runs_even_when_the_official_search_found_an_unrelated_page(monkeypatch):
    from sach import retrieve
    monkeypatch.setenv("SACH_NEWS_TIER", "1")
    seen = []
    class Chain:
        configured = True
        def new_run(self): return Run(news_ran=False)
        def search(self, q, count, run=None):
            seen.append(q)
            return ["https://example.gov.in/unrelated.pdf"] if "site:gov.in" in q else []
    monkeypatch.setattr(retrieve, "fetch", lambda u: {"status": 200, "final_url": u, "body": "<title>Fauna</title><p>unrelated</p>", "fetched_at": TS})
    ev, run = retrieve.BraveRetriever(key="k", chain=Chain()).search_with_status(DEATH)
    assert any(e.tier == TIER_OFFICIAL for e in ev)                        # an official page was found (unrelated, not yet judged)
    assert run.news is True and any("site:ptinews.com" in q for q in seen)   # and the news search still ran


def test_news_pages_found_but_not_confirmed_are_not_silence():
    assert news.assess(DEATH, _ev(("thehindu.com", "none"), ("ndtv.com", "none")), True) is None       # pages exist: never "no reliable report"
    assert news.assess(DEATH, [], True)["status"] == "no_reliable_report"                                # nothing found at all


def test_the_overlap_rule_can_second_a_news_report_but_never_reaches_a_verdict():
    from sach.stance import heuristic_stance
    claim = "Veteran Telugu actor Example Kumar passed away in Hyderabad"
    title, text = "Veteran Telugu actor Example Kumar dies at 80", "Veteran Telugu actor Example Kumar passed away in Hyderabad on Monday after a brief illness."
    assert heuristic_stance(claim, title, text, "news") == "confirms" and heuristic_stance(claim, title, text, "official") == "confirms"
    assert heuristic_stance(claim, title, text, "factchecker") == "none"
    assert heuristic_stance(claim, "Example Kumar is alive, death rumours are fake", "Example Kumar is alive, rumours fake", "news") == "none"
    e = Evidence("thehindu.com", "https://www.thehindu.com/x", news.TIER_NEWS, TS, title, text); e.stance = "confirms"
    assert verdict.decide(Claim(claim), [e]).verdict == UNVERIFIED
