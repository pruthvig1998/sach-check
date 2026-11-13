"""GROUNDED work package: Gemini on Vertex with Grounding with Google Search as a web-search provider. Fully offline: fake openers only."""
import io, json, os, pathlib, sys, threading, urllib.error
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from sach import search as S, status, vertex as V, retrieve as R
from sach.search import GroundedSearch, SearchChain, SearchRun, resolve_redirect, public_https_url
from test_vertex import rsa, sa, _sa_json, Resp, http_error, FakeGoogle, PROJECT   # noqa: F401  (rsa, sa are fixtures)

RD = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
PIB = "https://pib.gov.in/PressReleasePage.aspx?PRID=1"


def redirect_err(loc, code=302):
    class H(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)
    return urllib.error.HTTPError("x", code, "Found", H({"Location": loc} if loc is not None else {}), io.BytesIO(b""))


class Redirects:
    """No-follow opener fake: maps a redirect token to a Location (or an exception); records every URL it is asked for."""
    def __init__(self, table):
        self.table, self.asked, self.reqs = table, [], []
        self.lock = threading.Lock()
    def __call__(self, req, timeout=None):
        with self.lock:
            self.asked.append(req.full_url)
            self.reqs.append(req)
        v = self.table.get(req.full_url)
        if isinstance(v, Exception):
            raise v
        raise redirect_err(v)


class Gen(FakeGoogle):
    """Token + generateContent fake whose reply carries grounding chunks."""
    def __init__(self, chunks, **kw):
        super().__init__(**kw)
        self.chunks = chunks
    def __call__(self, req, timeout=None):
        if req.full_url == V.TOKEN_URL or self.gen_error:
            return super().__call__(req, timeout)
        with self.lock:
            self.reqs.append(req)
        return Resp({"candidates": [{"content": {"parts": [{"text": "prose to ignore"}]},
                                     "groundingMetadata": {"webSearchQueries": ["q"], "groundingChunks": [
                                         {"web": {"title": t, "uri": u}} for t, u in self.chunks]}}]})


def make(sa, chunks, table, **kw):
    g = Gen(chunks)
    client = V.VertexClient(sa, V.TokenProvider(sa, g), g)
    rd = Redirects(table)
    return GroundedSearch(client, opener=rd, **kw), g, rd


def chunks_for(*pairs):
    return [(t, RD + str(i)) for i, (t, _) in enumerate(pairs)], {RD + str(i): loc for i, (_, loc) in enumerate(pairs)}


# ---------------------------------------------------------------- request body, parsing
def test_request_body_and_endpoint(sa):
    ch, tb = chunks_for(("pib.gov.in", PIB))
    gs, g, rd = make(sa, ch, tb)
    assert gs.search("site:pib.gov.in Mahila Yojana Rs 5000") == [PIB]
    req = g.gen_calls()[0]
    assert req.full_url == "https://aiplatform.googleapis.com/v1/projects/%s/locations/global/publishers/google/models/gemini-3.1-flash-lite:generateContent" % PROJECT
    body = json.loads(req.data)
    assert body["tools"] == [{"google_search": {}}]
    txt = body["contents"][0]["parts"][0]["text"]
    assert txt.startswith("Find official Indian government sources") and txt.endswith("Claim: Mahila Yojana Rs 5000")
    assert req.get_header("Authorization").startswith("Bearer ")

def test_model_from_env(sa, monkeypatch):
    monkeypatch.setenv("SACH_GROUNDED_MODEL", "gemini-9-test")
    gs, g, _ = make(sa, [], {})
    gs.search("a claim")
    assert "models/gemini-9-test:generateContent" in g.gen_calls()[0].full_url
    monkeypatch.setenv("SACH_GROUNDED_MODEL", "bad model/../x")
    assert V.grounded_model() == "gemini-3.1-flash-lite"

def test_parse_chunks_tolerates_bad_shapes():
    assert V.grounded_chunks({}) == [] and V.grounded_chunks({"candidates": []}) == []
    assert V.grounded_chunks({"candidates": [{"groundingMetadata": {"groundingChunks": [{"x": 1}, {"web": {"uri": 5}}, None,
                                                                                         {"web": {"uri": "u", "title": "t"}}]}}]}) == [("t", "u")]

# ---------------------------------------------------------------- redirect resolution and safety
def test_resolve_reads_location_without_following():
    rd = Redirects({RD + "a": PIB})
    assert resolve_redirect(RD + "a", rd) == PIB
    assert rd.asked == [RD + "a"]

def test_only_the_vertex_redirect_host_is_ever_requested():
    rd = Redirects({})
    for u in ("https://evil.example.com/grounding-api-redirect/x", "http://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
              "https://vertexaisearch.cloud.google.com.evil.com/grounding-api-redirect/x", "https://vertexaisearch.cloud.google.com@evil.com/grounding-api-redirect/x",
              "https://vertexaisearch.cloud.google.com:8443/grounding-api-redirect/x", "https://vertexaisearch.cloud.google.com/other/x", "", "https://pib.gov.in/"):
        assert resolve_redirect(u, rd) == ""
    assert rd.asked == []

@pytest.mark.parametrize("loc", ["http://pib.gov.in/x", "https://127.0.0.1/x", "https://10.0.0.5/x", "https://169.254.169.254/latest", "https://[::1]/x",
                                 "https://localhost/x", "https://intranet/x", "https://box.internal/x", "https://user@pib.gov.in/x",
                                 "https://pib.gov.in\\@evil.com/", "javascript:alert(1)", "", None])
def test_unsafe_locations_dropped(loc):
    assert resolve_redirect(RD + "a", Redirects({RD + "a": loc})) == ""

def test_non_redirect_status_and_failures_drop():
    assert resolve_redirect(RD + "a", Redirects({RD + "a": http_error(500)})) == ""
    assert resolve_redirect(RD + "a", Redirects({RD + "a": TimeoutError()})) == ""
    assert resolve_redirect(RD + "a", Redirects({RD + "a": urllib.error.URLError("boom")})) == ""
    class Ok:                                                  # a 200 (no redirect) is not a usable answer
        status, headers = 200, {}
        def close(self): pass
    assert resolve_redirect(RD + "a", lambda req, timeout=None: Ok()) == ""

def test_returned_3xx_response_also_works():
    class R3:
        status, headers = 302, {"Location": PIB}
        def close(self): pass
    assert resolve_redirect(RD + "a", lambda req, timeout=None: R3()) == PIB

def test_relative_location_is_joined_then_checked():
    # a relative Location lands on the redirect host itself: public https, so the resolver returns it; the trust filter rejects it
    assert resolve_redirect(RD + "a", Redirects({RD + "a": "/x"})) == "https://vertexaisearch.cloud.google.com/x"

def test_public_https_url():
    assert public_https_url("https://pib.gov.in/x") and not public_https_url("ftp://pib.gov.in/")
    assert public_https_url("https://8.8.8.8/")                       # a global IP literal is public; the trust filter will drop it

def test_failure_drops_only_that_url(sa):
    ch, tb = chunks_for(("pib.gov.in", PIB), ("mha.gov.in", TimeoutError()), ("mohfw.gov.in", "https://mohfw.gov.in/a"))
    gs, g, rd = make(sa, ch, tb)
    assert gs.search("claim text") == [PIB, "https://mohfw.gov.in/a"]

def test_resolution_is_parallel_but_capped_at_six(sa, monkeypatch):
    live, peak, lock = [0], [0], threading.Lock()
    ev = threading.Event()
    def opener(req, timeout=None):
        with lock:
            live[0] += 1; peak[0] = max(peak[0], live[0])
        ev.wait(0.05)
        with lock:
            live[0] -= 1
        raise redirect_err("https://pib.gov.in/p" + req.full_url[-2:])
    ch = [("pib.gov.in", RD + "%02d" % i) for i in range(12)]
    g = Gen(ch)
    gs = GroundedSearch(V.VertexClient(sa, V.TokenProvider(sa, g), g), opener=opener)
    assert len(gs.search("claim", count=20)) == 12
    assert 1 < peak[0] <= S.RESOLVE_WORKERS == 6

# ---------------------------------------------------------------- trust filter
def test_official_filter_drops_news_keeps_pib_and_factcheckers(sa):
    ch, tb = chunks_for(("pib.gov.in", PIB), ("timesofindia.indiatimes.com", "https://timesofindia.indiatimes.com/a"),
                        ("boomlive.in", "https://www.boomlive.in/fact-check/x"), ("evil.com", "https://evil.com/pib.gov.in"),
                        ("pib.gov.in", "https://pib.gov.in.evil.com/x"), ("indiatoday.in", "https://www.indiatoday.in/news/x"),
                        ("rbi.org.in", "https://rbi.org.in/y"), ("x", "https://8.8.8.8/z"), ("pib.gov.in", PIB))
    gs, g, rd = make(sa, ch, tb)
    assert gs.search("claim") == [PIB, "https://www.boomlive.in/fact-check/x", "https://rbi.org.in/y"]
    # a title that is a plainly untrusted domain is not even resolved (fewer requests to Google)
    assert RD + "0" in rd.asked and RD + "1" not in rd.asked

def test_relative_redirect_to_non_official_is_filtered(sa):
    ch, tb = chunks_for(("pib.gov.in", "/grounding-api-redirect/zzz"))
    gs, _, _ = make(sa, ch, tb)
    assert gs.search("claim") == []

def test_prose_is_ignored(sa):
    gs, g, rd = make(sa, [], {})
    assert gs.search("claim") == []

# ---------------------------------------------------------------- chain order and fallthrough
class Fake:
    def __init__(self, name, *script):
        self.name, self.script, self.calls = name, list(script), []
    def search(self, query, count=8):
        self.calls.append(query)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item

class FakeGrounded(Fake):
    fallthrough_empty = True
    auth_pause_s = V.AUTH_PAUSE_S

class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t

def test_order_defaults_grounded_first_only_when_credential_set(rsa, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "bk"); monkeypatch.setenv("TAVILY_API_KEY", "tk")
    assert [p.name for p in SearchChain.from_env().providers] == ["brave", "tavily"]
    monkeypatch.setenv("GOOGLE_SA_JSON", _sa_json(rsa))
    assert [p.name for p in SearchChain.from_env().providers] == ["grounded", "brave", "tavily"]
    monkeypatch.setenv("SACH_SEARCH_ORDER", "tavily,brave")
    assert [p.name for p in SearchChain.from_env().providers] == ["tavily", "brave", "grounded"]
    monkeypatch.setenv("SACH_SEARCH_ORDER", "brave,grounded,tavily")
    assert [p.name for p in SearchChain.from_env().providers] == ["brave", "grounded", "tavily"]

def test_off_without_credential_and_with_a_broken_one(monkeypatch):
    assert SearchChain.from_env().providers == [] and not SearchChain.from_env().configured
    monkeypatch.setenv("GOOGLE_SA_JSON", "garbage!!")
    assert SearchChain.from_env().providers == []                         # no error, just off
    monkeypatch.setenv("GOOGLE_SA_JSON", "")
    assert not [r for r in R.default_retrievers() if type(r).__name__ == "BraveRetriever"]

def test_sa_alone_enables_web_search_retriever(rsa, monkeypatch):
    monkeypatch.setenv("GOOGLE_SA_JSON", _sa_json(rsa))
    assert [r for r in R.default_retrievers() if type(r).__name__ == "BraveRetriever"]

def test_grounded_hit_stops_the_chain():
    g, b = FakeGrounded("grounded", [PIB]), Fake("brave", ["https://x.gov.in/"])
    run = SearchRun()
    assert SearchChain([g, b]).search("q", run=run) == [PIB] and b.calls == [] and run.provider == "grounded"

def test_empty_grounded_falls_through_to_next_provider():
    g, b = FakeGrounded("grounded", []), Fake("brave", ["https://x.gov.in/"])
    run = SearchRun()
    assert SearchChain([g, b]).search("q", run=run) == ["https://x.gov.in/"] and run.provider == "brave" and run.status == "ok"

def test_empty_grounded_alone_is_an_honest_ok_answer_when_next_fails():
    g, b = FakeGrounded("grounded", []), Fake("brave", http_error(500))
    run = SearchRun()
    assert SearchChain([g, b]).search("q", run=run) == [] and run.status == "ok" and run.provider == "grounded"

def test_all_failing_is_down():
    run = SearchRun()
    assert SearchChain([FakeGrounded("grounded", TimeoutError()), Fake("brave", http_error(500))]).search("q", run=run) == [] and run.status == "down"

@pytest.mark.parametrize("code", [401, 403])
def test_auth_failure_pauses_grounded_ten_minutes(code):
    clk = Clock()
    g, b = FakeGrounded("grounded", V.VertexError("x", code)), Fake("brave", ["https://a.gov.in/"])
    ch = SearchChain([g, b], clock=clk)
    assert ch.search("q") == ["https://a.gov.in/"]
    assert ch.paused_until("grounded") == clk.t + 600
    ch.search("q"); assert len(g.calls) == 1                                # paused: skipped without a call
    clk.t += 601
    ch.search("q"); assert len(g.calls) == 2

def test_429_uses_retry_after_and_5xx_timeout_do_not_pause():
    clk = Clock()
    g = FakeGrounded("grounded", V.VertexError("x", 429, {"retry-after": "30"}))
    ch = SearchChain([g, Fake("brave", ["u"])], clock=clk)
    ch.search("q"); assert ch.paused_until("grounded") == clk.t + 30
    for err in (V.VertexError("x", 503), TimeoutError(), V.VertexError("x")):
        g2 = FakeGrounded("grounded", err); ch2 = SearchChain([g2, Fake("brave", ["u"])], clock=clk)
        assert ch2.search("q") == ["u"] and ch2.paused_until("grounded") == 0.0

def test_real_provider_errors_are_classified(sa):
    g = Gen([]); g.gen_error = http_error(403)
    gs = GroundedSearch(V.VertexClient(sa, V.TokenProvider(sa, g), g))
    clk = Clock(); ch = SearchChain([gs, Fake("brave", ["u"])], clock=clk)
    assert ch.search("q") == ["u"] and ch.paused_until("grounded") == clk.t + 600
    g2 = Gen([]); g2.gen_error = http_error(429, headers={"retry-after": "42"})
    ch2 = SearchChain([GroundedSearch(V.VertexClient(sa, V.TokenProvider(sa, g2), g2))], clock=clk)
    ch2.search("q"); assert ch2.paused_until("grounded") == clk.t + 42

# ---------------------------------------------------------------- daily cap
def test_cap_counts_only_real_calls_and_pauses_to_utc_midnight(sa, monkeypatch):
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "2")
    ch1, tb = chunks_for(("pib.gov.in", PIB))
    now = 86400 * 100 + 3600.0
    gs, g, _ = make(sa, ch1, tb, clock=lambda: now)
    assert gs.search("one") == [PIB] and gs.search("one") == [PIB]           # second is cached: one billed call
    assert V.grounded_usage(now=now)["calls_today"] == 1
    gs.search("two")
    with pytest.raises(S.SearchPaused) as ei:
        gs.search("three")
    assert ei.value.pause_s == 86400 - 3600 and len(g.gen_calls()) == 2
    u = V.grounded_usage(now=now)
    assert u["calls_today"] == 2 and u["max_per_day"] == 2 and u["skipped_over_cap_today"] == 1
    assert V.usage(now=now)["calls_today"] == 0                              # the judge cap is a separate counter
    clk = Clock(); clk.t = now
    chain = SearchChain([gs, Fake("brave", ["u"])], clock=clk)
    assert chain.search("four") == ["u"] and chain.paused_until("grounded") == now + 82800

def test_cap_zero_is_unlimited_and_default_is_400(sa, monkeypatch):
    assert V.grounded_max_per_day() == 400
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "0")
    gs, g, _ = make(sa, [], {})
    for i in range(5):
        gs.search("claim %d" % i)
    assert len(g.gen_calls()) == 5

# ---------------------------------------------------------------- status, secrets
def test_status_rows(sa, monkeypatch):
    gs, _, _ = make(sa, [], {})
    class Ret:
        chain = SearchChain([gs, Fake("brave", ["u"])])
    rows = {r["provider"]: r for r in status.search_providers([Ret()])}
    assert rows["grounded"]["configured"] and rows["grounded"]["state"] == "ready" and rows["grounded"]["max_per_day"] == 400
    gs.search("one claim")
    rows = {r["provider"]: r for r in status.search_providers([Ret()])}
    assert rows["grounded"]["calls_today"] == 1
    Ret.chain._pause("grounded", 100)
    rows = {r["provider"]: r for r in status.search_providers([Ret()])}
    assert rows["grounded"]["state"] == "paused" and rows["grounded"]["paused_for_s"] > 0
    from sach import limits
    limits.reset_memory()
    off = {r["provider"]: r for r in status.search_providers([])}
    assert off["grounded"]["configured"] is False and off["grounded"]["state"] == "off" and off["grounded"]["calls_today"] == 0
    page = status.status_page({**status.status_data(None, [Ret()]), }).decode()
    assert "grounded" in page and "Calls today" in page

def test_no_secret_in_errors_repr_or_urls(sa):
    g = Gen([]); g.gen_error = http_error(500, body=b"Bearer ya29.LEAK private_key")
    gs = GroundedSearch(V.VertexClient(sa, V.TokenProvider(sa, g), g))
    with pytest.raises(V.VertexError) as ei:
        gs.search("claim")
    blob = repr(gs) + str(ei.value) + repr(ei.value.__dict__)
    assert "ya29" not in blob and "PRIVATE" not in blob and "LEAK" not in blob
    ch, tb = chunks_for(("pib.gov.in", PIB))
    gs2, g2, rd = make(sa, ch, tb)
    gs2.search("claim")
    assert rd.reqs and all(r.get_header("Authorization") is None and r.get_method() == "GET" for r in rd.reqs)   # the token never goes to the redirect host
