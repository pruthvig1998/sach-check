"""Cache, counters, storage and verdict-trace tests. Offline and deterministic: no network, no real LLM."""
import json, re, time, pathlib
import pytest
import urllib.request as _ur
from test_sach import server, FakeRetriever, _post, TS          # noqa: F401  (server is a fixture)
from sach import cache, ledger, store, pipeline
from sach.models import *
from sach.models import RULE_TEXT
from sach.pipeline import check_forward
from sach.site import result_block
from sach.verdict import decide

FALSE_TEXT = "Government will give Rs 5000 to every woman. Please forward to all groups!"
PIB = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
               "Fake claim: government will give Rs 5000 to every woman", "Fake message claims government will give Rs 5000 to every woman")
OFFICIAL = Evidence("Ministry of Finance", "https://finmin.gov.in/other", TIER_OFFICIAL, TS, "Budget note", "Unrelated budget text")

class CountingRetriever(FakeRetriever):
    calls = 0
    def search(self, claim):
        self.calls += 1
        return super().search(claim)

class FakeLLM:
    """Judges by tier: PIB debunk contradicts, everything else is 'none'. failures stays 0 so results are not degraded."""
    failures = 0
    def __init__(self): self.stance_calls = 0
    def stance(self, claim, title, text, tier=None):
        self.stance_calls += 1
        return "contradicts" if tier == TIER_PIB else "none"

class NoneLLM(FakeLLM):
    def stance(self, claim, title, text, tier=None):
        return "none"

def run(text=FALSE_TEXT, ev=(PIB,), llm=None, **kw):
    r = CountingRetriever(list(ev))
    return check_forward(text, [r], llm or FakeLLM(), **kw), r

@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch):
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR"):
        monkeypatch.delenv(k, raising=False)
    store.reset()
    yield
    store.reset()

# ---------------------------------------------------------------- cache hits
def test_second_identical_check_is_a_fast_hit_with_same_verdict_and_citations():
    first, r1 = run()
    assert first["verdict"] == FALSE and not first.get("cached")
    assert r1.calls == 1
    t = time.monotonic()
    second = check_forward(FALSE_TEXT, [r1], FakeLLM())
    assert time.monotonic() - t < 2
    assert r1.calls == 1                                   # retriever not called again
    assert second["cached"] is True and second["verdict"] == FALSE
    assert second["claims"] == first["claims"] and second["card"] == first["card"]
    assert second["checked_at"] == first["checked_at"] == second["first_checked_at"]
    assert second["served_at"]
    # deliberate change (MATCH work package): a cache hit reports layer CACHE and remembers the layer that first answered
    assert second["trace"] == {**first["trace"], "layer": "CACHE", "original_layer": first["trace"]["layer"]}

def test_hit_never_calls_llm():
    llm = FakeLLM()
    run(llm=llm)
    n = llm.stance_calls
    check_forward(FALSE_TEXT, [], llm)
    assert llm.stance_calls == n

def test_normalisation_still_hits():
    run()
    for variant in ("  government   will give rs 5000 to every WOMAN.\n\nPlease forward to all groups! ",
                    "Government will give Rs 5000 to every wo​man. Please forward to all groups!"):
        out, r = run(variant)
        assert out.get("cached") is True and r.calls == 0

def test_changed_amount_misses():
    run()
    out, r = run(FALSE_TEXT.replace("5000", "6000"))
    assert not out.get("cached") and r.calls == 1

def test_reply_language_is_a_separate_entry():
    run()
    out, r = run(reply_lang="hi")
    assert not out.get("cached") and r.calls == 1
    out2, r2 = run(reply_lang="hi")
    assert out2["cached"] is True and out2["language"] == "hi"
    assert run(reply_lang="auto")[0].get("cached") is True          # 'auto' == None

# ---------------------------------------------------------------- what is stored
def test_degraded_results_are_never_stored():
    r = CountingRetriever([PIB])
    out = check_forward(FALSE_TEXT, [r], None)                       # no LLM -> degraded
    assert out["degraded"] is True
    assert check_forward(FALSE_TEXT, [r], None).get("cached") is None and r.calls == 2

def test_no_claims_and_timed_out_never_stored(monkeypatch):
    out, r = run("hello 👍")
    assert out.get("no_claims") and run("hello 👍")[0].get("cached") is None
    assert cache.storable(out) is False
    def boom(*a, **k): raise RuntimeError("late")
    real = pipeline._check_claim
    monkeypatch.setattr(pipeline, "_check_claim", boom)
    out, _ = run()
    assert out["claims"][0]["reason_code"] == "timed_out" and cache.storable(out) is False
    monkeypatch.setattr(pipeline, "_check_claim", real)
    assert run()[0].get("cached") is None                           # the timed-out run left nothing behind

def test_ttls_unverified_short_decisive_long(monkeypatch):
    t = [1_000_000.0]
    monkeypatch.setattr(store, "_now", lambda: t[0])
    monkeypatch.setattr(cache, "TTL_UNVERIFIED_S", 6 * 3600)
    monkeypatch.setattr(cache, "TTL_DECISIVE_S", 7 * 24 * 3600)
    run(llm=NoneLLM(), ev=())                                        # UNVERIFIED
    run(llm=FakeLLM())                                               # FALSE, decisive
    t[0] += 6 * 3600 - 5
    assert run(llm=NoneLLM(), ev=())[0].get("cached") is True
    t[0] += 10                                                       # just past 6 h
    out, r = run(llm=NoneLLM(), ev=())
    assert not out.get("cached") and r.calls == 1                    # short TTL expired
    assert run()[0].get("cached") is True                            # decisive still there
    t[0] += 7 * 24 * 3600
    assert not run()[0].get("cached")                                # now expired too

def test_cache_bypass_switches(monkeypatch):
    run()
    assert run(use_cache=False)[1].calls == 1
    assert run(log=False)[1].calls == 1
    monkeypatch.setenv("SACH_NO_CACHE", "1")
    assert run()[1].calls == 1
    monkeypatch.delenv("SACH_NO_CACHE")
    assert run()[0].get("cached") is True

def test_no_cache_and_log_false_do_not_write(monkeypatch):
    run(use_cache=False)
    run(log=False, text="Another viral claim: free scooters for all girls in India")
    assert run()[0].get("cached") is None                            # nothing was written by the bypassed runs
    monkeypatch.setenv("SACH_NO_CACHE", "1")
    run(text="Free laptops for all students under a new scheme")
    monkeypatch.delenv("SACH_NO_CACHE")
    assert run(text="Free laptops for all students under a new scheme")[0].get("cached") is None

# ---------------------------------------------------------------- counters, ledger
def test_hit_does_not_append_ledger_rows_but_counts():
    run()
    rows = len(ledger.load())
    run(); run()
    assert len(ledger.load()) == rows
    s = ledger.stats()
    assert s["checks_total"] == 3 and s["cache_hits"] == 2 and s["verdict:FALSE"] == 3

def test_counters_by_verdict_and_language_and_no_claims():
    run()                                                            # FALSE, en
    run(llm=NoneLLM(), ev=(), text="Drinking hot water cures cancer completely.")   # UNVERIFIED
    run("सरकार हर महिला को 5000 रुपये देगी, जल्दी शेयर करें।", llm=NoneLLM(), ev=())  # hi
    run("hello 👍")
    s = ledger.stats()
    assert s["checks_total"] == 4 and s["no_claims"] == 1
    assert s["verdict:FALSE"] == 1 and s["verdict:UNVERIFIED"] == 2 and s["verdict:TRUE"] == 0
    assert s["lang:hi"] == 1 and s["lang:en"] == 3
    assert s["first_event_at"] and s["ledger_rows"] == len(ledger.load())

def test_log_false_records_nothing():
    run(log=False)
    assert ledger.stats()["checks_total"] == 0 and ledger.stats()["first_event_at"] is None

def test_first_event_at_set_once():
    run()
    first = ledger.stats()["first_event_at"]
    store.get_store().set("x", 1)
    run(text="Another claim: all trains will be free from tomorrow, says minister")
    assert ledger.stats()["first_event_at"] == first

def test_filestore_ledger_not_double_counted():
    base = len(ledger.load())
    run()
    assert len(ledger.load()) == base + 1
    assert store.get_store().items("ledger") == []

# ---------------------------------------------------------------- store behaviour
def test_filestore_roundtrip_ttl_counters_and_list_cap(monkeypatch, tmp_path):
    s = store.FileStore(str(tmp_path / "s"))
    assert s.get("a") is None
    s.set("a", {"x": [1, 2]}); assert s.get("a") == {"x": [1, 2]}
    t = [100.0]; monkeypatch.setattr(store, "_now", lambda: t[0])
    s.set("b", 1, ttl_s=10); assert s.get("b") == 1
    t[0] = 111; assert s.get("b") is None
    assert s.incr("n") == 1 and s.incr("n", 4) == 5
    assert s.counters(["n", "missing"]) == {"n": 5, "missing": 0}
    for i in range(7): s.push("l", i, cap=5)
    assert s.items("l") == [2, 3, 4, 5, 6]
    assert not list((tmp_path / "s").glob("*.tmp"))

def test_get_store_follows_env_changes(monkeypatch, tmp_path):
    a = store.get_store()
    assert isinstance(a, store.FileStore) and a is store.get_store()
    monkeypatch.setenv("SACH_LEDGER", str(tmp_path / "other" / "ledger.json"))
    b = store.get_store()
    assert b is not a and b.dir == str(tmp_path / "other" / "store")
    monkeypatch.setenv("KV_REST_API_URL", "https://x.upstash.io"); monkeypatch.setenv("KV_REST_API_TOKEN", "tok")
    assert isinstance(store.get_store(), store.UpstashStore)

def test_unwritable_store_dir_never_breaks_a_check(monkeypatch, tmp_path):
    blocker = tmp_path / "file"; blocker.write_text("x")
    monkeypatch.setenv("SACH_STORE_DIR", str(blocker / "sub"))      # cannot be created
    out, r = run()
    assert out["verdict"] == FALSE
    again, r2 = run()
    assert not again.get("cached") and r2.calls == 1 and ledger.stats()["checks_total"] == 0

def test_corrupt_cache_entry_is_a_miss(tmp_path):
    run()
    for f in (tmp_path / "store").glob("kv_*.json"):
        f.write_text("{not json")
    out, r = run()
    assert not out.get("cached") and r.calls == 1

class FakeRedis:
    """Records requests and emulates the few Redis commands the store uses."""
    def __init__(self, fail=False, status=200):
        self.kv, self.lists, self.log, self.fail, self.status = {}, {}, [], fail, status
    def __call__(self, req, timeout=None):
        if self.fail: raise OSError("network down")
        cmd = json.loads(req.data.decode())
        self.log.append((req.full_url, req.get_header("Authorization"), cmd, timeout, req.get_method()))
        op, a = cmd[0], cmd[1:]
        if op == "GET": res = self.kv.get(a[0])
        elif op == "SET": self.kv[a[0]] = a[1]; res = "OK"
        elif op == "INCRBY": self.kv[a[0]] = int(self.kv.get(a[0], 0)) + a[1]; res = self.kv[a[0]]
        elif op == "MGET": res = [self.kv.get(k) for k in a]
        elif op == "RPUSH": self.lists.setdefault(a[0], []).append(a[1]); res = len(self.lists[a[0]])
        elif op == "LTRIM": self.lists[a[0]] = self.lists[a[0]][a[1]:]; res = "OK"
        elif op == "LRANGE": res = list(self.lists.get(a[0], []))
        else: res = None
        return _Resp(json.dumps({"result": res}), self.status)

class _Resp:
    def __init__(self, body, status): self.body, self.status = body, status
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.body.encode()

def test_upstash_requests_are_well_formed():
    f = FakeRedis()
    u = store.UpstashStore("https://eu1-x.upstash.io/", "secret", opener=f)
    u.set("cache:k", {"a": 1}, ttl_s=3600)
    url, auth, cmd, timeout, method = f.log[-1]
    assert url == "https://eu1-x.upstash.io" and auth == "Bearer secret" and method == "POST" and timeout == 2
    assert cmd == ["SET", "sach:cache:k", '{"a": 1}', "EX", 3600]
    assert u.get("cache:k") == {"a": 1} and f.log[-1][2] == ["GET", "sach:cache:k"]
    assert u.get("nope") is None
    assert u.incr("checks_total", 2) == 2 and f.log[-1][2] == ["INCRBY", "sach:c:checks_total", 2]
    assert u.counters(["checks_total", "zzz"]) == {"checks_total": 2, "zzz": 0}
    for i in range(4): u.push("ledger", {"i": i}, cap=3)
    assert u.items("ledger") == [{"i": 1}, {"i": 2}, {"i": 3}]
    assert all(c[2][1].startswith("sach:") for c in f.log)

@pytest.mark.parametrize("opener", [FakeRedis(fail=True), FakeRedis(status=500)])
def test_upstash_failures_are_misses_not_errors(opener):
    u = store.UpstashStore("https://x.upstash.io", "t", opener=opener)
    u.set("a", 1); u.push("l", 1)
    assert u.get("a") is None and u.incr("c") == 0 and u.counters(["c"]) == {"c": 0} and u.items("l") == []

def test_upstash_bad_json_is_a_miss():
    f = FakeRedis(); f.kv["sach:a"] = "{oops"
    assert store.UpstashStore("https://x.upstash.io", "t", opener=f).get("a") is None

def test_env_names_both_accepted(monkeypatch):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://a.upstash.io"); monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "t1")
    assert store.get_store().url == "https://a.upstash.io"
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL"); monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN")
    monkeypatch.setenv("KV_REST_API_URL", "https://b.upstash.io"); monkeypatch.setenv("KV_REST_API_TOKEN", "t2")
    assert store.get_store().url == "https://b.upstash.io" and store.get_store().token == "t2"
    monkeypatch.delenv("KV_REST_API_TOKEN")
    assert isinstance(store.get_store(), store.FileStore)             # URL alone is not enough

def test_whole_pipeline_on_upstash_fake_dedupes_ledger_and_hits(monkeypatch):
    f = FakeRedis()
    monkeypatch.setattr(_ur, "urlopen", f)
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://a.upstash.io"); monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "t")
    base = len(ledger.load())
    run()
    assert len(f.lists["sach:l:ledger"]) == 1
    assert len(ledger.load()) == base + 1                            # file row + store row are the same row
    out, r = run()
    assert out["cached"] is True and r.calls == 0
    assert ledger.stats()["cache_hits"] == 1

def test_upstash_down_never_breaks_check(monkeypatch):
    monkeypatch.setattr(_ur, "urlopen", FakeRedis(fail=True))
    monkeypatch.setenv("KV_REST_API_URL", "https://a.upstash.io"); monkeypatch.setenv("KV_REST_API_TOKEN", "t")
    out, r = run()
    assert out["verdict"] == FALSE
    assert not run()[0].get("cached")

# ---------------------------------------------------------------- trace
def test_trace_lists_every_judged_source_including_uncited():
    out, _ = run(ev=(PIB, OFFICIAL))
    c = out["claims"][0]
    srcs = c["trace"]["sources"]
    assert len(srcs) == 2
    assert all({"source", "url", "tier", "fetched_at", "title", "stance"} <= set(s) <= {"source", "url", "tier", "fetched_at", "title", "stance", "judged"} for s in srcs)
    by = {s["url"]: s for s in srcs}
    assert by[PIB.url]["stance"] == "contradicts" and by[OFFICIAL.url]["stance"] == "none"
    assert {x["url"] for x in c["citations"]} == {PIB.url}          # the second source was judged but not cited
    assert by[OFFICIAL.url]["tier"] == TIER_OFFICIAL and by[OFFICIAL.url]["fetched_at"] == TS and by[OFFICIAL.url]["title"] == "Budget note"
    assert c["trace"]["rule"] == "official_contradiction" and c["trace"]["rule_text"] == RULE_TEXT["official_contradiction"]
    assert c["trace"]["searched_as"] == c["claim"]["text"]
    assert out["trace"]["claims_extracted"] == 1 and out["trace"]["degraded"] is False
    assert "FALSE" in out["trace"]["overall_rule"]

def test_trace_caps_at_eight_sources():
    many = [Evidence(f"Src {i}", f"https://a{i}.gov.in/p", TIER_OFFICIAL, TS, "t", "x") for i in range(12)]
    out, _ = run(ev=many)
    assert len(out["claims"][0]["trace"]["sources"]) == 8

def test_rule_text_exists_for_every_reason_code_in_verdict_py():
    src = (pathlib.Path(__file__).resolve().parents[1] / "sach" / "verdict.py").read_text()
    codes = set(re.findall(r'"([a-z]+(?:_[a-z]+)+)"', src))
    assert codes >= {"official_contradiction", "official_confirmation", "core_fact_distorted",
                     "conflicting_official_sources", "factchecker_only", "no_evidence"}
    for code in codes | {"timed_out"}:
        assert RULE_TEXT.get(code) and RULE_TEXT[code].endswith(".")
    c = Claim("x")
    for evs in ([], [Evidence("a", "https://a.gov.in", TIER_OFFICIAL, TS, stance="confirms")],
                [Evidence("a", "https://a.gov.in", TIER_OFFICIAL, TS, stance="mixed")],
                [Evidence("a", "https://a.gov.in", TIER_PIB, TS, stance="contradicts")],
                [Evidence("a", "https://a.com", TIER_FACTCHECKER, TS, stance="none")]):
        assert decide(c, evs).reason_code in RULE_TEXT

def test_overall_rule_matches_aggregate():
    from sach.models import overall_rule
    mk = lambda v: ClaimVerdict(Claim("x"), v, "x")
    assert "FALSE" in overall_rule([mk(TRUE), mk(FALSE)])
    assert "MISLEADING" in overall_rule([mk(TRUE), mk(MISLEADING)])
    assert "TRUE" in overall_rule([mk(TRUE)]) and "UNVERIFIED" in overall_rule([mk(TRUE), mk(UNVERIFIED)])

def test_timed_out_claim_has_trace(monkeypatch):
    monkeypatch.setattr(pipeline, "_check_claim", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    out, _ = run()
    t = out["claims"][0]["trace"]
    assert t["rule"] == "timed_out" and t["sources"] == [] and t["rule_text"]

def test_trace_html_present_and_escaped():
    evil = Evidence("<b>Evil</b> Src", "https://pib.gov.in/x?a=1&b=2", TIER_PIB, TS, "<script>alert(1)</script> Fake claim: government will give Rs 5000 to every woman", "t")
    out, _ = run(ev=(evil,))
    html = result_block(out)
    assert '<details class="trace"><summary>How this verdict was reached</summary>' in html
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html and "<b>Evil</b>" not in html
    assert "CONTRADICTS" in html and "Claims found in the message" in html and "official_contradiction" not in html
    assert RULE_TEXT["official_contradiction"] in html and out["trace"]["overall_rule"] in html
    assert "First checked" not in html

def test_trace_html_shows_stances_searched_as_and_no_sources():
    out, _ = run(ev=(PIB, OFFICIAL))
    out["claims"][0]["trace"]["searched_as"] = "An English version"
    h = result_block(out)
    assert "Searched as: An English version" in h and "NEITHER" in h and "PARTLY" not in h
    empty, _ = run(ev=(), llm=NoneLLM(), text="Drinking hot water cures cancer completely.")
    assert "No sources were found for this claim." in result_block(empty)
    out["claims"][0]["trace"]["sources"][0]["stance"] = "mixed"
    assert "PARTLY" in result_block(out)

def test_no_claims_has_no_trace_details():
    out, _ = run("hello 👍")
    assert out["trace"]["claims_extracted"] == 0
    assert "<details" not in result_block(out)

def test_result_without_trace_fields_still_renders():
    out, _ = run()
    for c in out["claims"]: c.pop("trace")
    out.pop("trace")
    assert "How this verdict was reached" in result_block(out)

def test_cached_result_shows_first_checked_line():
    first, _ = run()
    hit, _ = run()
    h = result_block(hit)
    from sach import timefmt
    assert f"This result was checked before and is shown again; it was checked on {timefmt.fmt_ist(first['checked_at'])}." in h
    assert "First checked" not in result_block(first)

# ---------------------------------------------------------------- JSON API and HTML via the real server
def test_json_api_includes_trace_and_cached_flags(server):
    import sach.web as W
    W.Handler.llm = FakeLLM()
    code, body = _post(server, FALSE_TEXT, path="/?format=json")
    d = json.loads(body)
    assert code == 200 and d["verdict"] == FALSE and "cached" not in d
    assert d["trace"]["claims_extracted"] == 1 and d["claims"][0]["trace"]["sources"][0]["stance"] == "contradicts"
    code, body = _post(server, FALSE_TEXT, path="/?format=json")
    d2 = json.loads(body)
    assert d2["cached"] is True and d2["first_checked_at"] == d["checked_at"] and d2["served_at"]
    code, html = _post(server, FALSE_TEXT)
    assert "How this verdict was reached" in html and "checked before and is shown again" in html


# --- 13 Nov incident: a silent judge failure became a cached UNVERIFIED. Old UNVERIFIED live results are re-checked; evidence-backed ones stay.
def test_old_unverified_live_result_without_judge_timing_is_treated_as_a_miss(monkeypatch):
    from sach import cache
    old = {"verdict": "UNVERIFIED", "claims": [{"reason_code": "no_evidence", "trace": {"layer": "LIVE", "sources": []}}], "layer": "live"}
    assert cache._poisoned(old) is True
    new = {"verdict": "UNVERIFIED", "claims": [{"reason_code": "no_evidence", "trace": {"layer": "LIVE", "timing_ms": {"retrieve": 5, "judge": 5, "judge_window": 30000}}}]}
    assert cache._poisoned(new) is False                                          # recorded judging: a genuine "no evidence"
    assert cache._poisoned({"verdict": "FALSE", "claims": [{"trace": {}}]}) is False        # decisive results carry cited evidence
    assert cache._poisoned({"verdict": "UNVERIFIED", "layer": "match", "claims": [{"trace": {}}]}) is False
    assert cache._poisoned({"verdict": "UNVERIFIED", "no_claims": True, "claims": []}) is False

def test_a_check_with_a_failed_or_timed_out_judge_is_degraded_and_never_cached():
    from sach import cache
    out = {"verdict": "UNVERIFIED", "degraded": True, "claims": [{"reason_code": "no_evidence"}]}
    assert cache.storable(out) is False
