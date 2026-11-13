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

@pytest.mark.parametrize("loc", ["https://pib.gov.in:8443/", "https://pib.gov.in:80/", "https://pib.gov.in:0/", "https://pib.gov.in:8443/PressReleasePage.aspx?PRID=1"])
def test_location_on_a_non_default_port_is_dropped(loc):
    assert resolve_redirect(RD + "a", Redirects({RD + "a": loc})) == ""

@pytest.mark.parametrize("loc", ["https://pib.gov.in/", "https://pib.gov.in:443/", PIB])
def test_location_on_default_https_port_is_kept(loc):
    assert resolve_redirect(RD + "a", Redirects({RD + "a": loc})) == loc

def test_public_https_url_port_rule():
    assert public_https_url("https://pib.gov.in/") == "https://pib.gov.in/"
    assert public_https_url("https://pib.gov.in:443/") == "https://pib.gov.in:443/"
    assert public_https_url("https://pib.gov.in:8443/") == ""
    assert public_https_url("https://pib.gov.in:abc/") == ""

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

@pytest.mark.parametrize("host", ["127.1", "0x7f.0.0.1", "0177.0.0.1", "2130706433", "0x7f000001", "1.2.3", "10.1", "0x7f.1",
                                  "08.8.8.8", "1.2.3.4.5", "0xab", "1.0x7f", "a..b", "0x", "127.0.0.1", "10.0.0.1", "192.168.1.1"])
def test_numeric_looking_or_non_global_hosts_are_rejected(host):
    assert public_https_url("https://%s/x" % host) == ""

@pytest.mark.parametrize("url", ["https://pib.gov.in/", "https://mohfw.gov.in/a", "https://8.8.8.8/", "https://[2606:4700:4700::1111]/",
                                 "https://www.rbi.org.in/x", "https://dlas1.ucloud.int/"])
def test_real_hostnames_and_global_literals_are_accepted(url):
    assert public_https_url(url) == url

def test_docs_section_10_matches_the_code():
    text = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "scaling.md").read_text(encoding="utf-8")
    sec = text[text.index("## 10. Grounded search"):]
    sec = sec[:sec.index("\n## ", 5)] if "\n## " in sec[5:] else sec
    assert "give" not in sec.lower() and "released" not in sec.lower()          # the give-back mechanism is removed
    assert "up to three queries" not in sec and "four" in sec                  # PIB short, PIB keyword, official, fact-checker
    assert "per Google's published pricing as read on 2026-11-13; unverified by us" in sec
    assert "observed 3.5-5 s in one manual test on 2026-11-13 (not a guarantee)" in sec
    assert "3.5-5 s" not in sec.replace("observed 3.5-5 s", "")

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

def test_empty_grounded_is_not_ok_when_the_next_provider_fails():
    g, b = FakeGrounded("grounded", []), Fake("brave", http_error(500))
    run = SearchRun()
    assert SearchChain([g, b]).search("q", run=run) == [] and run.status == "down" and run.provider == ""

def test_empty_grounded_with_brave_500_and_tavily_timeout_is_down_like_without_grounded():
    # the exact repro: grounded answered with nothing, both later providers raised
    run = SearchRun()
    assert SearchChain([FakeGrounded("grounded", []), Fake("brave", http_error(500)), Fake("tavily", TimeoutError())]).search("q", run=run) == []
    assert run.status == "down"
    no_g = SearchRun()
    assert SearchChain([Fake("brave", http_error(500)), Fake("tavily", TimeoutError())]).search("q", run=no_g) == []
    assert no_g.status == "down" and run.status == no_g.status

def test_empty_grounded_as_the_only_provider_is_an_honest_ok():
    run = SearchRun()
    assert SearchChain([FakeGrounded("grounded", [])]).search("q", run=run) == [] and run.status == "ok" and run.provider == "grounded"

@pytest.mark.parametrize("later", [
    [Fake("brave", http_error(500))], [Fake("brave", TimeoutError())], [Fake("brave", http_error(403))],
    [Fake("brave", [])], [Fake("brave", ["https://x.gov.in/"])],
    [Fake("brave", TimeoutError()), Fake("tavily", [])], [Fake("brave", TimeoutError()), Fake("tavily", ["https://y.gov.in/"])],
])
def test_empty_grounded_status_matches_the_chain_without_grounded(later):
    # whatever the later providers do, the status with an empty grounded answer in front equals the status without grounded
    def build(providers):
        return SearchChain(providers, clock=Clock())
    with_g, without_g = SearchRun(), SearchRun()
    urls_g = build([FakeGrounded("grounded", [])] + [Fake(p.name, *p.script) for p in later]).search("q", run=with_g)
    urls_n = build([Fake(p.name, *p.script) for p in later]).search("q", run=without_g)
    assert urls_g == urls_n and with_g.status == without_g.status and with_g.provider == without_g.provider

def test_paused_later_provider_counts_as_not_answering():
    clk = Clock()
    b = Fake("brave", ["https://x.gov.in/"])
    ch = SearchChain([FakeGrounded("grounded", []), b], clock=clk)
    ch._pause("brave", 100)                                   # brave skipped without a call: it did not answer
    run = SearchRun()
    assert ch.search("q", run=run) == [] and run.status == "down" and b.calls == []

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

def test_cap_zero_is_unlimited_and_default_is_160(sa, monkeypatch):
    assert V.grounded_max_per_day() == 160
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "0")
    gs, g, _ = make(sa, [], {})
    for i in range(5):
        gs.search("claim %d" % i)
    assert len(g.gen_calls()) == 5

def test_default_grounded_cap_is_about_the_monthly_allowance_per_day():
    assert V.GROUNDED_DEFAULT_MAX_PER_DAY == 160 and V.GROUNDED_DEFAULT_MAX_PER_DAY * 30 <= 5000

def _cap_setup(sa, cap, monkeypatch, *, token_error=None, gen_error=None, chunks=None):
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", str(cap))
    now = 86400 * 50 + 10.0
    clk = [now]
    ch, tb = chunks_for(("pib.gov.in", PIB)) if chunks is None else chunks
    g = Gen(ch)
    g.token_error, g.gen_error = token_error, gen_error
    tp = V.TokenProvider(sa, g, clock=lambda: clk[0])
    gs = GroundedSearch(V.VertexClient(sa, tp, g), opener=Redirects(tb), clock=lambda: now)
    return gs, g, clk, now

def test_three_failed_token_attempts_do_not_exhaust_a_cap_of_three(sa, monkeypatch):
    gs, g, clk, now = _cap_setup(sa, 3, monkeypatch, token_error=http_error(500))
    for _ in range(3):
        with pytest.raises(V.VertexError):
            gs.search("claim")
    assert V.grounded_usage(now=now)["calls_today"] == 0 and V.grounded_usage(now=now)["skipped_over_cap_today"] == 0
    assert g.gen_calls() == []                                    # no generateContent without a token
    g.token_error = None
    clk[0] += 31                                                  # past the token's failed-refresh window
    for i in range(3):
        assert gs.search("claim %d" % i) == [PIB]
    assert V.grounded_usage(now=now)["calls_today"] == 3
    with pytest.raises(S.SearchPaused):
        gs.search("claim 9")

@pytest.mark.parametrize("err", [TimeoutError(), urllib.error.URLError("boom"), http_error(500), http_error(503),
                                 http_error(401), http_error(403), http_error(429), http_error(400), http_error(404)])
def test_every_failed_generate_call_counts_against_the_cap(sa, monkeypatch, err):
    # no give-back: a call that reached the reserve step is counted, whatever its outcome (conservative)
    gs, g, clk, now = _cap_setup(sa, 1, monkeypatch, gen_error=err)
    with pytest.raises(Exception):
        gs.search("claim")
    assert V.grounded_usage(now=now)["calls_today"] == 1
    g.gen_error = None
    with pytest.raises(S.SearchPaused):
        gs.search("claim 2")                                       # the slot was used up by the failed call
    assert len(g.gen_calls()) == 1 and V.grounded_usage(now=now)["calls_today"] == 1

def test_successful_call_stays_counted(sa, monkeypatch):
    gs, g, clk, now = _cap_setup(sa, 5, monkeypatch)
    assert gs.search("claim") == [PIB]
    assert V.grounded_usage(now=now)["calls_today"] == 1

def test_give_back_mechanism_is_gone():
    for name in ("release_grounded", "not_billed", "_release"):
        assert not hasattr(V, name)

def test_reserve_grounded_then_over_cap_leaves_the_count_at_the_cap(monkeypatch):
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "2")
    now = 86400 * 60 + 5.0
    V.reserve_grounded(None, now); V.reserve_grounded(None, now)
    with pytest.raises(V.VertexCapReached):
        V.reserve_grounded(None, now)
    assert V.grounded_usage(now=now)["calls_today"] == 2 and V.grounded_usage(now=now)["skipped_over_cap_today"] == 1
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "0")
    for _ in range(3):
        V.reserve_grounded(None, now)                             # unlimited: nothing counted, nothing raised
    assert V.grounded_usage(now=now)["calls_today"] == 2

def test_over_cap_never_decrements_a_store_it_did_not_increment(monkeypatch):
    # the remote store is healthy and already counted call A; call B's remote incr fails, so B is counted in memory and over the cap.
    # Undoing B must not touch the remote counter (old code decremented the remote store and drove it to 0).
    from test_scale import FakeStore
    from sach import limits
    class FailOnce(FakeStore):
        fail_next = False
        def incr(self, name, by=1):
            if self.fail_next:
                self.fail_next = False
                return 0                                          # one failed remote increment, then healthy again
            return super().incr(name, by)
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "1")
    now = 86400 * 70 + 9.0
    key = "gr:d:%d" % int(now // 86400)
    limits.reset_memory()
    st = FailOnce()
    V.reserve_grounded(st, now)                                   # call A: remote count 1
    st.fail_next = True
    limits._mem_incr(key, 5)                                      # memory already over the cap, so call B is rejected
    with pytest.raises(V.VertexCapReached):
        V.reserve_grounded(st, now)                               # call B: remote incr fails, memory fallback, rejected
    assert st.counters([key])[key] == 1                           # the healthy remote counter still says one call
    limits.reset_memory()

def test_counter_never_goes_below_zero_under_threads_and_memory_resets(monkeypatch):
    import threading
    from sach import limits
    monkeypatch.setenv("SACH_GROUNDED_MAX_PER_DAY", "3")
    monkeypatch.setattr(V.store, "get_store", lambda: None)       # no shared store: the in-memory fallback
    now = 86400 * 80 + 1.0
    key = "gr:d:%d" % int(now // 86400)
    limits.reset_memory()
    ok, low, lock = [], [0], threading.Lock()
    stop = threading.Event()

    def reset_loop():
        while not stop.is_set():
            limits.reset_memory()

    def worker():
        for _ in range(40):
            try:
                V.reserve_grounded(None, now)
                with lock: ok.append(1)
            except V.VertexCapReached:
                pass
            with limits._mem_lock:
                with lock: low[0] = min(low[0], limits._mem.get(key, 0))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert low[0] >= 0                                            # sampled after every call, no reset running
    assert V.grounded_usage(now=now)["calls_today"] == 3 and len(ok) == 3   # no resets: exactly the cap
    limits.reset_memory()
    resetter = threading.Thread(target=reset_loop)
    resetter.start()
    try:
        ts = [threading.Thread(target=worker) for _ in range(8)]
        for t in ts: t.start()
        for t in ts: t.join()
    finally:
        stop.set(); resetter.join()
    assert low[0] >= 0 and V.grounded_usage(now=now)["calls_today"] >= 0
    assert limits._mem.get(key, 0) >= 0
    limits.reset_memory()

# ---------------------------------------------------------------- status, secrets
def test_status_rows(sa, monkeypatch):
    gs, _, _ = make(sa, [], {})
    class Ret:
        chain = SearchChain([gs, Fake("brave", ["u"])])
    rows = {r["provider"]: r for r in status.search_providers([Ret()])}
    assert rows["grounded"]["configured"] and rows["grounded"]["state"] == "ready" and rows["grounded"]["max_per_day"] == 160
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

def test_check_search_reports_an_unparseable_service_account_as_such(monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_search", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_search.py")
    cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)
    monkeypatch.setenv("GOOGLE_SA_JSON", "garbage!!")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False); monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    lines = []
    bad = cs.check(out=lines.append)
    text = "\n".join(lines)
    assert "GOOGLE_SA_JSON is set but could not be parsed" in text and "no key" not in text.split("\n")[0]
    assert "No search keys" not in text                           # a set-but-broken credential is not 'off'
    assert "grounded 401/403 for 10 minutes" in text                 # grounded's auth pause is 600 s, not Brave/Tavily's 6 hours
    assert "grounded 401/403 for 6 hours" not in text
    assert bad == 1
    lines.clear(); monkeypatch.delenv("GOOGLE_SA_JSON")
    assert cs.check(out=lines.append) == 0 and "no key (set GOOGLE_SA_JSON" in "\n".join(lines)

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
