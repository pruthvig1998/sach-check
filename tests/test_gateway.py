"""GATEWAY work package: Vercel AI Gateway as an AI judge. Fully offline: fake openers, no network, no real key."""
import io, json, time, traceback, urllib.error
import pytest
from sach import llm as L, status, gateway as G
from sach.models import TIER_PIB

KEY = "vck_FAKE-GATEWAY-KEY-1234567890"
DEBUNK_T = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
DEBUNK_X = "A media report said the retirement age would be reduced to 50 years. This is fake; no such proposal exists."
CLAIM = "Central Government will reduce the retirement age of employees to 50 years."
REPLY = "CONTRADICTS | This is fake; no such proposal exists."


class Resp:
    def __init__(self, obj):
        self._b = json.dumps(obj).encode()
    def read(self, n=-1):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

def http_error(code, headers=None, body=b"{}"):
    return urllib.error.HTTPError("https://ai-gateway.vercel.sh/v1/chat/completions", code, "err", headers or {}, io.BytesIO(body))

class FakeGateway:
    def __init__(self, text="NEITHER"):
        self.reqs, self.text, self.error = [], text, None
    def __call__(self, req, timeout=None):
        self.reqs.append(req)
        err = self.error(json.loads(req.data)["model"]) if callable(self.error) else self.error
        if err:
            raise err
        return Resp({"choices": [{"message": {"content": self.text}}]})

def judge(g, **kw):
    return L.GatewayJudge(KEY, opener=g, **kw)

def other(ans="contradicts"):
    return type("N", (), {"name": "next", "models": ["m"], "failures": 0, "exhausted_until": 0.0,
                          "available": lambda s: True, "stance": lambda s, *a, **k: ans})()


def test_request_shape():
    g = FakeGateway(text="  hi  ")
    j = judge(g)
    assert j._raw("google/gemini-3.1-flash-lite", "SYS", "USER", 200) == "  hi  "
    r = g.reqs[0]
    assert r.full_url == "https://ai-gateway.vercel.sh/v1/chat/completions" and r.get_method() == "POST"
    assert r.get_header("Authorization") == "Bearer " + KEY and r.get_header("Content-type") == "application/json"
    b = json.loads(r.data)
    assert b["model"] == "google/gemini-3.1-flash-lite" and b["max_tokens"] == 200 and b["temperature"] == 0
    assert b["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert "reasoning_effort" not in b

def test_gpt_oss_gets_room_to_think():
    g = FakeGateway()
    judge(g)._raw("openai/gpt-oss-120b", "s", "u", 200)
    assert json.loads(g.reqs[0].data)["max_tokens"] == 700

def test_null_content_is_empty_text():
    j = judge(lambda req, timeout=None: Resp({"choices": [{"message": {"content": None}}]}))
    assert j._raw("m", "s", "u", 10) == ""

def test_default_models_and_env_override(monkeypatch):
    assert judge(FakeGateway()).models == ["openai/gpt-oss-120b", "google/gemini-3.1-flash-lite"]
    monkeypatch.setenv("SACH_GATEWAY_MODELS", " a/b , c/d ,")
    assert judge(FakeGateway()).models == ["a/b", "c/d"]

def test_stance_parses_and_validates_with_second_opinion():
    g = FakeGateway(text=REPLY)
    assert judge(g).stance(CLAIM, DEBUNK_T, DEBUNK_X) == "contradicts"
    assert [json.loads(r.data)["model"] for r in g.reqs] == ["openai/gpt-oss-120b", "google/gemini-3.1-flash-lite"]
    assert judge(FakeGateway(text="NEITHER")).stance(CLAIM, DEBUNK_T, DEBUNK_X) == "none"

def test_translate():
    assert judge(FakeGateway(text=" Hello ")).translate("नमस्ते") == "Hello"


# ---------------------------------------------------------------- failure policy
def test_401_pauses_ten_minutes_and_failover_continues():
    g = FakeGateway(); g.error = http_error(401)
    j = judge(g)
    f = L.FailoverJudge([j, other()])
    assert f.stance(CLAIM, DEBUNK_T, DEBUNK_X) == "contradicts"
    assert not j.available() and 500 < j.exhausted_until - time.time() <= 601
    n = len(g.reqs)
    f.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert len(g.reqs) == n

def test_402_pauses_until_utc_midnight_and_failover_moves_on():
    g = FakeGateway(); g.error = http_error(402)
    j = judge(g)
    f = L.FailoverJudge([j, other()])
    assert f.stance(CLAIM, DEBUNK_T, DEBUNK_X) == "contradicts"
    left = j.exhausted_until - time.time()
    assert 0 < left <= 86400 + 1 and not j.available()
    assert len(g.reqs) == 1                                           # the shared credit is gone: the other model is not tried
    assert f.failures == 0

def test_429_pauses_that_model_for_retry_after():
    g = FakeGateway(text=REPLY)
    g.error = lambda m: http_error(429, {"retry-after": "42"}) if m == "openai/gpt-oss-120b" else None
    j = judge(g)
    assert j.stance(CLAIM, DEBUNK_T, DEBUNK_X) == "none"
    assert [json.loads(r.data)["model"] for r in g.reqs] == j.models
    p = j._pauses()
    assert list(p) == ["openai/gpt-oss-120b"] and 30 < p["openai/gpt-oss-120b"] - time.time() <= 43 and j.available()
    assert j.stance(CLAIM, DEBUNK_T, DEBUNK_X, tier=TIER_PIB) == "contradicts"
    assert [json.loads(r.data)["model"] for r in g.reqs] == j.models + [j.models[1]]

def test_5xx_fails_over_without_benching():
    g = FakeGateway(); g.error = http_error(503)
    j = judge(g)
    with pytest.raises(G.GatewayError):
        j.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert j.available() and not j._pauses() and len(g.reqs) == 2     # both models tried

def test_timeout_pauses_only_that_model():
    g = FakeGateway(text="NEITHER")
    g.error = lambda m: TimeoutError("slow") if m == "openai/gpt-oss-120b" else None
    j = judge(g)
    j.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert list(j._pauses()) == ["openai/gpt-oss-120b"] and j.available()

def test_network_error_is_generic_gateway_error():
    g = FakeGateway(); g.error = urllib.error.URLError("dns")
    with pytest.raises(G.GatewayError):
        judge(g)._raw("m", "s", "u", 5)


# ---------------------------------------------------------------- spend guard
def test_daily_cap_blocks_calls_and_pauses_until_utc_midnight(monkeypatch):
    monkeypatch.setenv("SACH_GATEWAY_MAX_PER_DAY", "2")
    g = FakeGateway(text="NEITHER")
    j = judge(g)
    j.stance(CLAIM, DEBUNK_T, DEBUNK_X); j.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert len(g.reqs) == 2 and j.available()
    with pytest.raises(G.GatewayCapReached):
        j.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert len(g.reqs) == 2 and not j.available() and 0 < j.exhausted_until - time.time() <= 86401
    u = G.usage()
    assert u["calls_today"] == 2 and u["max_per_day"] == 2 and u["skipped_over_cap_today"] >= 1

def test_shared_store_counter_next_day_and_unlimited(monkeypatch):
    from test_scale import FakeStore
    st = FakeStore()
    monkeypatch.setenv("SACH_GATEWAY_MAX_PER_DAY", "3")
    now = 1_800_000_000.0
    for _ in range(3):
        G.reserve_call(st, now)
    with pytest.raises(G.GatewayCapReached):
        G.reserve_call(st, now)
    assert G.usage(st, now)["calls_today"] == 3
    G.reserve_call(st, now + 86400)
    assert G.usage(st, now + 86400)["calls_today"] == 1
    monkeypatch.setenv("SACH_GATEWAY_MAX_PER_DAY", "0")
    for _ in range(10):
        G.reserve_call(FakeStore(), now)

def test_broken_store_falls_back_to_memory(monkeypatch):
    from test_scale import FakeStore
    monkeypatch.setenv("SACH_GATEWAY_MAX_PER_DAY", "2")
    st = FakeStore(broken=True)
    G.reserve_call(st); G.reserve_call(st)
    with pytest.raises(G.GatewayCapReached):
        G.reserve_call(st)

def test_default_cap_is_1500_and_counter_is_separate_from_vertex():
    from sach import vertex
    assert G.max_per_day() == 1500
    G.reserve_call()
    assert G.usage()["calls_today"] == 1 and vertex.usage()["calls_today"] == 0


# ---------------------------------------------------------------- wiring / order
def _env(monkeypatch):
    for k in ("GEMINI_API_KEY", "GEMINI_API_KEYS", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GROQ_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY",
              "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "ANTHROPIC_API_KEY", "SACH_JUDGE_ORDER", "GOOGLE_SA_JSON"):
        monkeypatch.delenv(k, raising=False)

def _names():
    return [j.name.split("-")[0] for j in L.build_judges()]

def test_off_without_key_and_after_groq_when_set(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g1"); monkeypatch.setenv("GROQ_API_KEY", "q"); monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    assert _names() == ["groq", "gemini", "openrouter"]
    monkeypatch.setenv("AI_GATEWAY_API_KEY", KEY)
    assert _names() == ["groq", "gateway", "gemini", "openrouter"]
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "   ")
    assert _names() == ["groq", "gemini", "openrouter"]
    assert L.DEFAULT_JUDGE_ORDER == "groq,gemini,openrouter,mistral,cloudflare,claude"

def test_after_vertex_and_groq_and_explicit_order_wins(monkeypatch):
    _env(monkeypatch)
    stub = type("V", (L.GatewayJudge,), {"name": "vertex"})(KEY)
    monkeypatch.setattr(L, "_vertex_judge", lambda: stub)
    monkeypatch.setenv("GEMINI_API_KEY", "g1"); monkeypatch.setenv("GROQ_API_KEY", "q"); monkeypatch.setenv("AI_GATEWAY_API_KEY", KEY)
    assert _names() == ["vertex", "groq", "gateway", "gemini"]
    monkeypatch.setenv("SACH_JUDGE_ORDER", "gateway,groq,gemini")
    assert _names() == ["gateway", "groq", "gemini", "vertex"]

def test_gateway_alone_and_get_llm(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", KEY)
    f = L.get_llm()
    assert [j.name for j in f.judges] == ["gateway"] and f.models == ["openai/gpt-oss-120b", "google/gemini-3.1-flash-lite"]


# ---------------------------------------------------------------- status
def _row(f):
    return {r["provider"]: r for r in status.ai_providers(f)}["gateway"]

def test_status_row_counts_and_no_key(monkeypatch):
    monkeypatch.setenv("SACH_GATEWAY_MAX_PER_DAY", "10")
    j = judge(FakeGateway(text="NEITHER"))
    j.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    f = type("F", (), {"judges": [j]})()
    r = _row(f)
    assert r["configured"] is True and r["state"] == "ready" and r["calls_today"] == 1 and r["max_per_day"] == 10
    d = status.status_data(f, [])
    page = status.status_page(d).decode()
    assert KEY not in json.dumps(d) + page and "1 of 10" in page

def test_status_row_off_and_paused():
    off = _row(type("F", (), {"judges": []})())
    assert off["configured"] is False and off["state"] == "off" and off["max_per_day"] == 1500 and off["calls_today"] == 0
    g = FakeGateway(); g.error = http_error(402)
    j = judge(g)
    with pytest.raises(Exception):
        j.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert _row(type("F", (), {"judges": [j]})())["state"] == "paused"


# ---------------------------------------------------------------- the key never leaks
def _everything(exc):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + repr(exc) + str(exc) + repr(getattr(exc, "headers", ""))

def test_key_never_in_errors_logs_or_reprs(caplog, capsys):
    caplog.set_level("DEBUG")
    class Leaky(FakeGateway):
        def __call__(self, req, timeout=None):
            auth = req.get_header("Authorization")
            n = len(self.reqs)
            self.reqs.append(req)
            raise [RuntimeError("boom " + auth), http_error(401, {"x": auth}, body=auth.encode()),
                   urllib.error.URLError("echo " + auth), TimeoutError(auth)][n % 4]
    j = judge(Leaky())
    texts = []
    for _ in range(4):
        with pytest.raises(Exception) as ei:
            j._raw("m", "s", "u", 5)
        texts.append(_everything(ei.value))
    out = capsys.readouterr()
    d = json.dumps(status.status_data(type("F", (), {"judges": [j]})(), []))
    for blob in texts + [caplog.text, out.out, out.err, repr(j), str(j), j.name, d]:
        assert KEY not in blob and "vck_" not in blob and "Bearer" not in blob
