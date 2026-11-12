"""Source lists (official + fact-checker) and the Google Fact Check Tools retriever. All offline."""
import io, json, urllib.error
import pytest
from sach.fetch import is_official, is_factchecker
from sach.models import Claim, Evidence, TIER_FACTCHECKER, TIER_OFFICIAL, UNVERIFIED
from sach.verdict import decide
import sach.retrieve as R
from sach.factcheck_api import FactCheckToolsRetriever, ENDPOINT

TS = "2026-11-12T10:00:00+00:00"

# --- official list: (real host, real subdomain)
NEW_OFFICIAL = {
    "licindia.in": "customer.licindia.in", "sbi.co.in": "retail.sbi.co.in", "onlinesbi.sbi": "retail.onlinesbi.sbi",
    "aiims.edu": "www.aiims.edu", "pfrda.org.in": "www.pfrda.org.in", "aicte-india.org": "www.aicte-india.org",
    "rbiretaildirect.org.in": "www.rbiretaildirect.org.in", "ugc.ac.in": "www.ugc.ac.in", "jansuraksha.in": "www.jansuraksha.in",
}

@pytest.mark.parametrize("d,sub", NEW_OFFICIAL.items())
def test_new_official_hosts_match_host_subdomain_and_uppercase(d, sub):
    assert is_official(f"https://{d}/x") and is_official(f"https://{sub}/x?a=1")
    assert is_official(f"HTTPS://{d.upper()}/Path") and is_official(f"https://{sub.upper()}/")

@pytest.mark.parametrize("d", NEW_OFFICIAL)
def test_new_official_hosts_reject_lookalikes_and_tricks(d):
    bad = [f"https://evil{d}/", f"https://not-{d}/", f"https://{d}.evil.com/", f"https://{d}.evil.in/x",
           f"https://evil.com/{d}", f"https://evil.com/?u=https://{d}/", f"https://{d}@evil.com/",
           f"https://{d}:443@evil.com/", f"https://evil.com#@{d}/", f"https://evil.com\\@{d}/", f"https://{d}%2eevil.com/"]
    for u in bad:
        assert not is_official(u), u

def test_bank_in_is_a_zone_suffix_for_true_subdomains_only():
    for u in ["https://sbi.bank.in/", "https://onlinesbi.sbi.bank.in/x", "https://www.hdfc.bank.in/", "https://SBI.BANK.IN/"]:
        assert is_official(u), u
    for u in ["https://notabank.in/", "https://evilbank.in/", "https://bank.in/", "https://bank.in.evil.com/", "https://sbi.bank.in.evil.com/",
              "https://sbi.bank.in@evil.com/", "https://evil.com/sbi.bank.in", "https://fakebank.in.net/", "https://sbi.bank.info/"]:
        assert not is_official(u), u

def test_existing_suffix_matching_is_dot_anchored_and_backslash_safe():
    assert is_official("https://www.who.int/x") and is_official("https://who.int/")
    assert not is_official("https://notwho.int/") and not is_official("https://evilgov.in/") and not is_official("https://gov.in.evil.com/")
    assert not is_official("https://evil.com\\@rbi.org.in/")            # urlparse reads rbi.org.in, a browser goes to evil.com
    assert is_official("https://ssc.gov.in/") and is_official("https://uidai.gov.in/") and is_official("https://cybercrime.gov.in/")

# --- fact-checker list
WHOLE_SITE = {"altnews.in": "www.altnews.in", "boomlive.in": "hindi.boomlive.in", "vishvasnews.com": "factchecker.vishvasnews.com",
              "factly.in": "telugu.factly.in", "factcrescendo.com": "hindi.factcrescendo.com", "newschecker.in": "hindi.newschecker.in",
              "youturn.in": "www.youturn.in"}

@pytest.mark.parametrize("d,sub", WHOLE_SITE.items())
def test_whole_site_factcheckers(d, sub):
    assert is_factchecker(f"https://{d}/a") and is_factchecker(f"https://{sub}/a") and is_factchecker(f"HTTPS://{d.upper()}/A")
    for u in [f"https://evil{d}/", f"https://{d}.evil.com/", f"https://evil.com/{d}", f"https://{d}@evil.com/", f"https://evil.com\\@{d}/"]:
        assert not is_factchecker(u), u

PATH_SITES = {
    "newsmeter.in": ["/fact-check/x", "/fact-check-health/y-778244", "/ai-deepfake/z"], "newsmobile.in": ["/nm-fact-checker/fact-check-a/"],
    "telugupost.com": ["/factcheck/a-1", "/english-factcheck/b-2", "/ai-factcheck/c-3"], "indiatoday.in": ["/fact-check/story/a-2026-10-27"],
    "thequint.com": ["/news/webqoof/a-fact-check"], "ptinews.com": ["/factcheck/factcheck.aspx"],
}
NOT_FACTCHECK_PATHS = ["/", "/news/india/some-story", "/sports/x", "/fact-checker-fan", "/factchecking-blog", "/factcheck-not/x"]

@pytest.mark.parametrize("d,paths", PATH_SITES.items())
def test_news_site_counts_only_in_its_factcheck_section(d, paths):
    for p in paths:
        assert is_factchecker(f"https://www.{d}{p}"), p
        assert is_factchecker(f"https://{d.upper()}{p.upper()}"), p
    for p in NOT_FACTCHECK_PATHS:
        assert not is_factchecker(f"https://www.{d}{p}"), p
    assert not is_factchecker(f"https://{d}")                            # homepage is not a fact-check
    assert not is_factchecker(f"https://www.{d}/news/../sports/x")      # dot-segments are resolved before the prefix check
    assert is_factchecker(f"https://www.{d}/./{PATH_SITES[d][0].strip('/')}/./x")
    assert not is_factchecker(f"https://{d}.evil.com{PATH_SITES[d][0]}") and not is_factchecker(f"https://evil{d}{PATH_SITES[d][0]}")
    assert not is_factchecker(f"https://{d}@evil.com{PATH_SITES[d][0]}")
    assert not is_factchecker(f"https://evil.com/{d}{PATH_SITES[d][0]}")

def test_path_traversal_out_of_the_factcheck_section_is_rejected():
    assert not is_factchecker("https://www.indiatoday.in/fact-check/../india/x")
    assert not is_factchecker("https://www.indiatoday.in/fact-check/%2e%2e/india/x")
    assert not is_factchecker("https://www.thequint.com/news/webqoof/../../sports")

def test_factcheckers_are_not_official_and_vice_versa():
    assert not is_official("https://www.boomlive.in/x") and not is_official("https://www.indiatoday.in/fact-check/x")
    assert not is_factchecker("https://pib.gov.in/x") and not is_factchecker("https://www.rbi.org.in/")

def test_brave_factchecker_query_lists_the_new_whole_site_hosts():
    for d in WHOLE_SITE:
        assert f"site:{d}" in R.BraveRetriever.FC_Q
    assert "site:bank.in" in R.BraveRetriever.OFFICIAL_Q

# --- Fact Check Tools retriever
class _Resp:
    def __init__(self, body, status=200):
        self.status = status; self._b = body if isinstance(body, bytes) else json.dumps(body).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1): return self._b

class _Opener:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []
    def __call__(self, req, timeout=None):
        self.calls.append((req.full_url, timeout))
        if self.exc: raise self.exc
        return self.resp

def _review(url, title="Fact check: Rs 1000 for every woman is fake", pub="BOOM", rating="False", date="2026-05-01T00:00:00Z"):
    return {"publisher": {"name": pub, "site": "x"}, "url": url, "title": title, "reviewDate": date, "textualRating": rating, "languageCode": "en"}

def _claim(text, *reviews, claimant="Viral post"):
    return {"text": text, "claimant": claimant, "claimDate": "2026-04-30T00:00:00Z", "claimReview": list(reviews)}

KEY = "SECRET-KEY-123"
Q = "Government will give Rs 1000 to every woman under Mahila Sahayata Yojana"
GOOD = _claim("Government giving Rs 1000 to every woman under Mahila Sahayata Yojana", _review("https://www.boomlive.in/fact-check/mahila-1000"))

def test_request_shape_and_result_mapping():
    op = _Opener(_Resp({"claims": [GOOD]}))
    out = FactCheckToolsRetriever(key=KEY, opener=op).search(Q)
    url, timeout = op.calls[0]
    assert url.startswith(ENDPOINT + "?") and timeout == 6 and len(op.calls) == 1
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(url).query)
    assert qs["query"] == [Q] and qs["languageCode"] == ["en"] and qs["pageSize"] == ["8"] and qs["key"] == [KEY]
    assert len(out) == 1
    e = out[0]
    assert e.tier == TIER_FACTCHECKER and e.source_name == "BOOM" and e.url == "https://www.boomlive.in/fact-check/mahila-1000"
    assert e.title.startswith("Fact check") and "Rating: False" in e.text and "Claimant: Viral post" in e.text
    assert "Claim reviewed: Government giving Rs 1000" in e.text and "Reviewed: 2026-05-01" in e.text
    assert e.fetched_at.endswith("+00:00") and KEY not in (e.url + e.text + e.title + e.source_name)

def test_language_code_follows_the_script_and_can_be_overridden():
    op = _Opener(_Resp({"claims": []}))
    r = FactCheckToolsRetriever(key=KEY, opener=op)
    r.search("ప్రభుత్వం ప్రతి మహిళకు వెయ్యి రూపాయలు ఇస్తుంది అని వార్త")
    r.search("सरकार हर महिला को हजार रुपये दे रही है यह खबर झूठ")
    r.search(Q, language="hi")
    from urllib.parse import urlparse, parse_qs
    assert [parse_qs(urlparse(u).query)["languageCode"][0] for u, _ in op.calls] == ["te", "hi", "hi"]

def test_tier_is_always_factchecker_and_only_listed_publishers_survive():
    claim = _claim("Government giving Rs 1000 to every woman under Mahila Sahayata Yojana",
                   _review("https://factcheck.pib.gov.in/x", pub="PIB Fact Check"),               # official domain: still not on the list
                   _review("https://www.randomblog.com/fake"), _review("http://www.boomlive.in/http-only"),
                   _review("https://boomlive.in.evil.com/x"), _review("https://www.altnews.in/mahila-1000", pub="Alt News"),
                   _review("https://www.indiatoday.in/fact-check/story/mahila-1000", pub="India Today"),
                   _review("https://www.indiatoday.in/india/story/mahila-1000", pub="India Today"))
    out = FactCheckToolsRetriever(key=KEY, opener=_Opener(_Resp({"claims": [claim]}))).search(Q)
    assert {e.url for e in out} == {"https://www.altnews.in/mahila-1000", "https://www.indiatoday.in/fact-check/story/mahila-1000"}
    assert all(e.tier == TIER_FACTCHECKER for e in out)

def test_irrelevant_results_are_dropped_and_cap_is_three():
    other = _claim("Aliens landed in Pune last night", _review("https://www.boomlive.in/aliens", title="Aliens in Pune? No"))
    many = [_claim(f"Government giving Rs 1000 to every woman under Mahila Sahayata Yojana v{i}", _review(f"https://www.boomlive.in/f/{i}")) for i in range(6)]
    out = FactCheckToolsRetriever(key=KEY, opener=_Opener(_Resp({"claims": [other] + many}))).search(Q)
    assert len(out) == 3 and all("aliens" not in e.url for e in out)
    assert FactCheckToolsRetriever(key=KEY, opener=_Opener(_Resp({"claims": [other]}))).search(Q) == []
    dup = _claim("Government giving Rs 1000 to every woman under Mahila Sahayata Yojana", _review("https://www.boomlive.in/a"), _review("https://www.boomlive.in/a"))
    assert len(FactCheckToolsRetriever(key=KEY, opener=_Opener(_Resp({"claims": [dup]}))).search(Q)) == 1

@pytest.mark.parametrize("op", [
    _Opener(exc=urllib.error.HTTPError(ENDPOINT + "?key=" + KEY, 429, "quota", {}, io.BytesIO(b"{}"))),
    _Opener(exc=urllib.error.HTTPError(ENDPOINT + "?key=" + KEY, 403, "bad key", {}, io.BytesIO(b"{}"))),
    _Opener(exc=TimeoutError("timed out")), _Opener(exc=urllib.error.URLError("dns " + KEY)), _Opener(exc=RuntimeError(KEY)),
    _Opener(_Resp({"claims": [GOOD]}, status=500)), _Opener(_Resp(b"not json")), _Opener(_Resp(b"")), _Opener(_Resp([1, 2])),
    _Opener(_Resp({"error": {"code": 429, "message": "Quota exceeded"}})), _Opener(_Resp({"claims": "x"})),
    _Opener(_Resp({"claims": [None, 5, {"claimReview": "x"}, {"claimReview": [None, {"url": 7}, {"url": "https://www.boomlive.in/z"}]}]})),
])
def test_every_failure_mode_returns_empty_list_without_raising(op):
    assert FactCheckToolsRetriever(key=KEY, opener=op).search(Q) == []

def test_disabled_without_key_and_blank_query(monkeypatch):
    monkeypatch.delenv("GOOGLE_FACTCHECK_API_KEY", raising=False)
    op = _Opener(_Resp({"claims": [GOOD]}))
    assert FactCheckToolsRetriever(opener=op).search(Q) == [] and op.calls == []
    assert FactCheckToolsRetriever(key=KEY, opener=op).search("   ") == [] and op.calls == []

def test_default_retrievers_wiring(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False); monkeypatch.delenv("GOOGLE_FACTCHECK_API_KEY", raising=False)
    assert [type(r).__name__ for r in R.default_retrievers()] == ["PibRetriever"]
    monkeypatch.setenv("GOOGLE_FACTCHECK_API_KEY", KEY)
    assert [type(r).__name__ for r in R.default_retrievers()] == ["PibRetriever", "FactCheckToolsRetriever"]
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    assert [type(r).__name__ for r in R.default_retrievers()] == ["PibRetriever", "BraveRetriever", "FactCheckToolsRetriever"]

@pytest.mark.parametrize("stance", ["contradicts", "confirms", "mixed"])
def test_factchecker_evidence_alone_can_never_decide_a_verdict(stance):
    ev = FactCheckToolsRetriever(key=KEY, opener=_Opener(_Resp({"claims": [GOOD]}))).search(Q)
    ev[0].stance = stance
    v = decide(Claim(Q), ev)
    assert v.verdict == UNVERIFIED and v.reason_code == "factchecker_only"
    assert [c["tier"] for c in v.citations] == [TIER_FACTCHECKER] and v.citations[0]["url"].startswith("https://www.boomlive.in/")

def test_factchecker_citation_rides_along_but_does_not_change_an_official_verdict():
    fc = FactCheckToolsRetriever(key=KEY, opener=_Opener(_Resp({"claims": [GOOD]}))).search(Q)
    fc[0].stance = "confirms"
    off = Evidence("PIB", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_OFFICIAL, TS, "t", "x", "contradicts")
    v = decide(Claim(Q), [off] + fc)
    assert v.verdict == "FALSE" and v.reason_code == "official_contradiction"
