"""No live web: retrievers are replaced by recorded fixtures."""
import pytest
from sach.models import *
from sach.extract import extract_claims
from sach.lang import detect_language
from sach.verdict import decide, aggregate
from sach.stance import heuristic_stance
from sach.pipeline import check_forward
from sach.card import render_card
from sach.i18n import LABEL, WHY
from sach.fetch import is_official, is_factchecker
from sach.pib import parse_rss, parse_release

TS = "2026-11-12T10:00:00+00:00"
C = Claim("Government will give Rs 5000 to every woman under PM Mahila Yojana")

def ev(tier, stance, url="https://pib.gov.in/x", name="PIB"):
    return Evidence(name, url, tier, TS, "t", "txt", stance)

# --- claim extraction
def test_extract_splits_and_drops_boilerplate():
    f = "PM Kisan: farmers get Rs 6000 per year.\nPlease forward to all groups!!\nDrinking hot water cures cancer."
    cs = extract_claims(f)
    assert [c.domain for c in cs] == ["scheme", "health"]
    assert all("forward" not in c.text.lower() for c in cs)

def test_extract_hindi_telugu_split_on_danda():
    assert len(extract_claims("सरकार हर महिला को 5000 रुपये देगी। यह योजना कल बंद हो जाएगी।")) == 2
    assert extract_claims("ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది. ఈ పథకం రేపు ముగుస్తుంది.")[0].domain == "scheme"

# --- verdict rules (the hard ones)
def test_false_requires_official_contradiction():
    assert decide(C, [ev(TIER_PIB, "contradicts")]).verdict == FALSE
    assert decide(C, [ev(TIER_OFFICIAL, "contradicts")]).verdict == FALSE

def test_absence_of_evidence_is_unverified_never_false():
    assert decide(C, []).verdict == UNVERIFIED
    assert decide(C, [ev(TIER_OFFICIAL, "none")]).verdict == UNVERIFIED

def test_factchecker_alone_never_gives_false_or_true():
    for stance in ("contradicts", "confirms", "mixed"):
        v = decide(C, [ev(TIER_FACTCHECKER, stance, "https://www.altnews.in/a", "Alt News")])
        assert v.verdict == UNVERIFIED and v.reason_code == "factchecker_only"
        assert v.citations[0]["tier"] == TIER_FACTCHECKER   # labelled, not dressed up as official

def test_conflicting_official_sources_unverified():
    assert decide(C, [ev(TIER_PIB, "contradicts"), ev(TIER_OFFICIAL, "confirms", "https://a.gov.in")]).verdict == UNVERIFIED

def test_true_and_misleading():
    assert decide(C, [ev(TIER_OFFICIAL, "confirms")]).verdict == TRUE
    assert decide(C, [ev(TIER_OFFICIAL, "mixed")]).verdict == MISLEADING

def test_aggregate_priority():
    mk = lambda v: ClaimVerdict(C, v, "x")
    assert aggregate([mk(TRUE), mk(FALSE)]) == FALSE
    assert aggregate([mk(TRUE), mk(MISLEADING)]) == MISLEADING
    assert aggregate([mk(TRUE), mk(UNVERIFIED)]) == UNVERIFIED
    assert aggregate([mk(TRUE)]) == TRUE
    assert aggregate([]) == UNVERIFIED

# --- citations
@pytest.mark.parametrize("stance,tier", [("contradicts", TIER_PIB), ("confirms", TIER_OFFICIAL), ("mixed", TIER_OFFICIAL)])
def test_every_non_unverified_verdict_has_citation(stance, tier):
    v = decide(C, [ev(tier, stance)])
    assert v.citations and all(c["url"] and c["date_accessed"] and c["source"] for c in v.citations)

def test_unfetched_evidence_is_never_cited():
    e = ev(TIER_PIB, "contradicts"); e.fetched_at = ""
    assert decide(C, [e]).citations == []

# --- stance heuristic is conservative
def test_heuristic_stance():
    claim = "PM Mahila Yojana gives Rs 5000 to every woman"
    assert heuristic_stance(claim, "Fake: PM Mahila Yojana gives Rs 5000 to every woman", "", TIER_PIB) == "contradicts"
    assert heuristic_stance(claim, "Cabinet approves GST rate changes", "unrelated text about trade", TIER_PIB) == "none"
    assert heuristic_stance(claim, "PM Mahila Yojana", "gives Rs 2000 to every woman", TIER_OFFICIAL) == "mixed"

# --- language + cards
@pytest.mark.parametrize("text,lang", [
    ("Government will give free laptops to all students", "en"),
    ("सरकार हर महिला को 5000 रुपये देगी, जल्दी शेयर करें", "hi"),
    ("ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది", "te"),
    ("sarkar sabko free paisa degi yeh yojana kal band ho jayegi jaldi bhejo", "hi")])
def test_language_detection(text, lang):
    assert detect_language(text) == lang

CITE = [{"source": "PIB", "url": "https://pib.gov.in/x", "tier": TIER_PIB, "date_accessed": "2026-11-12", "fetched_at": TS}]

@pytest.mark.parametrize("lang", ["en", "hi", "te"])
@pytest.mark.parametrize("verdict", [TRUE, FALSE, MISLEADING, UNVERIFIED])
def test_card_verdict_first_and_in_language(lang, verdict):
    card = render_card(verdict, lang, CITE)
    first = card.splitlines()[0]
    assert LABEL[lang][verdict] in first
    if verdict != UNVERIFIED:
        assert "https://pib.gov.in/x" in card
    if lang != "en":
        assert not any(w in card for w in ("FALSE", "TRUE", "claim"))

def test_templates_complete_and_short():
    for lang in WHY:
        assert set(WHY[lang]) == {TRUE, FALSE, MISLEADING, UNVERIFIED}
        assert all(len(s) < 160 for s in WHY[lang].values())

class FakeRetriever:
    def __init__(self, ev): self.ev = ev
    def search(self, claim): return [Evidence(e.source_name, e.url, e.tier, e.fetched_at, e.title, e.text) for e in self.ev]

def test_pipeline_reply_language_matches_input_and_logs_ledger():
    from sach import ledger
    pib = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
                   "Fake claim: government will give Rs 5000 to every woman",
                   "Fake message claims government will give Rs 5000 to every woman")
    res = check_forward("सरकार हर महिला को 5000 रुपये देगी, जल्दी शेयर करें।", [FakeRetriever([pib])])
    assert res["language"] == "hi"
    # heuristic stance cannot match Devanagari claim to English page -> stays honest
    assert res["verdict"] == UNVERIFIED
    res2 = check_forward("Government will give Rs 5000 to every woman. Please forward to all groups!", [FakeRetriever([pib])])
    assert res2["verdict"] == FALSE and "https://pib.gov.in/PressReleasePage.aspx?PRID=1" in res2["card"]
    assert len(ledger.load()) >= 2 and all("citations" in r for r in ledger.load())

# --- domains + parsers
def test_domain_classification():
    assert is_official("https://pib.gov.in/x") and is_official("https://www.mohfw.gov.in/a") and is_official("https://www.who.int/b")
    assert not is_official("https://gov.in.evil.com/") and not is_official("https://evilgov.in/")
    assert is_factchecker("https://www.boomlive.in/a") and not is_factchecker("https://boomlive.in.evil.com")

def test_rss_and_release_parsers():
    xml = "<rss><channel><item><title>A</title><link>https://pib.gov.in/PressReleaseIframePage.aspx?PRID=42</link></item></channel></rss>"
    assert parse_rss(xml) == [{"title": "A", "prid": "42"}]
    d = parse_release("<html><h2>Title X</h2><div id='PdfDiv'>Body text</div></html>")
    assert d["title"] == "Title X" and d["body"] == "Body text"

# --- regressions from the Day-1 data checkpoint (live PIB pages)
def test_summary_page_mentioning_misinformation_is_not_a_debunk():
    claim = "PIB Fact Check Unit has issued over 2,900 fact checks."
    title = "Government Counters Misinformation; PIB Fact-Check Unit Issues Over 2,900 Fact Checks"
    assert heuristic_stance(claim, title, "The unit debunked fake news...", TIER_OFFICIAL) != "contradicts"
    assert heuristic_stance(claim, title, "The unit debunked fake news...", TIER_PIB) != "contradicts"

def test_negated_claim_is_not_judged_against_a_debunk_title():
    t = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
    assert heuristic_stance("Government will not reduce retirement age of Central Government employees", t, "", TIER_PIB) == "none"
    assert heuristic_stance("Central Government will reduce retirement age of employees to 50", t, "", TIER_PIB) in ("contradicts", "none")

def test_llm_failure_falls_back_to_heuristic():
    from sach.stance import judge
    class Broken:
        def stance(self, *a): raise RuntimeError("401 invalid api key")
    e = Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: PM Mahila Yojana gives Rs 5000 to every woman", "")
    assert judge("PM Mahila Yojana gives Rs 5000 to every woman", e, Broken()) == "contradicts"

# --- Gemini judge (no live calls)
def test_parse_label_maps_and_defaults_to_none():
    from sach.llm import parse_label
    assert parse_label("CONTRADICTS") == "contradicts" and parse_label("confirms.") == "confirms"
    assert parse_label("**PARTIAL**") == "mixed" and parse_label("NEITHER") == "none"
    assert parse_label("") == "none" and parse_label("The page seems to say it is false") == "none"

def test_gemini_judge_skips_dead_models_and_needs_second_opinion(monkeypatch):
    import urllib.error, sach.llm as L
    tried = []
    def fake_post(self, model, body):
        tried.append(model)
        if model == "old":
            raise urllib.error.HTTPError("u", 404, "retired", {}, None)
        if model == "busy":
            raise urllib.error.HTTPError("u", 503, "overloaded", {}, None)
        return {"candidates": [{"content": {"parts": [{"text": "CONTRADICTS | Fake: the scheme claim is a hoax"}]}}]}
    monkeypatch.setattr(L.GeminiJudge, "_post", fake_post)
    j = L.GeminiJudge(key="k", model="old,busy,good,good2")
    assert j.stance("the scheme claim", "t", "Fake: the scheme claim is a hoax, says ministry") == "contradicts"
    assert tried == ["old", "busy", "good", "old", "busy", "good2"][:len(tried)] and tried[2] == "good" and "good2" in tried

def test_decisive_stance_needs_a_second_model_to_agree(monkeypatch):
    import sach.llm as L
    page = "Fake: the scheme claim is a hoax, says ministry"
    def make(replies):
        def fake_post(self, model, body):
            r = replies[model]
            if isinstance(r, Exception): raise r
            return {"candidates": [{"content": {"parts": [{"text": r}]}}]}
        return fake_post
    agree = {"a": "CONTRADICTS | Fake: the scheme claim is a hoax", "b": "CONTRADICTS | Fake: the scheme claim is a hoax"}
    monkeypatch.setattr(L.GeminiJudge, "_post", make(agree))
    assert L.GeminiJudge(key="k", model="a,b").stance("the scheme claim", "t", page) == "contradicts"
    split = {"a": "CONTRADICTS | Fake: the scheme claim is a hoax", "b": "NEITHER"}
    monkeypatch.setattr(L.GeminiJudge, "_post", make(split))
    assert L.GeminiJudge(key="k", model="a,b").stance("the scheme claim", "t", page) == "none"      # disagreement -> no verdict
    down = {"a": "CONTRADICTS | Fake: the scheme claim is a hoax", "b": OSError("down")}
    monkeypatch.setattr(L.GeminiJudge, "_post", make(down))
    assert L.GeminiJudge(key="k", model="a,b").stance("the scheme claim", "t", page) == "none"       # lone LLM guess, no backup -> no verdict
    title = "Fake: the scheme claim is a hoax"      # a clear PIB debunk is backed by the deterministic check
    assert L.GeminiJudge(key="k", model="a,b").stance("the scheme claim", title, page, tier="pib_debunk") == "contradicts"
    quiet = {"a": "NEITHER", "b": OSError("never called")}
    monkeypatch.setattr(L.GeminiJudge, "_post", make(quiet))
    assert L.GeminiJudge(key="k", model="a,b").stance("the scheme claim", "t", page) == "none"       # 'none' needs no second call

def test_gemini_failure_still_falls_back_safely(monkeypatch):
    import sach.llm as L
    from sach.stance import judge
    monkeypatch.setattr(L.GeminiJudge, "_post", lambda self, m, b: (_ for _ in ()).throw(OSError("down")))
    e = Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: PM Mahila Yojana gives Rs 5000 to every woman", "")
    assert judge("PM Mahila Yojana gives Rs 5000 to every woman", e, L.GeminiJudge(key="k")) == "contradicts"

def test_ledger_merges_seed_and_live(tmp_path, monkeypatch):
    import json, sach.ledger as L
    seed = tmp_path / "seed.json"; seed.write_text(json.dumps([{"claim": "seeded"}]))
    monkeypatch.setattr(L, "_SEED", str(seed))
    L.append({"claim": "live"})
    assert [r["claim"] for r in L.load()] == ["seeded", "live"]
    assert [r["claim"] for r in json.load(open(L.path()))] == ["live"]   # seed never written into live file

# --- web surface (imported + exercised, so syntax/routing breaks are caught)
def test_web_routes_work_with_query_and_any_post_path():
    import threading, urllib.request, urllib.parse
    from http.server import ThreadingHTTPServer
    from sach.web import Handler
    Handler.retrievers = [FakeRetriever([])]; Handler.llm = None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        get = lambda p: urllib.request.urlopen(f"http://127.0.0.1:{port}{p}").read().decode()
        assert "Evidence ledger" in get("/?view=ledger") and "checked claims" in get("/?view=ledger")
        assert get("/?view=health") == "ok"
        body = urllib.parse.urlencode({"text": "Drinking hot water cures cancer in three days."}).encode()
        out = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/index", body)).read().decode()
        assert "UNVERIFIED" in out
    finally:
        srv.shutdown()


# --- tightened judge: verbatim quote, number match, denial-only contradiction, confirm+mixed conflict
from sach.stance import validate_stance
from sach.llm import parse_reply

def test_parse_reply():
    assert parse_reply("CONTRADICTS | It is fake") == ("contradicts", "It is fake")
    assert parse_reply("NEITHER") == ("none", "")

def test_quote_must_be_verbatim_in_page():
    page = "The Ministry clarifies that the message about Rs 1000 is fake and fraudulent."
    assert validate_stance("contradicts", "message about Rs 1000 is fake and fraudulent", "Rs 1000 message", "t", page) == "contradicts"
    assert validate_stance("contradicts", "this is a totally invented sentence", "Rs 1000 message", "t", page) == "none"

def test_descriptive_scheme_page_cannot_contradict():
    page = "PM Surya Ghar Muft Bijli Yojana has crossed 10 lakh rooftop solar installations for households."
    assert validate_stance("contradicts", "10 lakh rooftop solar installations for households", "free solar refrigerator households", "t", page) == "none"

def test_confirms_needs_the_claims_numbers_in_the_quote():
    page = "43,230 recruitments done including Sub-Inspectors and Constable (RPF) in this fiscal."
    claim = "RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors."
    assert validate_stance("confirms", "Sub-Inspectors and Constable (RPF)", claim, "t", page) == "none"
    page2 = "RPF recruitment of 4,208 Constables and 452 Sub-Inspectors has been notified."
    assert validate_stance("confirms", "RPF recruitment of 4,208 Constables and 452 Sub-Inspectors has been notified", claim, "t", page2) == "confirms"

def test_confirm_plus_mixed_is_unverified_not_misleading():
    assert decide(C, [ev(TIER_OFFICIAL, "confirms"), ev(TIER_OFFICIAL, "mixed", "https://b.gov.in")]).verdict == UNVERIFIED
    assert decide(C, [ev(TIER_OFFICIAL, "mixed")]).verdict == MISLEADING   # mixed alone still works

def test_hung_retriever_and_judge_cannot_block_a_check(monkeypatch):
    import time, sach.pipeline as P
    monkeypatch.setattr(P, "RETRIEVE_DEADLINE_S", 0.3); monkeypatch.setattr(P, "JUDGE_DEADLINE_S", 0.3)
    class Hung:
        def search(self, c): time.sleep(5); return []
    class SlowJudge:
        def stance(self, *a): time.sleep(5); return "contradicts"
    t = time.time()
    res = check_forward("Government will give Rs 5000 to every woman.", [Hung()])
    assert res["verdict"] == UNVERIFIED and time.time() - t < 2
    ev = Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 5000 to every woman", "")
    res = check_forward("Government will give Rs 5000 to every woman.", [FakeRetriever([ev])], SlowJudge())
    assert time.time() - t < 4 and res["verdict"] in (UNVERIFIED, FALSE)


# --- website: content, safety, API, validation
import json as _json, threading as _th, urllib.request as _ur, urllib.parse as _up, urllib.error as _ue

@pytest.fixture
def server(monkeypatch):
    from http.server import ThreadingHTTPServer
    import sach.web as W
    W._hits.clear()
    ev = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
                  "Fake claim: government will give Rs 5000 to every woman", "Fake message claims government will give Rs 5000 to every woman")
    W.Handler.retrievers = [FakeRetriever([ev])]; W.Handler.llm = None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
    _th.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()

def _post(base, text, path="/", headers=None, raw=None):
    data = raw if raw is not None else _up.urlencode({"text": text}).encode()
    req = _ur.Request(base + path, data, headers or {})
    try:
        r = _ur.urlopen(req); return r.status, r.read().decode()
    except _ue.HTTPError as e:
        return e.code, e.read().decode()

def test_home_has_all_sections_and_features(server):
    h = _ur.urlopen(server + "/").read().decode()
    for needle in ("Got a forward?", 'id="check"', 'id="how"', 'id="rules"', 'id="sources"', 'id="evidence"', 'id="faq"', 'id="api"',
                   'id="theme"', 'id="paste"', 'id="count"', "Hinglish", "both mean", "truth", "MISLEADING", "prefers-color-scheme"):
        assert needle in h, needle
    assert h.count('class="chip"') == 5

def test_result_page_has_card_citation_and_actions(server):
    code, h = _post(server, "Government will give Rs 5000 to every woman.")
    assert code == 200 and 'id="result"' in h and "https://pib.gov.in/PressReleasePage.aspx?PRID=1" in h
    for needle in ("Copy card", "Share on WhatsApp", "Download image", "Report a wrong verdict", "https://wa.me/?text="):
        assert needle in h, needle

def test_user_text_is_html_escaped_no_xss(server):
    evil = '<script>alert(1)</script> "><img src=x onerror=alert(2)> Government will give Rs 5000 to every woman.'
    code, h = _post(server, evil)
    assert "<script>alert(1)" not in h and "<img src=x" not in h and "&lt;script&gt;alert(1)" in h

def test_ledger_page_escapes_and_filters(server):
    from sach import ledger
    ledger.append({"claim": "<b>x</b>", "domain": "other", "verdict": "FALSE", "reason_code": "r", "citations": [], "language": "en", "checked_at": TS})
    h = _ur.urlopen(server + "/?view=ledger").read().decode()
    assert "&lt;b&gt;x&lt;/b&gt;" in h and "<b>x</b>" not in h and 'data-v="FALSE"' in h and 'id="q"' in h

def test_empty_and_too_long_input_rejected_with_message(server):
    code, h = _post(server, "   ")
    assert code == 400 and "Please paste a message" in h
    code, h = _post(server, "a " * 5000)
    assert code == 413 and "too long" in h

def test_json_api(server):
    code, body = _post(server, "Government will give Rs 5000 to every woman.", "/?format=json")
    d = _json.loads(body)
    assert code == 200 and d["verdict"] == "FALSE" and d["claims"][0]["citations"][0]["url"].startswith("https://pib.gov.in")
    code, body = _post(server, "", "/?format=json", raw=_json.dumps({"text": "Government will give Rs 5000 to every woman."}).encode(),
                       headers={"Content-Type": "application/json"})
    assert code == 200 and _json.loads(body)["verdict"] == "FALSE"
    code, body = _post(server, "", "/?format=json", raw=b"not json", headers={"Content-Type": "application/json"})
    assert code == 400 and "error" in _json.loads(body)

def test_rate_limit_returns_429_not_crash(server):
    import sach.web as W
    codes = [_post(server, "Government will give Rs 5000 to every woman.", "/?format=json")[0] for _ in range(W.RATE_LIMIT + 2)]
    assert codes[: W.RATE_LIMIT] == [200] * W.RATE_LIMIT and codes[-1] == 429

def test_pipeline_exception_gives_friendly_500(server, monkeypatch):
    import sach.web as W
    monkeypatch.setattr(W, "check_forward", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    code, h = _post(server, "Government will give Rs 5000 to every woman.")
    assert code == 500 and "Something went wrong" in h and "boom" not in h and "Traceback" not in h

def test_head_healthz_and_security_headers(server):
    r = _ur.urlopen(_ur.Request(server + "/", method="HEAD")); assert r.status == 200
    r = _ur.urlopen(server + "/?view=health"); assert r.read() == b"ok" and r.headers["X-Content-Type-Options"] == "nosniff"

def test_hindi_and_telugu_text_roundtrip_in_page(server):
    code, h = _post(server, "सरकार हर महिला को 5000 रुपये देगी।")
    assert code == 200 and "झूठ" in h or "पुष्टि नहीं हुई" in h
    assert "सरकार हर महिला" in h          # prefill preserved so the user can edit and resubmit


def test_call_to_action_fragments_are_not_claims():
    cs = extract_claims("Government is giving Rs 1000 to everyone under Corona Sahayata Yojana. Click the link to register. Please forward to all groups!")
    assert [c.text for c in cs] == ["Government is giving Rs 1000 to everyone under Corona Sahayata Yojana."]
    assert len(extract_claims("The Cabinet approved a Rs 500 crore scheme to register small farmers for crop insurance cover.")) == 1   # long real claim survives


def test_cross_lingual_claims_are_translated_for_search_and_judging():
    seen = {}
    class Rec:
        def search(self, q):
            seen["q"] = q
            return [Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")]
    class TL:
        def translate(self, t): return "Government will give Rs 1000 to every woman"
        def stance(self, claim, title, text): return "contradicts" if "1000" in claim else "none"
    res = check_forward("సరకారు ప్రతి మహిళకు 1000 రూపాయలు ఇస్తుంది అని ప్రచారం జరుగుతోంది", [Rec()], TL())
    assert seen["q"] == "Government will give Rs 1000 to every woman"        # searched in English
    assert res["language"] == "te" and res["claims"][0]["claim"]["text"].startswith("సరకారు")   # ledger keeps the original wording
    assert "అబద్ధం" in res["card"]                                       # card still in Telugu

def test_translation_failure_falls_back_to_original_text():
    seen = {}
    class Rec:
        def search(self, q): seen["q"] = q; return []
    class Bad:
        def translate(self, t): raise RuntimeError("down")
        def stance(self, *a): return "none"
    txt = "సరకారు ప్రతి మహిళకు 1000 రూపాయలు ఇస్తుంది అని ప్రచారం జరుగుతోంది"
    res = check_forward(txt, [Rec()], Bad())
    assert seen["q"].startswith("సరకారు") and res["verdict"] == UNVERIFIED


@pytest.mark.parametrize("text,expected", [
    ("The Cabinet approved Rs. 37,500 crore for the scheme. Dr. Singh said it is good.", 2),
    ("కేంద్ర మంత్రివర్గం బొగ్గు గ్యాసిఫికేషన్ ప్రాజెక్టులకు రూ. 37,500 కోట్ల పథకాన్ని ఆమోదించింది.", 1),
    ("सरकार ने रु. 5000 हर महिला को देने की घोषणा की है।", 1),
    ("Govt. will give Rs. 1000 to every farmer. This scheme starts tomorrow for everyone.", 2)])
def test_abbreviation_dots_do_not_split_claims(text, expected):
    cs = extract_claims(text)
    assert len(cs) == expected
    assert any(("Rs." in c.text or "रु." in c.text or "రూ." in c.text) for c in cs)


# --- hardening from the awkward-input battery
def test_invisible_and_bidi_characters_are_stripped():
    from sach.extract import clean_text
    assert clean_text("\u202eGovernment will give Rs 5000\u200b to every woman\u0000 today") == "Government will give Rs 5000 to every woman today"
    assert clean_text("keep\nnewlines\tand tabs") == "keep\nnewlines\tand tabs"

@pytest.mark.parametrize("junk", ["🙏🙏🙏😂😂", "https://example.com/win", "1000 5000 2024", "Hello",
                                   "Good morning friends. Have a blessed day! Please forward to all groups."])
def test_non_claims_get_a_clear_no_claim_card_in_every_language(junk):
    res = check_forward(junk, [FakeRetriever([])])
    assert res.get("no_claims") and res["verdict"] == UNVERIFIED and res["claims"] == []
    assert "official source" not in res["card"]          # must not imply a search happened and failed

def test_no_claim_card_follows_language():
    res = check_forward("शुभ प्रभात! सबको शेयर करें 🙏", [FakeRetriever([])])
    assert res["language"] == "hi" and "दावा" in res["card"]

def test_partial_needs_strong_overlap_and_numbers_on_both_sides():
    claim = "Government will give Rs 5000 to every woman today"
    page = "JHARCRAFT supports handicraft artisans, with Rs 5000 grants for women artisans in Jharkhand textile units."
    q = "Rs 5000 grants for women artisans in Jharkhand textile units"
    assert validate_stance("mixed", q, claim, "JHARCRAFT", page) == "none"           # loose topical overlap: rejected
    page2 = "Government will give Rs 2000 to every woman under the scheme, the Ministry said."
    assert validate_stance("mixed", "Government will give Rs 2000 to every woman", claim, "t", page2) == "mixed"
    assert validate_stance("mixed", "Government will give money to every woman", claim, "t", "Government will give money to every woman") == "none"  # no number in quote

def test_multi_claim_forward_runs_in_parallel_within_budget(monkeypatch):
    import time, sach.pipeline as P
    class Slow:
        def search(self, q): time.sleep(1.0); return []
    monkeypatch.setattr(P, "BUDGET_S", 10)
    text = ". ".join(f"Government will give Rs {n}000 to every farmer in district number {n}" for n in range(1, 5)) + "."
    t = time.time(); res = check_forward(text, [Slow()]); dt = time.time() - t
    assert len(res["claims"]) == 4 and dt < 3.5          # 4 claims x 1 s, 3 workers: ~2 s, not 4 s

def test_overall_budget_turns_unfinished_claims_into_unverified_timed_out(monkeypatch):
    import time, sach.pipeline as P
    from sach import ledger
    class Hang:
        def search(self, q): time.sleep(20); return []
    monkeypatch.setattr(P, "BUDGET_S", 1.0)
    t = time.time(); res = check_forward("Government will give Rs 5000 to every woman in the country.", [Hang()]); dt = time.time() - t
    assert dt < 6 and res["verdict"] == UNVERIFIED
    assert not any(r["reason_code"] == "timed_out" for r in ledger.load() if "reason_code" in r)


def test_brave_requests_are_throttled_and_429_retried(monkeypatch):
    import io, json as j, urllib.error, sach.retrieve as R
    stamps, calls = [], []
    monkeypatch.setattr(R, "BRAVE_MIN_INTERVAL_S", 0.2); R._brave_last[0] = 0.0
    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def fake_open(req, timeout=0):
        import time; stamps.append(time.monotonic()); calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("u", 429, "slow down", {}, None)
        return Resp(j.dumps({"web": {"results": [{"url": "https://pib.gov.in/a"}]}}).encode())
    monkeypatch.setattr(R.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(R._time, "sleep", lambda s: None)
    assert R.BraveRetriever(key="k")._search("q") == ["https://pib.gov.in/a"] and len(calls) == 2


# --- Tinglish (Telugu in English letters)
@pytest.mark.parametrize("text", [
    "Prabhutvam andariki Corona Sahayata Yojana kinda Rs 1000 istundi. Link click chesi register cheskondi.",
    "Central sarkaru employees retirement age ni 50 years ki taggistundi ani message vachindi",
    "Pension ledu ani cheppaaru kani nijam kaadu"])
def test_tinglish_detected(text):
    assert detect_language(text) == "tl"

@pytest.mark.parametrize("text,lang", [
    ("Government will give free laptops to all students", "en"),
    ("Please check this message and tell me what you think of it", "en"),
    ("sarkar sabko free paisa degi yeh yojana kal band ho jayegi jaldi bhejo", "hi"),
    ("ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది", "te")])
def test_tinglish_does_not_hijack_other_languages(text, lang):
    assert detect_language(text) == lang

@pytest.mark.parametrize("verdict", [TRUE, FALSE, MISLEADING, UNVERIFIED])
def test_tinglish_card_is_latin_script_and_verdict_first(verdict):
    card = render_card(verdict, "tl", CITE)
    first = card.splitlines()[0]
    assert LABEL["tl"][verdict] in first
    assert not any("\u0C00" <= ch <= "\u0C7F" or "\u0900" <= ch <= "\u097F" for ch in card)   # Latin script only
    assert "FALSE" not in card and "TRUE" not in card.replace("TRUE", "", 0) or verdict == TRUE
    if verdict != UNVERIFIED:
        assert "https://pib.gov.in/x" in card

def test_tinglish_forward_gets_tinglish_card_and_is_searched_in_english():
    seen = {}
    class Rec:
        def search(self, q):
            seen["q"] = q
            return [Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")]
    class TL:
        def translate(self, t): return "Government will give Rs 1000 to every woman"
        def stance(self, claim, title, text): return "contradicts" if "1000" in claim else "none"
    res = check_forward("Prabhutvam prathi mahilaku Rs 1000 istundi ani message vachindi, andariki share cheyandi", [Rec()], TL())
    assert res["language"] == "tl" and seen["q"] == "Government will give Rs 1000 to every woman"
    assert res["card"].splitlines()[0].endswith("ABADDHAM") and "prakaaram" in res["card"]


# --- "what it means in English"
def test_non_english_result_carries_english_card_and_claim_meaning():
    class Rec:
        def search(self, q): return [Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")]
    class TL:
        def translate(self, t): return "Government will give Rs 1000 to every woman"
        def stance(self, claim, title, text): return "contradicts"
    res = check_forward("ప్రభుత్వం ప్రతి మహిళకు 1000 రూపాయలు ఇస్తుంది అని ప్రచారం జరుగుతోంది", [Rec()], TL())
    assert res["language"] == "te" and "అబద్ధం" in res["card"]
    assert res["card_en"].splitlines()[0].endswith("FALSE") and "https://pib.gov.in/x" in res["card_en"]
    assert res["claims"][0]["english"] == "Government will give Rs 1000 to every woman"

def test_english_forward_has_no_redundant_english_panel():
    res = check_forward("Government will give Rs 1000 to every woman in the country.", [FakeRetriever([])])
    assert "card_en" not in res and res["claims"][0]["english"] == ""

def test_website_shows_english_meaning_panel(server):
    import sach.web as W
    class TL:
        def translate(self, t): return "Government will give Rs 5000 to every woman"
        def stance(self, claim, title, text): return "contradicts"
    W.Handler.llm = TL()
    code, h = _post(server, "ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది అని ప్రచారం జరుగుతోంది")
    assert code == 200 and "What this means in English" in h and "We understood the forward as" in h
    assert "Government will give Rs 5000 to every woman" in h and "Copy both languages" in h
    code, h = _post(server, "Government will give Rs 5000 to every woman.")
    assert "What this means in English" not in h            # English forwards don't need it
    W.Handler.llm = None

def test_no_claim_card_has_english_meaning_for_telugu():
    res = check_forward("శుభోదయం 🙏 అందరికీ షేర్ చేయండి", [FakeRetriever([])])
    assert res.get("no_claims") and "NO CLAIM FOUND" in res["card_en"]


# --- generic-word matching must not create verdicts (National Mango Day vs National Handloom Day)
def test_distinctive_words_drive_matching_not_generic_government_words():
    from sach.stance import distinctive, subject_coverage, _stem
    claim = "The Cabinet has approved declaring the 14th of every month as National Mango Day."
    assert "mango" in distinctive(claim) and _stem("cabinet") not in distinctive(claim) and _stem("national") not in distinctive(claim)
    page = "PM's address at the celebration of National Handloom Day. The Cabinet has approved new schemes on the 7th of August every year."
    assert subject_coverage(claim, page) < 0.5

def test_unrelated_official_page_cannot_make_misleading_or_true_or_false():
    claim = "The Cabinet has approved declaring the 14th of every month as National Mango Day."
    title = "PM's address at the celebration of National Handloom Day"
    page = "The Cabinet has approved declaring the 7th of August every year as National Handloom Day, the PM said on the 14th."
    assert heuristic_stance(claim, title, page, TIER_OFFICIAL) == "none"
    for label in ("mixed", "confirms", "contradicts"):
        assert validate_stance(label, "The Cabinet has approved declaring the 7th of August every year as National Handloom Day", claim, title, page) == "none"

def test_real_scheme_with_wrong_number_still_reaches_partial():
    claim = "The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 50,000 crore."
    page = "The Union Cabinet has approved a Scheme for Promotion of Surface Coal/Lignite Gasification Projects with a financial outlay of Rs 37,500 crore."
    q = "Scheme for Promotion of Surface Coal/Lignite Gasification Projects with a financial outlay of Rs 37,500 crore"
    assert validate_stance("mixed", q, claim, "Cabinet approves Scheme", page) == "mixed"


# --- degraded (no-LLM / quota exhausted) mode must be safe
def test_claim_about_fake_news_is_never_judged_by_the_heuristic():
    claim = "Suspected fake news can be sent to the PIB Fact Check WhatsApp hotline 8799711259."
    title = "PIB Fact Check Unit Invites Public to Share Suspected Fake News related to Government on 8799711259"
    assert heuristic_stance(claim, title, "Send suspected fake news to WhatsApp 8799711259", TIER_PIB) == "none"

def test_degraded_mode_only_ever_contradicts_from_a_pib_debunk():
    from sach.stance import degraded_stance
    claim = "Central Government will reduce the retirement age of employees to 50 years."
    title = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
    body = "A media report said the retirement age would be reduced to 50 years. This is fake; no such proposal exists."
    assert degraded_stance(claim, title, body, TIER_PIB) == "contradicts"
    assert degraded_stance(claim, title, body, TIER_OFFICIAL) == "none"          # not a PIB debunk page
    ok = "Cabinet approves continuation of the Samagra Shiksha scheme from April 2021 to March 2026"
    assert degraded_stance("Cabinet approves continuation of Samagra Shiksha from April 2021 to March 2026", ok, ok, TIER_OFFICIAL) == "none"   # never TRUE
    assert degraded_stance("Cabinet approves continuation of Samagra Shiksha from April 2021 to March 2030", ok, ok, TIER_OFFICIAL) == "none"   # never MISLEADING

def test_degraded_flag_when_llm_missing_or_failing():
    class Down:
        failures = 0
        def stance(self, *a, **k):
            Down.failures += 1; raise RuntimeError("429 quota")
    ev = Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")
    assert check_forward("Government will give Rs 1000 to every woman in the country.", [FakeRetriever([ev])], None)["degraded"] is True
    d = Down()
    assert check_forward("Government will give Rs 1000 to every woman in the country.", [FakeRetriever([ev])], d)["degraded"] is True
    class Fine:
        failures = 0
        def stance(self, *a, **k): return "none"
    assert check_forward("Government will give Rs 1000 to every woman in the country.", [FakeRetriever([ev])], Fine())["degraded"] is False

def test_website_shows_limited_mode_notice(server):
    code, h = _post(server, "Government will give Rs 5000 to every woman.")     # fixture runs with llm=None
    assert code == 200 and "Limited mode" in h

# --- user-chosen reply language (independent of the input language)
class _PibFake:
    def __init__(self): self.q = None
    def search(self, q):
        self.q = q
        return [Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")]
class _TL:
    def translate(self, t): return "Government will give Rs 1000 to every woman"
    def stance(self, claim, title, text, tier=""): return "contradicts"

HI_FWD = "सरकार हर महिला को 1000 रुपये दे रही है, जल्दी शेयर करें।"
EN_FWD = "Government will give Rs 1000 to every woman in the country."

def test_hindi_forward_with_english_reply_chosen():
    r = _PibFake(); res = check_forward(HI_FWD, [r], _TL(), reply_lang="en")
    assert res["input_language"] == "hi" and res["language"] == "en"
    assert res["card"].splitlines()[0].endswith("FALSE") and "card_en" not in res
    assert r.q == "Government will give Rs 1000 to every woman"          # still searched in English via the INPUT language

def test_english_forward_with_telugu_and_tinglish_reply_chosen():
    res = check_forward(EN_FWD, [_PibFake()], _TL(), reply_lang="te")
    assert res["input_language"] == "en" and res["language"] == "te" and "అబద్ధం" in res["card"]
    assert res["card_en"].splitlines()[0].endswith("FALSE")                # English meaning accompanies a non-English reply
    res = check_forward(EN_FWD, [_PibFake()], _TL(), reply_lang="tl")
    assert res["language"] == "tl" and res["card"].splitlines()[0].endswith("ABADDHAM")

@pytest.mark.parametrize("bad", [None, "auto", "xx", "", "EN ", "klingon"])
def test_unknown_or_auto_reply_lang_falls_back_to_matching_the_forward(bad):
    res = check_forward(HI_FWD, [_PibFake()], _TL(), reply_lang=bad)
    assert res["language"] == "hi" and "झूठ" in res["card"]

def test_no_claim_card_respects_chosen_language():
    res = check_forward("Good morning 🙏", [FakeRetriever([])], None, reply_lang="hi")
    assert res["no_claims"] and res["language"] == "hi" and "दावा" in res["card"] and "NO CLAIM FOUND" in res["card_en"]

def test_website_language_selector_form_json_and_query(server):
    import sach.web as W
    W.Handler.llm = _TL()
    h = _ur.urlopen(server + "/").read().decode()
    assert 'name="lang"' in h and all(f'value="{v}"' in h for v in ("auto", "en", "hi", "te", "tl"))
    code, h = _post(server, EN_FWD, raw=_up.urlencode({"text": EN_FWD, "lang": "te"}).encode())
    assert code == 200 and "అబద్ధం" in h and "(your choice)" in h and 'value="te" selected' in h        # choice is remembered on the result page
    code, body = _post(server, "", "/?format=json", raw=_json.dumps({"text": HI_FWD, "lang": "en"}).encode(), headers={"Content-Type": "application/json"})
    d = _json.loads(body); assert d["language"] == "en" and d["input_language"] == "hi" and d["card"].splitlines()[0].endswith("FALSE")
    code, body = _post(server, EN_FWD, "/?format=json&lang=hi")
    assert _json.loads(body)["language"] == "hi"
    code, body = _post(server, EN_FWD, "/?format=json&lang=klingon")
    assert code == 200 and _json.loads(body)["language"] == "en"                                          # bad value never errors
    code, h = _post(server, EN_FWD)
    assert "(matched to the forward)" in h
    W.Handler.llm = None

def test_empty_input_keeps_the_chosen_language_in_the_form(server):
    code, h = _post(server, "", raw=_up.urlencode({"text": "  ", "lang": "hi"}).encode())
    assert code == 400 and 'value="hi" selected' in h


# --- wider official allowlist
@pytest.mark.parametrize("url", ["https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=1", "https://rbidocs.rbi.org.in/x.pdf",
    "https://www.mygov.in/campaigns/x", "https://sansad.in/ls/questions", "https://www.npci.org.in/what-we-do/upi", "https://nta.ac.in/Home"])
def test_more_official_domains_are_recognised(url):
    assert is_official(url)

@pytest.mark.parametrize("url", ["https://rbi.org.in.evil.com/", "https://evilrbi.org.in/", "https://fakesansad.in/", "https://mygov.in.phish.io/x",
    "https://notrbi.org.in/", "https://rbi.org.in@evil.com/", "https://sansad.in.evil.in/"])
def test_lookalike_domains_are_not_official(url):
    assert not is_official(url)

# --- source expansion: local PIB index, PIB-first multi-query retrieval, de-duplication
import sach.index as PIDX
import sach.retrieve as R

def _entry(prid, title, excerpt="", debunk=False):
    return {"prid": str(prid), "title": title, "excerpt": excerpt, "debunk": debunk, "url": f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}", "fetched_at": TS}

def test_index_append_dedupes_search_needs_subject_words_and_survives_corrupt_lines(tmp_path):
    p = str(tmp_path / "idx.jsonl")
    assert PIDX.append([_entry(1, "No reduction in retirement age of Central Government employees", "fake news busts", True),
                        _entry(2, "PM's address at the celebration of National Handloom Day", "Cabinet approved handloom schemes")], p) == 2
    assert PIDX.append([_entry(1, "dup"), _entry(3, "Cabinet approves Samagra Shiksha continuation 2021 to 2026")], p) == 1     # PRID 1 already indexed
    with open(p, "a") as f: f.write("{not json}\n")
    assert len(PIDX.load(p)) == 3                                                                   # corrupt line skipped
    hits = PIDX.search("Central Government will reduce the retirement age of employees to 50 years.", path=p)
    assert hits and hits[0]["prid"] == "1" and hits[0]["debunk"]
    assert PIDX.search("The Cabinet has approved declaring the 14th of every month as National Mango Day.", path=p) == []   # generic words alone never match
    assert PIDX.load(str(tmp_path / "missing.jsonl")) == []

def test_canonical_key_merges_pib_url_variants():
    ks = {R.canonical_key(u) for u in ["https://pib.gov.in/PressReleasePage.aspx?PRID=1618590",
          "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1618590&reg=48&lang=2", "https://pib.gov.in/PressReleaseIframePage.aspx?PRID=1618590"]}
    assert ks == {"pib:1618590"}
    assert R.canonical_key("https://Example.gov.in/a/#x") == R.canonical_key("https://example.gov.in/a")
    assert R.canonical_key("https://evil.com/?PRID=1618590") != "pib:1618590"

def test_pib_retriever_uses_the_local_index(tmp_path, monkeypatch):
    p = str(tmp_path / "idx.jsonl")
    PIDX.append([_entry(777, "Clarification: fake recruitment notification for 4208 Constable posts in RPF", "fictitious message RPF", True)], p)
    monkeypatch.setattr(PIDX, "INDEX_PATH", p)
    monkeypatch.setattr(R, "get_release", lambda prid: {"title": "Clarification: fake recruitment notification for 4208 Constable posts in RPF",
        "body": "A fictitious message is being circulated.", "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=%s" % prid, "fetched_at": TS})
    ev = R.PibRetriever(seed_path=str(tmp_path / "none.json"), use_rss=False).search("RPF has announced recruitment of 4,208 Constable posts.")
    assert len(ev) == 1 and ev[0].tier == TIER_PIB and ev[0].url.endswith("PRID=777")

class _FakeBrave(R.BraveRetriever):
    def __init__(self, results):
        super().__init__(key="k"); self.results, self.queries = results, []
    def _search(self, q, count=8):
        self.queries.append(q)
        for needle, urls in self.results.items():
            if needle in q: return urls
        return []

def _stub_pages(monkeypatch, titles):
    monkeypatch.setattr(R, "fetch", lambda url: {"status": 200, "fetched_at": TS, "body": f"<html><title>{titles.get(url, 'Page')}</title><body>{titles.get(url, 'Page')} text</body></html>"})

def test_brave_runs_pib_then_official_and_skips_factcheckers_when_authoritative_found(monkeypatch):
    _stub_pages(monkeypatch, {})
    b = _FakeBrave({"site:pib.gov.in": ["https://www.pib.gov.in/PressReleasePage.aspx?PRID=5&reg=3&lang=1"],
                    "site:gov.in": ["https://www.pib.gov.in/PressReleasePage.aspx?PRID=5", "https://rbi.org.in/Scripts/x.aspx", "https://example.com/no"],
                    "site:altnews.in": ["https://www.altnews.in/x"]})
    ev = b.search("Government will give Rs 1000 to every woman under Corona Sahayata Yojana")
    assert b.queries[0].startswith("site:pib.gov.in") and "site:gov.in" in b.queries[1]
    assert not any("altnews" in q for q in b.queries)                       # saved a query: fact-checkers cannot decide a verdict
    urls = [e.url for e in ev]
    assert any("rbi.org.in" in u for u in urls) and not any("example.com" in u for u in urls)
    assert sum("PRID=5" in u for u in urls) == 1                            # same release under two URLs counted once

def test_brave_falls_back_to_keyword_pib_query_then_factcheckers_when_nothing_official(monkeypatch):
    _stub_pages(monkeypatch, {})
    b = _FakeBrave({"site:altnews.in": ["https://www.altnews.in/fake-claim"]})
    ev = b.search("Every household will receive a free solar-powered refrigerator next month")
    assert sum(q.startswith("site:pib.gov.in") for q in b.queries) == 2     # full-claim query, then the keyword form
    assert any("site:altnews.in" in q for q in b.queries)
    assert [e.tier for e in ev] == [TIER_FACTCHECKER]

def test_brave_pib_pages_are_parsed_and_tiered_as_debunks(monkeypatch):
    html = "<html><title>Press Release Page</title><h2>Fake news on WhatsApp claims Government giving Rs 1000</h2><div id='PdfDiv'>The claim is fake.</div></html>"
    monkeypatch.setattr(R, "fetch", lambda url: {"status": 200, "fetched_at": TS, "body": html})
    b = _FakeBrave({"site:pib.gov.in": ["https://www.pib.gov.in/PressReleasePage.aspx?PRID=1618314&reg=3&lang=1"]})
    ev = b.search("Government giving Rs 1000 Corona Sahayata Yojana")
    assert ev[0].tier == TIER_PIB and ev[0].title.startswith("Fake news on WhatsApp") and ev[0].source_name.startswith("PIB")

def test_keyword_query_keeps_distinctive_words_and_numbers():
    kw = R.BraveRetriever._keywords("The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore.")
    assert "coal" in kw and "lignite" in kw and "37,500" in kw and "Cabinet" not in kw

def test_pipeline_dedupes_same_release_from_two_retrievers():
    a = Evidence("PIB", "https://pib.gov.in/PressReleasePage.aspx?PRID=9", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")
    b = Evidence("www.pib.gov.in", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=9&reg=3&lang=1", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")
    class TL:
        def stance(self, c, t, x, tier=""): return "contradicts"
    res = check_forward("Government will give Rs 1000 to every woman in the country.", [FakeRetriever([a]), FakeRetriever([b])], TL())
    assert res["verdict"] == FALSE and len(res["claims"][0]["citations"]) == 1


def test_logo_shows_english_meaning_truth(server):
    h = _ur.urlopen(server + "/?x=1").read().decode()
    assert "<small><span class=\"sc\">सच · నిజం · </span>truth</small>" in h

# --- LLM failover: key rotation, free providers, cooldowns
import sach.llm as LL
import urllib.error, urllib.request

PAGE = "Fake: the scheme claim is a hoax, says ministry"
CLAIM = "the scheme claim"
GOOD = "CONTRADICTS | Fake: the scheme claim is a hoax"

class _Scripted(LL._Judge):
    """A judge whose _raw replies come from a script: str = reply, Exception = raised."""
    def __init__(self, name, script, models="m1,m2"):
        self.name, self.models, self.script, self.calls = name, models.split(","), script, 0
    def _raw(self, model, system, user, max_tokens):
        self.calls += 1
        r = self.script(model, system) if callable(self.script) else self.script
        if isinstance(r, Exception): raise r
        return r

def _http(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)

def test_failover_uses_next_judge_when_first_is_out_of_quota():
    a, b = _Scripted("a", _http(429)), _Scripted("b", GOOD)
    f = LL.FailoverJudge([a, b])
    assert f.stance(CLAIM, "t", PAGE) == "contradicts" and b.calls >= 1
    assert f.failures == 0                          # a backup answered: not "limited mode"

def test_quota_exhausted_judge_is_skipped_during_cooldown_then_retried(monkeypatch):
    a, b = _Scripted("a", _http(429)), _Scripted("b", GOOD)
    f = LL.FailoverJudge([a, b]); now = [1000.0]
    monkeypatch.setattr(LL.time, "time", lambda: now[0])
    f.stance(CLAIM, "t", PAGE); first_calls = a.calls
    assert first_calls == 1 and not a.available()    # one 429 and its sibling models are not hammered
    f.stance(CLAIM, "t", PAGE); f.stance(CLAIM, "t", PAGE)
    assert a.calls == first_calls                    # skipped without a call while cooling down
    now[0] += LL.COOLDOWN_S + 1
    assert a.available(); f.stance(CLAIM, "t", PAGE)
    assert a.calls == first_calls + 1                # retried after the cooldown

@pytest.mark.parametrize("err", [_http(503), _http(404), TimeoutError("slow"), ValueError("odd payload")])
def test_transient_errors_do_not_start_a_cooldown(err):
    a = _Scripted("a", err)
    with pytest.raises(Exception): a.stance(CLAIM, "t", PAGE)
    assert a.available() and a.calls == 2            # both models tried, judge stays usable

def test_all_judges_down_raises_counts_failure_and_site_falls_back_safely():
    f = LL.FailoverJudge([_Scripted("a", _http(429)), _Scripted("b", OSError("down"))])
    with pytest.raises(Exception): f.stance(CLAIM, "t", PAGE)
    assert f.failures == 1
    ev = Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")
    res = check_forward("Government will give Rs 1000 to every woman.", [FakeRetriever([ev])], LL.FailoverJudge([_Scripted("a", _http(429))]))
    assert res["degraded"] is True and res["verdict"] == FALSE      # safe rules-only mode still catches the clear PIB debunk

def test_everything_in_cooldown_fails_fast_without_calls():
    a = _Scripted("a", _http(429)); f = LL.FailoverJudge([a])
    with pytest.raises(Exception): f.stance(CLAIM, "t", PAGE)
    calls = a.calls
    with pytest.raises(Exception): f.stance(CLAIM, "t", PAGE)
    assert a.calls == calls and f.failures == 2

def test_translation_fails_over_too():
    f = LL.FailoverJudge([_Scripted("a", _http(429)), _Scripted("b", "Government will give Rs 1000")])
    assert f.translate("తెలుగు") == "Government will give Rs 1000"

def test_failover_judge_works_with_judges_that_take_no_tier_argument():
    class Old:
        name = "old"; models = ["x"]; failures = 0
        def available(self): return True
        def stance(self, c, t, x): return "contradicts"
    assert LL.FailoverJudge([Old()]).stance(CLAIM, "t", PAGE, tier="pib_debunk") == "contradicts"

def test_decisive_call_from_backup_provider_still_needs_the_validation_rules():
    # backup provider hallucinates a quote that is not on the page -> rejected, never a verdict
    liar = _Scripted("groq", "CONTRADICTS | This sentence is nowhere on the page at all")
    assert LL.FailoverJudge([liar]).stance(CLAIM, "t", PAGE) == "none"

def test_openai_compatible_judge_parses_chat_completions_and_sends_bearer_auth(monkeypatch):
    sent = {}
    def fake_post(self, model, body):
        sent["model"], sent["body"] = model, body
        return {"choices": [{"message": {"content": GOOD}}]}
    monkeypatch.setattr(LL.OpenAICompatJudge, "_post", fake_post)
    j = LL.OpenAICompatJudge("groq", "https://api.groq.com/openai/v1/", "sekret", "m1,m2")
    assert j.stance(CLAIM, "t", PAGE) == "contradicts"
    assert sent["body"]["messages"][0]["role"] == "system" and sent["body"]["temperature"] == 0 and j.base_url.endswith("/v1")

def test_openai_compatible_judge_request_headers(monkeypatch):
    seen = {}
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b'{"choices":[{"message":{"content":"NEITHER"}}]}'
    def fake_open(req, timeout=0):
        seen["h"], seen["url"] = dict(req.header_items()), req.full_url; return R()
    monkeypatch.setattr(LL.urllib.request, "urlopen", fake_open)
    LL.OpenAICompatJudge("mistral", "https://api.mistral.ai/v1", "KEY123", "m")._raw("m", "s", "u", 10)
    assert seen["h"]["Authorization"] == "Bearer KEY123" and seen["url"] == "https://api.mistral.ai/v1/chat/completions"

def test_build_judges_wiring_from_environment(monkeypatch):
    for k in ("GEMINI_API_KEY", "GEMINI_API_KEYS", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GROQ_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert LL.get_llm() is None                                           # no keys: rules-only mode
    monkeypatch.setenv("GEMINI_API_KEY", "gk1,gk2"); monkeypatch.setenv("GEMINI_API_KEY_2", "gk2 , gk3")
    monkeypatch.setenv("GROQ_API_KEY", "gq"); monkeypatch.setenv("OPENROUTER_API_KEY", "or"); monkeypatch.setenv("MISTRAL_API_KEY", "ms")
    monkeypatch.setenv("SACH_GROQ_MODELS", "custom-model")
    f = LL.get_llm()
    assert [j.name.split("-")[0] for j in f.judges] == ["gemini", "gemini", "gemini", "groq", "openrouter", "mistral"]     # order of preference
    assert len({j.key for j in f.judges if j.name.startswith("gemini")}) == 3                                           # duplicates removed
    assert [j for j in f.judges if j.name == "groq"][0].models == ["custom-model"]
    assert [n for n, _ in f.describe()][-1] == "mistral" and all(s == "ready" for _, s in f.describe())


def test_denial_quote_gets_its_subject_from_the_title():
    claim = "Central Government will reduce the retirement age of employees to 50 years."
    title = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
    page = "A media report said the retirement age would be reduced to 50 years. This is fake; no such proposal exists."
    assert validate_stance("contradicts", "This is fake; no such proposal exists.", claim, title, page) == "contradicts"

def test_denial_on_a_roundup_page_about_other_claims_is_still_rejected():
    claim = "Central Government will reduce the retirement age of employees to 50 years."
    title = "PIBFactCheck tweets five items today carrying the official version"          # generic title: no subject
    page = "A viral video about a bridge is fake. This is fake; no such proposal exists. Retirement was not discussed."
    assert validate_stance("contradicts", "This is fake; no such proposal exists.", claim, title, page) == "none"
    # confirmations still need the quote itself to carry the claim
    page2 = "The Cabinet approved the scheme. It is true."
    assert validate_stance("confirms", "It is true.", "The Cabinet approved the scheme.", "Cabinet approves scheme", page2) == "none"


# --- a debunk page repeating the rumour can never CONFIRM it
RUMOUR_CLAIM = "Central Government will reduce the retirement age of employees to 50 years."
DEBUNK_TITLE = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
DEBUNK_BODY = "A media report said the retirement age would be reduced to 50 years. This is fake; no such proposal exists."

@pytest.mark.parametrize("label", ["confirms", "mixed"])
def test_debunk_page_cannot_confirm_or_partially_confirm_the_rumour_it_debunks(label):
    assert validate_stance(label, "A media report said the retirement age would be reduced to 50 years", RUMOUR_CLAIM, DEBUNK_TITLE, DEBUNK_BODY) == "none"

def test_quote_that_only_reports_a_rumour_cannot_confirm():
    page = "Viral message says Central Government will reduce the retirement age of employees to 50 years, officials noted."
    assert validate_stance("confirms", "Viral message says Central Government will reduce the retirement age of employees to 50 years", RUMOUR_CLAIM, "Retirement update", page) == "none"

def test_real_announcement_can_still_confirm():
    claim = "The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021 to March 2026."
    title = "Cabinet approves continuation of Samagra Shiksha Scheme for School Education from 1st April, 2021 to 31st March, 2026"
    page = title + ". Financial outlay of Rs.2,94,283.04 crore which includes Central share of Rs.1,85,398.32 crore."
    assert validate_stance("confirms", "Cabinet approves continuation of Samagra Shiksha Scheme for School Education from 1st April, 2021 to 31st March, 2026", claim, title, page) == "confirms"

def test_claims_about_fact_checking_itself_are_exempt_from_the_debunk_page_rule():
    claim = "PIB Fact-Check Unit has issued over 2,900 fact checks."
    title = "Government Counters Misinformation; PIB Fact-Check Unit Issues Over 2,900 Fact Checks"
    page = title + ". The PIB Fact-Check Unit has issued over 2,900 fact checks in total."
    assert validate_stance("confirms", "The PIB Fact-Check Unit has issued over 2,900 fact checks in total", claim, title, page) == "confirms"


def test_numbers_ignore_thousands_separators_including_indian_grouping():
    from sach.stance import numbers
    assert numbers("19,800 posts; 1,20,579 vacancies; Rs 37,500 crore; 99.8%; 2,900.") == {"19800", "120579", "37500", "99.8", "2900"}
    assert numbers("recruitment of 19800 posts and 120579 vacancies") >= {"19800", "120579"}

def test_comma_formatted_claim_matches_plain_number_in_debunk_title_degraded_mode():
    from sach.stance import degraded_stance
    c = "Railways has issued a recruitment notification for 19,800 Constable posts in RPF."
    t = "Clarification regarding fake recruitment notification for 19800 post of Constable in RPF in Social Media"
    x = "A fictitious message is being circulated on social media regarding recruitment of 19800 posts of Constable in RPF."
    assert degraded_stance(c, t, x, TIER_PIB) == "contradicts"

# --- tip jar (UPI): off by default, env-configured, safe
import sach.site as SITE

def _tip_env(monkeypatch, vpa="supporter@okbank", name=None):
    if vpa is None: monkeypatch.delenv("SACH_UPI_ID", raising=False)
    else: monkeypatch.setenv("SACH_UPI_ID", vpa)
    if name is None: monkeypatch.delenv("SACH_UPI_NAME", raising=False)
    else: monkeypatch.setenv("SACH_UPI_NAME", name)

def test_tip_jar_is_hidden_when_no_upi_id_is_set(server, monkeypatch):
    _tip_env(monkeypatch, None)
    h = _ur.urlopen(server + "/?t=off").read().decode()
    assert 'id="tip"' not in h and "upi://" not in h and "qrcode-generator" not in h and 'id="upiqr"' not in h and "Tip jar" not in h and "Do tips change" not in h
    code, h = _post(server, "Government will give Rs 5000 to every woman.")
    assert "Chip in for the corrections desk" not in h

@pytest.mark.parametrize("bad", ["", "notaupi", "a@b c", "x@", "@bank", "ab@123", '"><script>alert(1)</script>@x', "a b@okbank", "javascript:alert(1)", "me@ok bank", "a@b@c", "x" * 80 + "@ok"])
def test_invalid_upi_ids_disable_the_feature_instead_of_rendering(monkeypatch, bad):
    _tip_env(monkeypatch, bad)
    assert SITE.tip_config() is None
    assert b"upi://" not in SITE.home() and b'id="tip"' not in SITE.home()

@pytest.mark.parametrize("good", ["name@okhdfcbank", "first.last-1@ybl", "9876543210@paytm", "shop_name@oksbi", "a1@upi"])
def test_valid_upi_ids_are_accepted(monkeypatch, good):
    _tip_env(monkeypatch, good)
    assert SITE.tip_config()["vpa"] == good

def test_upi_links_are_well_formed_and_encoded(monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank", "Sach Desk & Co <x>")
    cfg = SITE.tip_config()
    assert cfg["name"] == "Sach Desk & Co x"                                   # unsafe characters stripped from the display name
    link = SITE.upi_link(cfg, 50, "Sach tip - One forward verified")
    assert link.startswith("upi://pay?pa=supporter@okbank&pn=Sach%20Desk%20%26%20Co%20x&cu=INR&tn=Sach%20tip%20-%20One%20forward%20verified&am=50")
    assert "am=" not in SITE.upi_link(cfg)                                     # "any amount": no am parameter
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(link).query)
    assert q["pa"] == ["supporter@okbank"] and q["cu"] == ["INR"] and q["am"] == ["50"] and q["pn"] == ["Sach Desk & Co x"]



def test_soft_tip_prompt_only_after_decisive_verdicts(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    code, h = _post(server, "Government will give Rs 5000 to every woman.")            # fixture evidence -> FALSE
    assert "Chip in for the corrections desk" in h and "never affects a verdict" in h
    code, h = _post(server, "Good morning 🙏")                                         # no claim
    assert "Chip in" not in h.split('id="tip"')[0]                                       # no prompt in the result block

def test_json_api_is_unaffected_by_tips(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    code, body = _post(server, "Government will give Rs 5000 to every woman.", "/?format=json")
    assert code == 200 and "upi" not in body.lower() and _json.loads(body)["verdict"] == "FALSE"

def test_malicious_display_name_cannot_inject_html(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank", '"><script>alert(1)</script>')
    h = _ur.urlopen(server + "/?t=xss").read().decode()
    assert "<script>alert(1)" not in h and "alert(1)" not in h.split('id="tip"')[1].split("</section>")[0]

def test_tip_never_influences_verdicts():
    from sach.verdict import decide
    import inspect, sach.verdict as V, sach.pipeline as P
    assert "upi" not in inspect.getsource(V).lower() and "tip" not in inspect.getsource(V).lower().replace("multip", "")
    assert "tip_config" not in inspect.getsource(P)


# --- tip jar v2: the UPI address never appears in page HTML (redirect + server-drawn QR)
import http.client as _hc

def _raw_get(server, path):
    host, port = server.replace("http://", "").split(":")
    c = _hc.HTTPConnection(host, int(port)); c.request("GET", path); r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()

def test_page_html_never_contains_the_upi_address_or_upi_links(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank", "Sach Desk")
    for path in ("/?t=1", "/?view=ledger"):
        h = _ur.urlopen(server + path).read().decode()
        assert "supporter" not in h and "okbank" not in h and "upi://" not in h and "@okbank" not in h
    code, h = _post(server, "Government will give Rs 5000 to every woman.")            # result page too
    assert "supporter" not in h and "upi://" not in h

def test_tip_section_has_funny_copy_tiers_picker_and_qr_image_but_no_copy_button(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _ur.urlopen(server + "/?t=2").read().decode()
    assert 'id="tip"' in h and "Nobody asked, but" in h and "Tips never change a verdict" in h
    assert any(t in h for t in SITE.TIP_HEADLINES) or any(SITE.esc(t) in h for t in SITE.TIP_HEADLINES)
    assert h.count('class="tipcard"') == 4 and "Samosa for the fact-checker" in h and "Sponsor a family-group intervention" in h
    for amt in (20, 50, 100, 500):
        assert f'href="/?view=pay&amp;amt={amt}"' in h
    assert 'id="fw"' in h and 'id="fwgo"' in h and "You were about to forward" in h                # forwards-saved picker
    assert '<img id="upiqr" src="/?view=tipqr"' in h
    assert 'id="copyupi"' not in h and "Copy UPI ID" not in h and "qrcode-generator" not in h and "cdnjs" not in h
    assert "Do tips change what Sach says?" in h and "Tip jar" in h and "will show you who you are paying" in h

def test_tip_button_redirects_to_the_upi_app_with_the_amount(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank", "Sach Desk")
    code, hdr, body = _raw_get(server, "/?go=tip&amt=50")
    assert code == 302 and hdr["Location"] == SITE.upi_link(SITE.tip_config(), 50, "Sach tip")
    assert hdr["Location"].startswith("upi://pay?pa=supporter@okbank&pn=Sach%20Desk&cu=INR") and hdr["Location"].endswith("&am=50")
    assert hdr["Cache-Control"] == "no-store" and "noindex" in hdr["X-Robots-Tag"] and body == b""
    code, hdr, _ = _raw_get(server, "/?go=tip")
    assert code == 302 and "am=" not in hdr["Location"]                                          # pay any amount

@pytest.mark.parametrize("bad", ["abc", "-5", "0", "99999999", "50.5", "5 0", "1e3", "%27%3B", "", "٥٠", "  "])
def test_bad_tip_amounts_mean_any_amount_never_an_error(server, monkeypatch, bad):
    _tip_env(monkeypatch, "supporter@okbank")
    from urllib.parse import quote
    code, hdr, _ = _raw_get(server, f"/?go=tip&amt={quote(bad)}")
    assert code == 302 and "am=" not in hdr["Location"] and hdr["Location"].count("pa=") == 1

def test_tip_endpoints_404_when_tip_jar_is_off(server, monkeypatch):
    _tip_env(monkeypatch, None)
    assert _raw_get(server, "/?go=tip&amt=50")[0] == 404
    assert _raw_get(server, "/?view=tipqr")[0] == 404

def test_tip_qr_is_a_server_drawn_svg_without_the_address_text(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    code, hdr, body = _raw_get(server, "/?view=tipqr")
    assert code == 200 and hdr["Content-Type"] == "image/svg+xml" and body.lstrip().startswith(b"<svg")
    assert b"supporter" not in body and b"okbank" not in body and hdr["Cache-Control"] == "no-store"
    assert len(body) > 500                                                                      # an actual drawn code, not an empty file

def test_tip_amount_parsing():
    assert [SITE.tip_amount(x) for x in ("1", "50", "10000", " 20 ")] == [1, 50, 10000, 20]
    assert [SITE.tip_amount(x) for x in ("0", "10001", "-1", "abc", "5.5", None, "")] == [None] * 7

def test_headline_is_stable_within_a_day_and_comes_from_the_list():
    assert SITE.tip_headline() == SITE.tip_headline() and SITE.tip_headline() in SITE.TIP_HEADLINES

def test_soft_prompt_quips_differ_by_verdict_and_unverified_gets_none(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    code, h = _post(server, "Government will give Rs 5000 to every woman.")                    # fixture evidence -> FALSE
    assert SITE.TIP_QUIPS["FALSE"] in h
    assert set(SITE.TIP_QUIPS) == {"FALSE", "TRUE", "MISLEADING"}


def test_forwards_picker_defaults_to_three_matching_the_server_rendered_amount(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _ur.urlopen(server + "/?t=picker").read().decode()
    assert '<option value="3" selected>3</option>' in h and 'amt=30"' in h and "Chip in ₹30" in h


# --- UPI app chooser (iPhone: the generic upi:// link opened WhatsApp instead of letting the payer choose)
def test_tier_buttons_open_the_chooser_not_a_random_app(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _ur.urlopen(server + "/?t=choose").read().decode()
    assert 'href="/?view=pay&amp;amt=20"' in h and 'href="/?view=pay"' in h and 'href="/?view=pay&amp;amt=30"' in h
    assert "?go=tip" not in h.split('id="tip"')[1].split("</section>")[0]                 # nothing in the tip section jumps straight to an app
    assert "then pick your UPI app" in h

def test_chooser_page_lists_apps_amount_and_qr_without_the_address(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank", "Sach")
    code, hdr, body = _raw_get(server, "/?view=pay&amt=50")
    h = body.decode()
    assert code == 200 and "Pay ₹50" in h
    for name in ("Google Pay", "PhonePe", "Paytm", "BHIM", "Any other UPI app"):
        assert name in h
    for app in ("gpay", "phonepe", "paytm", "bhim", "upi"):
        assert f'href="/?go=tip&amp;amt=50&amp;app={app}"' in h
    assert '<img id="upiqr" src="/?view=tipqr&amp;amt=50"' in h and "WhatsApp" in h                  # iPhone tip explains the WhatsApp surprise
    assert "supporter" not in h and "okbank" not in h and "upi://" not in h and "gpay://" not in h        # no address, no scheme links in HTML

def test_chooser_without_amount_says_any_amount(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    code, _, body = _raw_get(server, "/?view=pay")
    h = body.decode()
    assert code == 200 and "Pay any amount" in h and 'href="/?go=tip&amp;app=gpay"' in h and "amt=" not in h.split("<h1")[1].split("</h1>")[0]

@pytest.mark.parametrize("app,prefix", [("gpay", "gpay://upi/pay?"), ("phonepe", "phonepe://pay?"), ("paytm", "paytmmp://pay?"), ("bhim", "bhim://upi/pay?"), ("upi", "upi://pay?")])
def test_each_app_gets_its_own_link_scheme_with_the_same_payee_and_amount(server, monkeypatch, app, prefix):
    _tip_env(monkeypatch, "supporter@okbank", "Sach")
    code, hdr, _ = _raw_get(server, f"/?go=tip&amt=100&app={app}")
    loc = hdr["Location"]
    assert code == 302 and loc.startswith(prefix) and "pa=supporter@okbank" in loc and loc.endswith("&am=100") and "cu=INR" in loc

@pytest.mark.parametrize("bad", ["WhatsApp", "javascript:alert(1)", "", "gpay://evil", "../x", "G P A Y", "bhim://evil", "amazonpay"])
def test_unknown_app_falls_back_to_generic_scheme_never_an_open_redirect(server, monkeypatch, bad):
    from urllib.parse import quote
    _tip_env(monkeypatch, "supporter@okbank")
    code, hdr, _ = _raw_get(server, f"/?go=tip&amt=20&app={quote(bad)}")
    assert code == 302 and hdr["Location"].startswith("upi://pay?pa=supporter@okbank")

def test_app_name_is_case_insensitive(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    assert _raw_get(server, "/?go=tip&app=GPay")[1]["Location"].startswith("gpay://upi/pay?")

def test_amount_qr_differs_from_any_amount_qr_and_leaks_nothing(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    a = _raw_get(server, "/?view=tipqr")[2]; b = _raw_get(server, "/?view=tipqr&amt=50")[2]
    assert a != b and b.lstrip().startswith(b"<svg") and b"supporter" not in b
    assert _raw_get(server, "/?view=tipqr&amt=abc")[2] == a                                          # bad amount -> any-amount QR

def test_chooser_is_hidden_when_tip_jar_is_off(server, monkeypatch):
    _tip_env(monkeypatch, None)
    assert _raw_get(server, "/?view=pay&amt=50")[0] == 404

def test_chooser_escapes_and_ignores_hostile_amounts(server, monkeypatch):
    from urllib.parse import quote
    _tip_env(monkeypatch, "supporter@okbank")
    code, _, body = _raw_get(server, "/?view=pay&amt=" + quote('"><script>alert(1)</script>'))
    h = body.decode()
    assert code == 200 and "alert(1)" not in h and "Pay any amount" in h

def test_upi_link_builder_supports_apps_and_falls_back():
    cfg = {"vpa": "supporter@okbank", "name": "Sach"}
    assert SITE.upi_link(cfg, 20, app="phonepe").startswith("phonepe://pay?pa=supporter@okbank")
    assert SITE.upi_link(cfg, 20, app="nope").startswith("upi://pay?")
    assert SITE.upi_link(cfg, 20).startswith("upi://pay?")                                           # default unchanged


# --- logos, BHIM tile, custom amounts
def test_every_app_tile_has_its_own_inline_logo_and_no_external_image_requests(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _raw_get(server, "/?view=pay&amt=50")[2].decode()
    tiles = h.split('class="appbtn"')[1:]
    assert len(tiles) == 5 and all('class="ico"><svg' in t.split("</a>")[0] for t in tiles)
    icons = [t.split('class="ico">')[1].split("</span>")[0] for t in tiles]
    assert len(set(icons)) == 5                                           # five different icons
    assert 'fill="#4285F4"' in icons[0] and 'fill="#5F259F"' in icons[1] and 'fill="#20336B"' in icons[2] and "BHIM" in icons[3]
    import re
    assert "<img" not in h.replace('<img id="upiqr"', "") and "cdn" not in h                             # logos are inline SVG
    assert not re.search(r'src="https?://', h) and not re.search(r"url\(https?://", h)                  # no third-party images or scripts (only the page's font stylesheet link)
    assert "trademarks of their owners" in h and "Simple Icons" in h

def test_chooser_has_a_change_amount_form_prefilled(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _raw_get(server, "/?view=pay&amt=75")[2].decode()
    assert 'class="otheramt compact"' in h and 'name="view" value="pay"' in h and 'name="amt" type="number"' in h and 'min="1" max="10000"' in h
    assert 'value="75"' in h and "Change amount" in h and 'method="get" action="/"' in h

def test_tip_section_has_an_other_amount_tile(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _ur.urlopen(server + "/?t=other").read().decode()
    tip = h.split('id="tip"')[1].split("</section>")[0]
    assert 'class="tipcard other"' in tip and "Other amount" in tip and 'name="amt" type="number"' in tip and "₹1 to ₹10,000" in tip
    assert tip.count('class="tipcard"') == 4                                # the four preset tiers are unchanged

@pytest.mark.parametrize("bad", ["abc", "0", "-5", "10001", "99999999", "5.5", "1e3"])
def test_invalid_custom_amount_shows_a_clear_message_and_still_lets_them_pay(server, monkeypatch, bad):
    _tip_env(monkeypatch, "supporter@okbank")
    code, _, body = _raw_get(server, f"/?view=pay&amt={bad}")
    h = body.decode()
    assert code == 200 and "whole number of rupees from 1 to 10,000" in h and "Pay any amount" in h and 'href="/?go=tip&amp;app=gpay"' in h

def test_no_error_message_for_valid_or_missing_amount(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    for path in ("/?view=pay", "/?view=pay&amt=75", "/?view=pay&amt="):
        assert "whole number of rupees" not in _raw_get(server, path)[2].decode()

def test_custom_amount_flows_into_the_app_links_and_qr(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    h = _raw_get(server, "/?view=pay&amt=75")[2].decode()
    assert 'href="/?go=tip&amp;amt=75&amp;app=phonepe"' in h and 'src="/?view=tipqr&amp;amt=75"' in h and "Pay ₹75" in h
    assert _raw_get(server, "/?go=tip&amt=75&app=paytm")[1]["Location"].endswith("&am=75")

def test_icons_and_forms_leak_no_address(server, monkeypatch):
    _tip_env(monkeypatch, "supporter@okbank")
    for path in ("/?view=pay&amt=50", "/?t=leak", "/?view=pay&amt=abc"):
        h = _raw_get(server, path)[2].decode()
        assert "supporter" not in h and "okbank" not in h and "upi://" not in h and "bhim://" not in h and "gpay://" not in h
