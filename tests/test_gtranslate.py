"""Google Cloud Translation as first-choice translator. Fully offline: fake openers, fake stores, fake LLMs. No network, no key."""
import json
from datetime import date
import pytest
from sach import gtranslate as G, ledger, limits, match, status, store
from sach.models import Evidence
from sach.pipeline import check_forward
from sach.site import trace_block

KEY = "AIzaSyFAKEKEYFORTESTSONLY1234567890abcd"
HI = "सभी छात्रों को मुफ्त लैपटॉप मिलेगा, जल्दी शेयर करें।"          # Devanagari, no regional markers: our detector says 'hi'
BN = "সব ছাত্রছাত্রীকে বিনামূল্যে ল্যাপটপ দেওয়া হবে।"               # Bengali script, no Assamese letters: 'bn'
TE = "విద్యార్థులందరికీ ఉచిత ల్యాప్‌టాప్ ఇస్తారు"
TODAY = date(2026, 11, 13)


class Resp:
    def __init__(self, body, status=200):
        self.status, self._b = status, json.dumps(body).encode() if not isinstance(body, bytes) else body
    def read(self, n=-1): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def ok(text="Free laptops for all students", det="hi"):
    t = {"translatedText": text}
    if det:
        t["detectedSourceLanguage"] = det
    return {"data": {"translations": [t]}}


class Opener:
    def __init__(self, *responses, exc=None):
        self.responses, self.exc, self.reqs = list(responses), exc, []
    def __call__(self, req, timeout=None):
        self.reqs.append((req, timeout))
        if self.exc:
            raise self.exc
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return r if isinstance(r, Resp) else Resp(r)


class MemStore:
    """Remote-style store (counters honoured) backed by dicts."""
    remote = True
    def __init__(self): self.kv, self.c, self.sets = {}, {}, 0
    def get(self, k): return self.kv.get(k)
    def set(self, k, v, ttl_s=None): self.kv[k] = v; self.sets += 1
    def incr(self, k, by=1): self.c[k] = self.c.get(k, 0) + by; return self.c[k]
    def expire(self, k, ttl): pass
    def counters(self, names): return {n: self.c.get(n, 0) for n in names}
    def push(self, name, value, cap=500): self.kv.setdefault('l:' + name, []).append(value)
    def items(self, name): return list(self.kv.get('l:' + name, []))


class BrokenStore:
    remote = True
    def get(self, k): raise RuntimeError("boom")
    def set(self, *a, **k): raise RuntimeError("boom")
    def incr(self, *a, **k): raise RuntimeError("boom")
    def expire(self, *a, **k): raise RuntimeError("boom")
    def counters(self, n): raise RuntimeError("boom")


class LLM:
    failures = 0
    def __init__(self, out="LLM english"): self.t_calls, self.out = 0, out
    def stance(self, *a, **k): return "none"
    def translate(self, text): self.t_calls += 1; return self.out


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("SACH_NO_CACHE", "SACH_NO_MATCH", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN",
              "SACH_STORE_DIR", "GOOGLE_FACTCHECK_API_KEY", "SACH_TRANSLATE_MAX_CHARS_PER_DAY", "SACH_TRANSLATE_MAX_CHARS_PER_MIN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GOOGLE_TRANSLATE_API_KEY", KEY)
    store.reset(); G.reset()
    yield
    store.reset(); G.reset()


# ---------------------------------------------------------------- request / response
def test_request_shape_header_not_url():
    op = Opener(ok())
    r = G.translate(HI, "hi", op)
    req, timeout = op.reqs[0]
    assert req.full_url == "https://translation.googleapis.com/language/translate/v2" and req.get_method() == "POST"
    assert "key=" not in req.full_url and KEY not in req.full_url
    assert req.get_header("X-goog-api-key") == KEY
    body = json.loads(req.data)
    assert body == {"q": [HI], "target": "en", "format": "text", "source": "hi"}
    assert timeout == 4
    assert r == {"text": "Free laptops for all students", "detected": "hi"}


def test_no_source_means_autodetect():
    op = Opener(ok(det="mr"))
    r = G.translate(HI, None, op)
    assert "source" not in json.loads(op.reqs[0][0].data) and r["detected"] == "mr"


def test_html_entities_unescaped_and_missing_detected():
    r = G.translate(HI, None, Opener(ok("It&#39;s &quot;free&quot; &amp; fast", det=None)))
    assert r == {"text": 'It\'s "free" & fast', "detected": None}


def test_input_capped_at_1000_chars():
    op = Opener(ok())
    G.translate("क" * 5000, None, op)
    assert len(json.loads(op.reqs[0][0].data)["q"][0]) == 1000


@pytest.mark.parametrize("resp", [Resp(ok(), 500), Resp(ok(), 403), Resp(ok(), 429), Resp(b"not json"), Resp({"data": {}}),
                                  Resp({"data": {"translations": []}}), Resp(ok("   ")), Resp([1, 2])])
def test_failure_modes_return_none(resp):
    assert G.translate(HI, None, Opener(resp)) is None


def test_exceptions_return_none_and_hide_key():
    import urllib.error
    for exc in (TimeoutError("slow"), OSError("down"), urllib.error.HTTPError("https://x/?key=" + KEY, 403, "forbidden", {}, None)):
        assert G.translate(HI, None, Opener(exc=exc)) is None


def test_off_without_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_TRANSLATE_API_KEY")
    op = Opener(ok())
    assert G.translate(HI, None, op) is None and op.reqs == []
    assert G.translate_claim(HI, "hi", LLM(), op)["translator"] == "llm" and op.reqs == []


def test_quota_error_pauses_google_for_a_while():
    op = Opener(Resp(ok(), 429))
    st = MemStore()
    assert G.translate_claim(HI, "hi", None, op, st)["translator"] == "none"
    assert len(op.reqs) == 1
    G.translate_claim(HI + "!", "hi", None, op, st)
    assert len(op.reqs) == 1                      # paused: no second call


def test_key_never_in_returns_or_logs(caplog):
    caplog.set_level("DEBUG")
    st = MemStore()
    out = [G.translate_claim(HI, "hi", LLM(), Opener(ok()), st), G.translate(HI, None, Opener(exc=OSError(KEY))), G.usage(st)]
    assert KEY not in json.dumps(out, default=str) and KEY not in caplog.text and KEY not in json.dumps(st.kv) + json.dumps(st.c)


# ---------------------------------------------------------------- scripts and codes
def test_latin_script_never_goes_to_google():
    op = Opener(ok())
    for txt in ("Sabko free laptop milega, jaldi forward karo", "andariki free laptop istundi, ee roju chudandi", "Free laptops for all students"):
        assert G.translate(txt, None, op) is None
        r = G.translate_claim(txt, "tl", LLM("llm said"), op, MemStore())
        assert r["translator"] == "llm" and r["text"] == "llm said"
    assert op.reqs == []


def test_language_code_mapping():
    assert G.google_code("kok") == "gom" and G.google_code("mni") == "mni-Mtei"
    assert G.google_code("te") == "te" and G.google_code("ta") == "ta"
    assert G.google_code("hi") is None and G.google_code("bn") is None      # ambiguous scripts: let Google detect
    assert G.google_code("tl") is None and G.google_code("en") is None
    op = Opener(ok())
    G.translate_claim("ꯃꯩꯇꯩꯂꯣꯟ ꯃꯅꯤꯄꯨꯔꯤꯒꯤ ꯁꯔꯀꯥꯔ", "mni", None, op, MemStore())
    assert json.loads(op.reqs[0][0].data).get("source") == "mni-Mtei"
    op = Opener(ok())
    G.translate_claim(TE, "te", None, op, MemStore())
    assert json.loads(op.reqs[0][0].data).get("source") == "te"
    op = Opener(ok())
    G.translate_claim(HI, "hi", None, op, MemStore())
    assert "source" not in json.loads(op.reqs[0][0].data)


# ---------------------------------------------------------------- cache and budget
def test_cache_hit_costs_no_call_and_no_budget():
    st, op = MemStore(), Opener(ok())
    a = G.translate_claim(HI, "hi", None, op, st)
    used = dict(st.c)
    b = G.translate_claim(HI, "hi", None, op, st)
    assert len(op.reqs) == 1 and a == b and b["translator"] == "google" and b["detected"] == "hi"
    assert st.c == used
    key = [k for k in st.kv if k.startswith("gt:")][0]
    assert len(key) == 3 + 64
    assert G.usage(st)["chars_today"] == len(HI)


def test_cache_key_depends_on_language():
    st, op = MemStore(), Opener(ok())
    G.translate_claim(TE, "te", None, op, st)
    G.translate_claim(TE, "ta", None, op, st)
    assert len(op.reqs) == 2


def test_budget_exhaustion_falls_back_to_llm(monkeypatch):
    monkeypatch.setenv("SACH_TRANSLATE_MAX_CHARS_PER_DAY", str(len(HI) + 5))
    st, op, llm = MemStore(), Opener(ok()), LLM()
    assert G.translate_claim(HI, "hi", llm, op, st)["translator"] == "google"
    r = G.translate_claim(HI + " नया", "hi", llm, op, st)           # a different text: cache miss, budget gone
    assert r["translator"] == "llm" and llm.t_calls == 1 and len(op.reqs) == 1
    assert G.usage(st)["skipped_over_budget_today"] == 1
    assert G.usage(st)["chars_today"] == len(HI)                      # the refused reservation was given back


def test_per_minute_cap_and_zero_means_unlimited(monkeypatch):
    monkeypatch.setenv("SACH_TRANSLATE_MAX_CHARS_PER_MIN", "10")
    st, op, llm = MemStore(), Opener(ok()), LLM()
    assert G.translate_claim(HI, "hi", llm, op, st)["translator"] == "llm" and op.reqs == []
    monkeypatch.setenv("SACH_TRANSLATE_MAX_CHARS_PER_MIN", "0"); monkeypatch.setenv("SACH_TRANSLATE_MAX_CHARS_PER_DAY", "0")
    assert G.translate_claim(HI, "hi", llm, op, st)["translator"] == "google"


def test_failed_google_call_does_not_use_budget():
    st = MemStore()
    G.translate_claim(HI, "hi", None, Opener(Resp(ok(), 500)), st)
    assert G.usage(st)["chars_today"] == 0


def test_store_errors_fail_open():
    r = G.translate_claim(HI, "hi", LLM(), Opener(ok()), BrokenStore())
    assert r["translator"] == "google" and r["text"] == "Free laptops for all students"


def test_default_budget_values(monkeypatch):
    assert G.max_per_day() == 150000
    monkeypatch.setenv("SACH_TRANSLATE_MAX_CHARS_PER_DAY", "junk")
    assert G.max_per_day() == 150000


# ---------------------------------------------------------------- language refinement
@pytest.mark.parametrize("ours,det,text,want", [
    ("hi", "mr", HI, "mr"), ("hi", "ne", HI, "ne"), ("hi", "gom", HI, "kok"), ("bn", "as", BN, "as"),
    # forbidden changes
    ("mr", "hi", HI, "mr"), ("kok", "hi", HI, "kok"), ("ne", "mr", HI, "ne"), ("as", "bn", BN, "as"),
    ("hi", "bn", HI, "hi"), ("hi", "as", HI, "hi"), ("bn", "mr", BN, "bn"), ("bn", "hi", BN, "bn"),
    ("hi", "mr", "Sabko free laptop milega jaldi forward karo", "hi"),     # Latin script: never
    ("hi", "mr", BN, "hi"), ("bn", "as", HI, "bn"),                         # script-incompatible
    ("te", "ta", TE, "te"), ("hi", None, HI, "hi"), ("hi", "MR ", HI, "mr"),
])
def test_refine_language_rules(ours, det, text, want):
    assert G.refine_language(ours, det, text) == want


# ---------------------------------------------------------------- pipeline
class Retr:
    def __init__(self): self.queries = []
    def search(self, q): self.queries.append(q); return []


class FC:
    def __init__(self): self.queries = []
    def claim_reviews(self, query, language=None): self.queries.append(query); return []


def _matcher(fc=None):
    return match.Matcher(pib_records=[], fc=fc or FC(), today=TODAY)


@pytest.fixture
def gstore(monkeypatch):
    s = MemStore()
    monkeypatch.setattr(store, "get_store", lambda: s)
    return s


def patch_google(monkeypatch, opener):
    real = G.translate
    monkeypatch.setattr(G, "translate", lambda text, source=None, opener_=None, **k: real(text, source, opener))


def test_pipeline_uses_google_and_match_gets_same_english(monkeypatch, gstore):
    patch_google(monkeypatch, Opener(ok("Free laptops for all students")))
    llm, r, fc = LLM(), Retr(), FC()
    res = check_forward(HI, [r], llm, matcher=_matcher(fc), use_cache=False)
    assert llm.t_calls == 0
    assert "Free laptops for all students" in fc.queries               # the match layer got Google's English
    assert r.queries == ["Free laptops for all students"]               # and the live layer reuses it
    assert res["claims"][0]["trace"]["translator"] == "google"
    assert res["claims"][0]["english"] == "Free laptops for all students"
    assert "Translated to English with Google Translate" in trace_block(res)


def test_pipeline_falls_back_to_llm_once(monkeypatch, gstore):
    patch_google(monkeypatch, Opener(Resp(ok(), 500)))
    llm, r = LLM("LLM english"), Retr()
    res = check_forward(HI, [r], llm, matcher=_matcher(), use_cache=False)
    assert llm.t_calls == 1 and r.queries == ["LLM english"]
    assert res["claims"][0]["trace"]["translator"] == "llm"


def test_pipeline_force_live_translates_in_live_layer(monkeypatch, gstore):
    patch_google(monkeypatch, Opener(ok("Free laptops for all students")))
    llm, r = LLM(), Retr()
    res = check_forward(HI, [r], llm, matcher=_matcher(), use_cache=False, force_live=True)
    assert llm.t_calls == 0 and r.queries == ["Free laptops for all students"]
    assert res["claims"][0]["trace"]["translator"] == "google"


def test_pipeline_without_key_is_the_old_llm_path(monkeypatch, gstore):
    monkeypatch.delenv("GOOGLE_TRANSLATE_API_KEY")
    llm, r = LLM("E"), Retr()
    res = check_forward(HI, [r], llm, matcher=_matcher(), use_cache=False)
    assert llm.t_calls == 1 and r.queries == ["E"] and res["claims"][0]["trace"]["translator"] == "llm"


def test_pipeline_budget_exhausted_uses_llm(monkeypatch, gstore):
    monkeypatch.setenv("SACH_TRANSLATE_MAX_CHARS_PER_DAY", "1")
    op = Opener(ok())
    patch_google(monkeypatch, op)
    llm = LLM()
    res = check_forward(HI, [Retr()], llm, matcher=_matcher(), use_cache=False)
    assert op.reqs == [] and llm.t_calls == 1 and res["claims"][0]["trace"]["translator"] == "llm"


def test_english_forward_unchanged_no_translator_call(monkeypatch, gstore):
    op = Opener(ok())
    patch_google(monkeypatch, op)
    llm, r = LLM(), Retr()
    res = check_forward("Government is giving free laptops to all students under a new scheme.", [r], llm, matcher=_matcher(), use_cache=False)
    assert op.reqs == [] and llm.t_calls == 0
    assert res["verdict"] == "UNVERIFIED" and res["input_language"] == "en" and res["claims"][0]["trace"]["translator"] == "none"
    assert res["claims"][0]["english"] == ""


def test_pipeline_refines_language_for_auto_reply_only(monkeypatch, gstore):
    patch_google(monkeypatch, Opener(ok(det="mr")))
    res = check_forward(HI, [Retr()], LLM(), matcher=_matcher(), use_cache=False)
    assert res["input_language"] == "mr" and res["language"] == "mr"
    assert ledger.load()[-1]["language"] == "mr"
    G.reset()
    patch_google(monkeypatch, Opener(ok("Another english claim here", det="mr")))
    res = check_forward(HI + " दूसरा", [Retr()], LLM(), matcher=_matcher(), use_cache=False, reply_lang="en")
    assert res["language"] == "en" and res["input_language"] == "mr"        # a chosen reply language is never overridden


def test_pipeline_does_not_downgrade_marker_detected_marathi(monkeypatch, gstore):
    patch_google(monkeypatch, Opener(ok(det="hi")))
    mr = "सरकार सर्वांना मोफत लॅपटॉप देणार आहे आणि हे सर्व विद्यार्थ्यांसाठी आहे"
    res = check_forward(mr, [Retr()], LLM(), matcher=_matcher(), use_cache=False)
    assert res["input_language"] == "mr"


# ---------------------------------------------------------------- status page
def test_status_line_no_secrets(monkeypatch):
    st = MemStore()
    G.translate_claim(HI, "hi", None, Opener(ok()), st)
    d = status.status_data(None, [], st=st)
    g = d["google_translation"]
    assert g["configured"] is True and g["chars_today"] == len(HI) and g["max_chars_per_day"] == 150000
    page = status.status_page(d).decode()
    assert "Google Translation" in page and "150000" in page and KEY not in page and KEY not in json.dumps(d)
    monkeypatch.delenv("GOOGLE_TRANSLATE_API_KEY")
    assert status.status_data(None, [], st=st)["google_translation"]["configured"] is False
