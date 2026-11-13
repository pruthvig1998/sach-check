"""Web-search failover and honest search status. Offline: fake providers and fake openers, no network, no keys."""
import importlib.util, io, json, pathlib, sys, threading, urllib.error
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sach.retrieve as R
import sach.search as S
from sach import cache, store
from sach.models import Evidence, TIER_PIB
from sach.pipeline import check_forward
from sach.search import SearchChain, SearchRun, BraveSearch, TavilySearch, combine_status
from sach.site import result_block
from test_sach import server, _post, TS            # noqa: F401  (server is a fixture)
from test_eval_set import env, run_eval, SMALL     # noqa: F401  (env is a fixture)

NOTICE = "Live web search was unavailable for this check"
CLAIM = "Government will give Rs 5000 to every woman under PM Mahila Yojana"


@pytest.fixture(autouse=True)
def _no_throttle_no_keys(monkeypatch):
    monkeypatch.setattr(S, "BRAVE_MIN_INTERVAL_S", 0.0)
    for k in ("BRAVE_API_KEY", "TAVILY_API_KEY", "SACH_SEARCH_ORDER", "SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN",
              "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR"):
        monkeypatch.delenv(k, raising=False)
    store.reset()
    yield
    store.reset()


def http(code, headers=None):
    return urllib.error.HTTPError("https://example.test/?q=x", code, "msg", headers or {}, None)


class Fake:
    """Provider whose answers are scripted: a list of URL lists or exceptions, repeated at the last item."""
    def __init__(self, name, *script):
        self.name, self.script, self.calls = name, list(script), []
    def search(self, query, count=8):
        self.calls.append(query)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


# ------------------------------------------------------------------ chain
def test_brave_402_fails_over_to_tavily_and_brave_is_paused_six_hours():
    clk = Clock()
    b, t = Fake("brave", http(402)), Fake("tavily", ["https://pib.gov.in/a"])
    ch = SearchChain([b, t], clock=clk)
    run = ch.new_run()
    assert ch.search("q1", 8, run) == ["https://pib.gov.in/a"]
    assert (run.status, run.provider) == ("ok", "tavily")
    assert ch.paused_until("brave") == clk.t + 6 * 3600
    assert ch.search("q2", 8, run) == ["https://pib.gov.in/a"]
    assert len(b.calls) == 1 and len(t.calls) == 2           # paused provider skipped without a call
    clk.t += 6 * 3600 + 1
    ch.search("q3", 8, run)
    assert len(b.calls) == 2                                  # pause over: tried again


@pytest.mark.parametrize("code", [401, 403, 432, 433])
def test_auth_and_plan_limit_errors_pause_six_hours(code):
    clk = Clock()
    b = Fake("brave", http(code))
    ch = SearchChain([b, Fake("tavily", [])], clock=clk)
    ch.search("q")
    assert ch.paused_until("brave") == clk.t + 6 * 3600


@pytest.mark.parametrize("header,expect", [({"Retry-After": "120"}, 120), ({"retry-after": "2"}, 5), ({"Retry-After": "9999"}, 600), ({}, 60), ({"Retry-After": "soon"}, 60)])
def test_429_pauses_for_retry_after_clamped(header, expect):
    clk = Clock()
    ch = SearchChain([Fake("brave", http(429, header)), Fake("tavily", ["https://x.gov.in/"])], clock=clk)
    assert ch.search("q") == ["https://x.gov.in/"]
    assert ch.paused_until("brave") == clk.t + expect


@pytest.mark.parametrize("err", [TimeoutError("t"), urllib.error.URLError("down"), http(503), http(400), ValueError("bad json")])
def test_timeouts_and_server_errors_try_next_provider_without_pause(err):
    clk = Clock()
    b, t = Fake("brave", err), Fake("tavily", ["https://pib.gov.in/z"])
    ch = SearchChain([b, t], clock=clk)
    assert ch.search("q") == ["https://pib.gov.in/z"]
    assert ch.paused_until("brave") == 0.0
    ch.search("q2")
    assert len(b.calls) == 2                                  # tried again on the next query


def test_all_providers_failing_is_down_and_empty():
    ch = SearchChain([Fake("brave", http(402)), Fake("tavily", http(503))])
    run = ch.new_run()
    assert ch.search("q1", 8, run) == [] and ch.search("q2", 8, run) == []
    assert run.status == "down" and run.provider == ""


def test_an_empty_answer_is_still_an_answer_and_partial_status():
    b = Fake("brave", [], http(503), [])
    ch = SearchChain([b])
    run = ch.new_run()
    ch.search("a", 8, run); assert run.status == "ok"
    ch.search("b", 8, run); assert run.status == "partial"
    ch.search("c", 8, run); assert run.status == "partial" and run.provider == "brave"


def test_no_keys_is_off_not_down(monkeypatch):
    ch = SearchChain.from_env()
    assert not ch.configured and ch.new_run().status == "off"
    assert ch.search("q") == []
    ret = R.BraveRetriever()
    ev, run = ret.search_with_status(CLAIM)
    assert ev == [] and run.status == "off"


def test_from_env_order_and_keys(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "bk"); monkeypatch.setenv("TAVILY_API_KEY", "tk")
    assert [p.name for p in SearchChain.from_env().providers] == ["brave", "tavily"]
    monkeypatch.setenv("SACH_SEARCH_ORDER", "tavily,brave")
    assert [p.name for p in SearchChain.from_env().providers] == ["tavily", "brave"]
    monkeypatch.setenv("SACH_SEARCH_ORDER", "tavily")
    assert [p.name for p in SearchChain.from_env().providers] == ["tavily", "brave"]       # unlisted configured providers follow
    monkeypatch.delenv("BRAVE_API_KEY")
    assert [p.name for p in SearchChain.from_env().providers] == ["tavily"]
    assert [r for r in R.default_retrievers() if type(r).__name__ == "BraveRetriever"]     # Tavily alone enables web search


def test_search_order_changes_who_is_asked_first(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "bk"); monkeypatch.setenv("TAVILY_API_KEY", "tk")
    calls = []
    def opener(req, timeout=0):
        calls.append(req.full_url.split("?")[0])
        return Resp({"results": [{"url": "https://pib.gov.in/t"}], "web": {"results": [{"url": "https://pib.gov.in/b"}]}})
    monkeypatch.setenv("SACH_SEARCH_ORDER", "tavily,brave")
    assert SearchChain.from_env(opener=opener).search("q") == ["https://pib.gov.in/t"]
    assert calls == ["https://api.tavily.com/search"]


def test_combine_status():
    assert combine_status(["ok", "ok"]) == "ok" and combine_status(["off", "off"]) == "off" and combine_status([]) == "off"
    assert combine_status(["down", "down"]) == "down" and combine_status(["ok", "down"]) == "partial"
    assert combine_status(["partial", "ok"]) == "partial" and combine_status([None, "ok"]) == "ok"


# ------------------------------------------------------------------ providers: request and response shapes
class Resp(io.BytesIO):
    def __init__(self, obj): super().__init__(json.dumps(obj).encode())
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_tavily_request_shape_and_response_parsing():
    seen = {}
    def opener(req, timeout=0):
        seen.update(url=req.full_url, method=req.get_method(), auth=req.get_header("Authorization"), body=json.loads(req.data), timeout=timeout,
                    ctype=req.get_header("Content-type"))
        return Resp({"results": [{"title": "t", "url": "https://boomlive.in/x", "content": "c", "score": 0.9}, {"title": "no url"}], "response_time": 1})
    t = TavilySearch("tvly-SECRET", opener=opener)
    assert t.search("site:boomlive.in some claim words", 8) == ["https://boomlive.in/x"]
    assert seen["url"] == "https://api.tavily.com/search" and seen["method"] == "POST"
    assert seen["auth"] == "Bearer tvly-SECRET" and seen["ctype"] == "application/json" and seen["timeout"] > 0
    assert seen["body"] == {"query": "some claim words", "max_results": 8, "search_depth": "basic", "include_domains": ["boomlive.in"]}
    assert "tvly-SECRET" not in seen["url"] and "tvly-SECRET" not in json.dumps(seen["body"])


def test_tavily_translates_site_or_groups_and_filters_by_domain():
    seen = []
    def opener(req, timeout=0):
        seen.append(json.loads(req.data))
        return Resp({"results": [{"url": "https://www.boomlive.in/a"}, {"url": "https://evil.com/b"}, {"url": "https://notboomlive.in/c"}]})
    t = TavilySearch("k", opener=opener)
    urls = t.search("some claim (site:boomlive.in OR site:newsmeter.in OR site:factly.in)", 99)
    assert seen[0]["query"] == "some claim" and seen[0]["include_domains"] == ["boomlive.in", "newsmeter.in", "factly.in"]
    assert seen[0]["max_results"] == 20 and "include_domains_mode" not in seen[0]
    assert urls == ["https://www.boomlive.in/a"]                 # hard filter re-checked locally (suffix match is by label, not substring)
    # zones (gov.in, nic.in) are not documented as domain filters: dropped from the filter, the rest only preferred
    t.search("kw words (site:gov.in OR site:nic.in OR site:who.int OR site:rbi.org.in)", 5)
    assert seen[1]["include_domains"] == ["who.int", "rbi.org.in"] and seen[1]["include_domains_mode"] == "prefer"
    assert seen[1]["query"] == "kw words"
    t.search("plain claim with no operators", 5)
    assert "include_domains" not in seen[2] and seen[2]["query"] == "plain claim with no operators"


def test_brave_search_request_unchanged_and_429_retried_once(monkeypatch):
    monkeypatch.setattr(S._time, "sleep", lambda s: None)
    reqs = []
    def opener(req, timeout=0):
        reqs.append(req)
        if len(reqs) == 1:
            raise http(429)
        return Resp({"web": {"results": [{"url": "https://pib.gov.in/a"}]}})
    assert BraveSearch("brave-SECRET", opener=opener).search("hello world", 7) == ["https://pib.gov.in/a"]
    assert reqs[0].full_url == "https://api.search.brave.com/res/v1/web/search?q=hello+world&count=7"
    assert reqs[0].get_header("X-subscription-token") == "brave-SECRET" and len(reqs) == 2


def test_keys_never_appear_in_errors_or_logs(caplog):
    def opener(req, timeout=0):
        raise http(402)
    ch = SearchChain([BraveSearch("brave-SECRET", opener=opener), TavilySearch("tvly-SECRET", opener=opener)])
    run = ch.new_run()
    assert ch.search("q", 8, run) == []                           # nothing raised to the caller
    assert "SECRET" not in caplog.text and "SECRET" not in repr(run.__dict__)
    assert "SECRET" not in repr(ch._paused)


# ------------------------------------------------------------------ BraveRetriever
def _stub_pages(monkeypatch):
    monkeypatch.setattr(R, "fetch", lambda url: {"status": 200, "final_url": url, "fetched_at": TS, "body": "<html><title>T</title><body>text</body></html>"})


def test_brave_retriever_uses_chain_and_reports_ok(monkeypatch):
    _stub_pages(monkeypatch)
    t = Fake("tavily", ["https://pib.gov.in/PressReleasePage.aspx?PRID=5"])
    r = R.BraveRetriever(key="k", chain=SearchChain([Fake("brave", http(402)), t]))
    ev, run = r.search_with_status(CLAIM)
    assert [e.url for e in ev] == ["https://pib.gov.in/PressReleasePage.aspx?PRID=5"]
    assert run.status == "ok" and run.provider == "tavily"
    assert r.search(CLAIM)                                        # plain interface still returns a list
    assert t.calls[0].startswith("site:pib.gov.in")               # same query order as before


def test_brave_retriever_down_and_partial(monkeypatch):
    _stub_pages(monkeypatch)
    r = R.BraveRetriever(key="k", chain=SearchChain([Fake("brave", http(402))]))
    ev, run = r.search_with_status("Every household will receive a free solar-powered refrigerator next month")
    assert ev == [] and run.status == "down" and run.total >= 3
    # first query answered, the rest got no answer -> partial
    r = R.BraveRetriever(key="k", chain=SearchChain([Fake("brave", [], http(503))]))
    ev, run = r.search_with_status("Every household will receive a free solar-powered refrigerator next month")
    assert run.status == "partial"


def test_parallel_claims_do_not_mix_up_statuses(monkeypatch):
    _stub_pages(monkeypatch)
    plan = {}                                                    # thread name -> "fail" | "ok"
    barrier = threading.Barrier(6)
    class Prov:
        name = "brave"
        def search(self, q, count=8):
            try: barrier.wait(timeout=0.5)                       # force the claims to overlap inside the search
            except threading.BrokenBarrierError: pass
            if plan[threading.current_thread().name] == "fail":
                raise http(503)
            return []
    r = R.BraveRetriever(key="k", chain=SearchChain([Prov()]))
    got = {}
    def work(name):
        got[name] = r.search_with_status("Every household will receive a free solar-powered refrigerator next month")[1].status
    names = [f"w{i}" for i in range(6)]
    for i, n in enumerate(names):
        plan[n] = "fail" if i % 2 else "ok"
    ths = [threading.Thread(target=work, args=(n,), name=n) for n in names]
    [t.start() for t in ths]; [t.join() for t in ths]
    assert {n: got[n] for n in names} == {n: ("down" if plan[n] == "fail" else "ok") for n in names}
    assert r._tls.__dict__.get("run") is None                    # nothing leaks into the main thread


# ------------------------------------------------------------------ pipeline / site / API / cache
class StatusRetriever:
    """Retriever reporting a scripted search status; counts calls."""
    def __init__(self, ok=True, answered=0, total=1, boom=False):
        self.ok, self.answered, self.total, self.boom, self.calls = ok, answered, total, boom, 0
    def search(self, claim): return self.search_with_status(claim)[0]
    def search_with_status(self, claim):
        self.calls += 1
        if self.boom:
            raise RuntimeError("search exploded")
        run = SearchRun(configured=self.ok is not None)
        for i in range(self.total):
            run.record(i < self.answered, "brave" if i < self.answered else None)
        return [], run


class Judge:
    failures = 0
    def stance(self, claim, title, text, tier=None): return "none"


def test_check_forward_reports_search_status():
    for r, want in [(StatusRetriever(answered=1), "ok"), (StatusRetriever(answered=0), "down"), (StatusRetriever(answered=1, total=2), "partial"),
                    (StatusRetriever(ok=None, total=0), "off"), (StatusRetriever(boom=True), "down")]:
        out = check_forward(CLAIM, [r], Judge(), log=False)
        assert out["search_status"] == want and out["degraded"] is False
    out = check_forward(CLAIM, [StatusRetriever(answered=1)], Judge(), log=False)
    assert out["search_provider"] == "brave"
    class Plain:                                                 # a retriever without status: nothing to report
        def search(self, c): return []
    assert check_forward(CLAIM, [Plain()], Judge(), log=False)["search_status"] == "off"


def test_site_notice_only_for_down_and_partial():
    def block(r):
        return result_block(check_forward(CLAIM, [r], Judge(), log=False))
    assert NOTICE in block(StatusRetriever(answered=0)) and "An UNVERIFIED result may change later." in block(StatusRetriever(answered=0))
    assert NOTICE in block(StatusRetriever(answered=1, total=2))
    assert NOTICE not in block(StatusRetriever(answered=1)) and NOTICE not in block(StatusRetriever(ok=None, total=0))


def test_json_api_includes_search_status(server):
    import sach.web as W
    W.Handler.retrievers = [StatusRetriever(answered=0)]; W.Handler.llm = Judge()
    try:
        code, body = _post(server, CLAIM, path="/?format=json")
    finally:
        W.Handler.llm = None
    assert code == 200 and json.loads(body)["search_status"] == "down"


def test_results_with_failed_search_are_not_cached():
    assert cache.storable({"verdict": "UNVERIFIED", "claims": [], "search_status": "ok"}) is True
    assert cache.storable({"verdict": "UNVERIFIED", "claims": [], "search_status": "off"}) is True
    assert cache.storable({"verdict": "UNVERIFIED", "claims": [], "search_status": "down"}) is False
    assert cache.storable({"verdict": "UNVERIFIED", "claims": [], "search_status": "partial"}) is False
    bad, good = StatusRetriever(answered=0), StatusRetriever(answered=1)
    check_forward(CLAIM, [bad], Judge()); check_forward(CLAIM, [bad], Judge())
    assert bad.calls == 2                                         # second request searched again: outage not cached
    check_forward(CLAIM + " today", [good], Judge()); check_forward(CLAIM + " today", [good], Judge())
    assert good.calls == 1                                        # healthy result is cached as before


# ------------------------------------------------------------------ evaluation and health check
def test_run_eval_marks_search_failure_as_degraded_and_uses_fallback_file(env):
    tmp, calls, mp = env
    def fake_check(text, ret, llm, log=False):
        v = {"claim one": "FALSE", "दावा दो": "TRUE", "claim three": "UNVERIFIED"}[text]
        return {"verdict": v, "search_status": "down" if text == "claim one" else "partial" if text == "दावा दो" else "ok",
                "claims": [{"reason_code": "r", "citations": [{"url": "https://pib.gov.in/x"}]}]}
    mp.setattr(run_eval, "check_forward", fake_check)
    assert run_eval.main([]) == 0
    assert not (tmp / "docs" / "evaluation.md").exists() and not (tmp / "data" / "eval_summary.json").exists()
    rep = (tmp / "docs" / "evaluation-fallback-run.md").read_text(encoding="utf-8")
    assert "web search failed for 2 claims" in rep and "degraded" in rep
    assert json.load(open(tmp / "cache" / "eval_progress.json"))["search_failures"] == 2


def test_run_eval_search_failures_survive_resume(env):
    tmp, calls, mp = env
    state = {"fail": True}
    def fake_check(text, ret, llm, log=False):
        return {"verdict": "UNVERIFIED", "search_status": "down" if state["fail"] and text == "claim one" else "ok", "claims": []}
    mp.setattr(run_eval, "check_forward", fake_check)
    run_eval.main(["--limit", "1"])
    state["fail"] = False
    run_eval.main(["--resume"])                                   # the first claim is resumed, the others now succeed
    assert json.load(open(tmp / "cache" / "eval_progress.json"))["search_failures"] == 1
    assert (tmp / "docs" / "evaluation-fallback-run.md").exists() and not (tmp / "docs" / "evaluation.md").exists()


def test_run_eval_clean_when_search_ok(env):
    tmp, calls, mp = env
    mp.setattr(run_eval, "check_forward", lambda text, ret, llm, log=False: {"verdict": {"claim one": "FALSE", "दावा दो": "TRUE", "claim three": "UNVERIFIED"}[text],
                                                                              "search_status": "ok", "claims": []})
    run_eval.main([])
    assert (tmp / "docs" / "evaluation.md").exists()


def _script(name):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def test_check_search_script_labels_and_never_prints_keys():
    cs = _script("check_search")
    def opener_for(code):
        def op(req, timeout=0):
            if code is None:
                return Resp({"results": [{"url": "https://pib.gov.in/a"}], "web": {"results": [{"url": "https://pib.gov.in/a"}]}})
            raise http(code)
        return op
    lines = []
    bad = cs.check([("brave", BraveSearch("brave-SECRET", opener=opener_for(402))), ("tavily", TavilySearch("tvly-SECRET", opener=opener_for(None)))], out=lines.append)
    text = "\n".join(lines)
    assert bad == 1 and "out of credits (402)" in text and "OK" in text and "SECRET" not in text
    for code, label in [(429, "rate limited"), (401, "auth error"), (403, "auth error"), (432, "out of credits")]:
        lines.clear(); cs.check([("brave", BraveSearch("k", opener=opener_for(code)))], out=lines.append)
        assert label in "\n".join(lines)
    lines.clear()
    assert cs.check([("brave", None), ("tavily", None)], out=lines.append) == 0 and "no key" in "\n".join(lines)
