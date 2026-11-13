"""VERTEX work package: Google Cloud Vertex AI Gemini as an AI judge. Fully offline: fake openers, a throwaway RSA key generated at
test time (never committed), openssl used as an independent signature check only when the binary exists."""
import base64, io, json, os, secrets, shutil, subprocess, threading, time, traceback, urllib.error
import pytest
from sach import limits, llm as L, status, vertex as V

EMAIL, PROJECT = "sa-test@proj-test-123.iam.gserviceaccount.com", "proj-test-123"


# ---------------------------------------------------------------- a throwaway RSA key, built here (independent of sach/vertex.py)
def _is_prime(n, rounds=24):
    if n < 4 or n % 2 == 0:
        return n in (2, 3)
    d, s = n - 1, 0
    while d % 2 == 0:
        d, s = d // 2, s + 1
    for _ in range(rounds):
        x = pow(secrets.randbelow(n - 3) + 2, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True

def _prime(bits):
    while True:
        c = secrets.randbits(bits) | (3 << (bits - 2)) | 1          # top two bits set: the product has the full bit length
        if _is_prime(c):
            return c

def _tlv(tag, content):
    n = len(content)
    ln = bytes([n]) if n < 128 else (b"\x82" + n.to_bytes(2, "big") if n < 65536 else b"\x83" + n.to_bytes(3, "big"))
    return bytes([tag]) + ln + content

def _int(i):
    return _tlv(2, i.to_bytes((i.bit_length() + 8) // 8, "big"))

def _pem(label, der):
    b = base64.b64encode(der).decode()
    return "-----BEGIN %s-----\n%s\n-----END %s-----\n" % (label, "\n".join(b[i:i + 64] for i in range(0, len(b), 64)), label)

@pytest.fixture(scope="module")
def rsa():
    e = 65537
    while True:
        p, q = _prime(512), _prime(512)
        n, phi = p * q, (p - 1) * (q - 1)
        if p != q and phi % e:
            break
    d = pow(e, -1, phi)
    rsakey = _tlv(0x30, b"".join(_int(x) for x in (0, n, e, d, p, q, d % (p - 1), d % (q - 1), pow(q, -1, p))))
    alg = _tlv(0x30, bytes.fromhex("06092a864886f70d0101010500"))
    p8 = _tlv(0x30, _int(0) + alg + _tlv(4, rsakey))
    return {"n": n, "e": e, "d": d, "pkcs8_pem": _pem("PRIVATE KEY", p8), "pkcs1_pem": _pem("RSA PRIVATE KEY", rsakey)}

def _expected_block(message, k):
    t = bytes.fromhex("3031300d060960864801650304020105000420") + __import__("hashlib").sha256(message).digest()
    return b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t

def _sa_json(rsa, **over):
    d = {"type": "service_account", "project_id": PROJECT, "client_email": EMAIL, "private_key": rsa["pkcs8_pem"],
         "token_uri": "https://oauth2.googleapis.com/token"}
    d.update(over)
    return json.dumps(d)

@pytest.fixture
def sa(rsa):
    return V.ServiceAccount.from_json(_sa_json(rsa))


# ---------------------------------------------------------------- fakes
class Resp:
    def __init__(self, obj):
        self._b = json.dumps(obj).encode()
    def read(self, n=-1):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

def http_error(code, url="https://x", headers=None, body=b"{}"):
    return urllib.error.HTTPError(url, code, "err", headers or {}, io.BytesIO(body))

class FakeGoogle:
    """opener(req, timeout): routes the token endpoint and generateContent; records every request."""
    def __init__(self, rsa=None, text="NEITHER", token="ya29.FAKE-ACCESS-TOKEN-abcdef", expires_in=3600, delay=0):
        self.reqs, self.text, self.token, self.expires_in, self.delay = [], text, token, expires_in, delay
        self.token_error = None          # exception to raise from the token endpoint
        self.gen_error = None            # exception (or callable(model) -> exception/None) from generateContent
        self.lock = threading.Lock()
    def __call__(self, req, timeout=None):
        url = req.full_url
        with self.lock:
            self.reqs.append(req)
        if url == V.TOKEN_URL:
            if self.delay:
                time.sleep(self.delay)
            if self.token_error:
                raise self.token_error
            return Resp({"access_token": self.token, "expires_in": self.expires_in, "token_type": "Bearer"})
        err = self.gen_error(url) if callable(self.gen_error) else self.gen_error
        if err:
            raise err
        return Resp({"candidates": [{"content": {"parts": [{"text": self.text}]}}]})
    def token_calls(self):
        return [r for r in self.reqs if r.full_url == V.TOKEN_URL]
    def gen_calls(self):
        return [r for r in self.reqs if r.full_url != V.TOKEN_URL]

def make_judge(sa, g, clock=time.time, **kw):
    client = V.VertexClient(sa, V.TokenProvider(sa, g, clock), g)
    return L.VertexJudge(client, **kw)

DEBUNK_T = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
DEBUNK_X = "A media report said the retirement age would be reduced to 50 years. This is fake; no such proposal exists."
CLAIM = "Central Government will reduce the retirement age of employees to 50 years."
REPLY = "CONTRADICTS | This is fake; no such proposal exists."


# ---------------------------------------------------------------- RS256 + DER
def test_der_parses_pkcs8_and_pkcs1(rsa):
    for pem in (rsa["pkcs8_pem"], rsa["pkcs1_pem"]):
        assert V.parse_private_key_pem(pem) == (rsa["n"], rsa["e"], rsa["d"])

@pytest.mark.parametrize("bad", ["", "not a key", "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n!!!!\n-----END PRIVATE KEY-----"])
def test_der_rejects_garbage(bad):
    with pytest.raises(ValueError):
        V.parse_private_key_pem(bad)

def test_der_rejects_truncated_and_non_rsa(rsa):
    der = base64.b64decode("".join(rsa["pkcs8_pem"].splitlines()[1:-2]))
    for cut in (10, 60, len(der) - 3):
        with pytest.raises(ValueError):
            V.parse_private_key_der(der[:cut])
    with pytest.raises(ValueError):                         # the algorithm is not rsaEncryption
        V.parse_private_key_der(der.replace(bytes.fromhex("2a864886f70d010101"), bytes.fromhex("2a864886f70d010102"), 1))

def test_rs256_matches_the_padded_block_and_verifies(rsa):
    key = V.parse_private_key_pem(rsa["pkcs8_pem"])
    k = (rsa["n"].bit_length() + 7) // 8
    for msg in (b"", b"a.b", b"x" * 5000):
        sig = V.rs256_sign(msg, key)
        assert len(sig) == k
        assert pow(int.from_bytes(sig, "big"), rsa["e"], rsa["n"]).to_bytes(k, "big") == _expected_block(msg, k)
        # PKCS#1 v1.5 is deterministic: blinding must not change the signature
        assert sig == pow(int.from_bytes(_expected_block(msg, k), "big"), rsa["d"], rsa["n"]).to_bytes(k, "big")
        assert V.rs256_sign(msg, key) == sig

def test_rs256_refuses_a_faulty_key(rsa):
    with pytest.raises(V.VertexError):
        V.rs256_sign(b"m", (rsa["n"], rsa["e"], rsa["d"] + 2))

@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl binary not available")
def test_rs256_verified_by_openssl(tmp_path):
    def run(*a, **kw):
        return subprocess.run(["openssl", *a], check=True, capture_output=True, **kw)
    k1, k8, pub, msg, sigf = (str(tmp_path / n) for n in ("k1.pem", "k8.pem", "pub.pem", "msg", "sig"))
    run("genrsa", "-out", k1, "2048")
    run("pkcs8", "-topk8", "-nocrypt", "-in", k1, "-out", k8)
    run("rsa", "-in", k1, "-pubout", "-out", pub)
    pem = open(k8).read()
    assert "BEGIN PRIVATE KEY" in pem
    key = V.parse_private_key_pem(pem)
    message = b"eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ4In0"
    open(msg, "wb").write(message)
    open(sigf, "wb").write(V.rs256_sign(message, key))
    out = run("dgst", "-sha256", "-verify", pub, "-signature", sigf, msg).stdout
    assert b"Verified OK" in out
    open(msg, "wb").write(message + b"!")                      # and a different message must NOT verify
    with pytest.raises(subprocess.CalledProcessError):
        run("dgst", "-sha256", "-verify", pub, "-signature", sigf, msg)


# ---------------------------------------------------------------- credential
def test_service_account_from_env_raw_base64_and_escaped_newlines(rsa, monkeypatch):
    raw = _sa_json(rsa)
    for val in (raw, base64.b64encode(raw.encode()).decode(), base64.urlsafe_b64encode(raw.encode()).decode().rstrip("="),
                _sa_json(rsa, private_key=rsa["pkcs8_pem"].replace("\n", "\\n"))):
        monkeypatch.setenv("GOOGLE_SA_JSON", val)
        sa = V.ServiceAccount.from_env()
        assert sa.client_email == EMAIL and sa.project_id == PROJECT
        assert sa.sign(b"x") == V.rs256_sign(b"x", (rsa["n"], rsa["e"], rsa["d"]))

def test_service_account_unset_is_none_and_invalid_is_generic(rsa, monkeypatch):
    assert V.ServiceAccount.from_env() is None and not V.configured()
    for bad in ("{}", "garbage!!", _sa_json(rsa, private_key="nope"), _sa_json(rsa, client_email=""), _sa_json(rsa, project_id="a b/../c")):
        monkeypatch.setenv("GOOGLE_SA_JSON", bad)
        with pytest.raises(ValueError) as ei:
            V.ServiceAccount.from_env()
        assert str(ei.value) == "GOOGLE_SA_JSON is not a valid service-account key"
        assert ei.value.__cause__ is None and ei.value.__suppress_context__

def test_service_account_never_prints(sa, rsa):
    for s in (repr(sa), str(sa), repr(V.VertexClient(sa)), repr(V.TokenProvider(sa))):
        assert EMAIL not in s and PROJECT not in s and str(rsa["n"]) not in s


# ---------------------------------------------------------------- token provider
def test_jwt_is_well_formed_and_verifies(sa, rsa):
    g, now = FakeGoogle(), 1_700_000_000
    V.TokenProvider(sa, g, lambda: now).token()
    req = g.token_calls()[0]
    assert req.get_method() == "POST" and req.get_header("Content-type") == "application/x-www-form-urlencoded"
    form = dict(x.split("=", 1) for x in req.data.decode().split("&"))
    assert form["grant_type"] == "urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
    h, c, s = form["assertion"].split(".")
    dec = lambda x: base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))
    assert json.loads(dec(h)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(dec(c)) == {"iss": EMAIL, "scope": "https://www.googleapis.com/auth/cloud-platform",
                                  "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}
    k = (rsa["n"].bit_length() + 7) // 8
    assert pow(int.from_bytes(dec(s), "big"), rsa["e"], rsa["n"]).to_bytes(k, "big") == _expected_block(("%s.%s" % (h, c)).encode(), k)

def test_token_is_cached_and_refreshed_five_minutes_before_expiry(sa):
    g, t = FakeGoogle(expires_in=3600), [1000.0]
    tp = V.TokenProvider(sa, g, lambda: t[0])
    a = tp.token()
    t[0] = 1000 + 3600 - 301
    assert tp.token() == a and len(g.token_calls()) == 1
    t[0] = 1000 + 3600 - 299
    g.token = "ya29.SECOND"
    assert tp.token() == "ya29.SECOND" and len(g.token_calls()) == 2

def test_failed_refresh_is_cached_for_30_seconds(sa):
    g, t = FakeGoogle(), [5000.0]
    g.token_error = http_error(400, V.TOKEN_URL, body=b'{"error":"invalid_grant"}')
    tp = V.TokenProvider(sa, g, lambda: t[0])
    for i in range(5):
        with pytest.raises(V.VertexError) as ei:
            tp.token()
        assert ei.value.code == 401                                  # a bad credential reads as an auth failure
    assert len(g.token_calls()) == 1                                 # the other four never reached Google
    t[0] += 31
    g.token_error = None
    assert tp.token() and len(g.token_calls()) == 2                  # after 30 s it tries again and recovers

def test_failed_refresh_on_network_error_is_also_backed_off(sa):
    g, t = FakeGoogle(), [1.0]
    g.token_error = urllib.error.URLError(TimeoutError())
    tp = V.TokenProvider(sa, g, lambda: t[0])
    with pytest.raises(TimeoutError):
        tp.token()
    for _ in range(2):
        with pytest.raises(V.VertexError) as ei:
            tp.token()
        assert ei.value.code is None                                 # a network blip must not read as a bad credential
    assert len(g.token_calls()) == 1

def test_only_one_refresh_at_a_time(sa):
    g = FakeGoogle(delay=0.15)
    tp = V.TokenProvider(sa, g)
    out = []
    ts = [threading.Thread(target=lambda: out.append(tp.token())) for _ in range(8)]
    [x.start() for x in ts]; [x.join() for x in ts]
    assert len(g.token_calls()) == 1 and len(set(out)) == 1 and len(out) == 8

def test_shared_provider_is_one_per_credential(sa):
    assert V.shared_provider(sa) is V.shared_provider(sa)


# ---------------------------------------------------------------- request shape + response parsing
def test_request_shape(sa):
    g = FakeGoogle(text=REPLY)
    j = make_judge(sa, g)
    assert j.models == ["gemini-3.1-flash-lite", "gemini-3.8-flash"] and j.name == "vertex"
    assert j._raw("gemini-3.1-flash-lite", "SYS", "USER", 77) == REPLY
    req = g.gen_calls()[0]
    assert req.full_url == ("https://aiplatform.googleapis.com/v1/projects/proj-test-123/locations/global/publishers/google/models/"
                            "gemini-3.1-flash-lite:generateContent")
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer ya29.FAKE-ACCESS-TOKEN-abcdef"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == {"systemInstruction": {"parts": [{"text": "SYS"}]},
                                    "contents": [{"role": "user", "parts": [{"text": "USER"}]}],
                                    "generationConfig": {"temperature": 0, "maxOutputTokens": 77}}
    assert "key=" not in req.full_url and "us-central1" not in req.full_url

def test_models_env_override_and_bad_model_name(sa, monkeypatch):
    monkeypatch.setenv("SACH_VERTEX_MODELS", "gemini-x, gemini-y")
    assert make_judge(sa, FakeGoogle()).models == ["gemini-x", "gemini-y"]
    g = FakeGoogle()
    with pytest.raises(V.VertexError):
        V.VertexClient(sa, V.TokenProvider(sa, g), g).generate("../evil?x=1", {})
    assert not g.gen_calls()

def test_stance_parses_and_validates_like_gemini(sa):
    j = make_judge(sa, FakeGoogle(text=REPLY))
    assert j.stance(CLAIM, DEBUNK_T, DEBUNK_X, tier="pib_debunk") == "contradicts"
    assert make_judge(sa, FakeGoogle(text="NEITHER")).stance(CLAIM, DEBUNK_T, DEBUNK_X) == "none"
    # a quote that is not on the page fails the verbatim validation: the judge cannot be talked into a verdict
    assert make_judge(sa, FakeGoogle(text="CONTRADICTS | invented quote")).stance(CLAIM, DEBUNK_T, DEBUNK_X) == "none"

def test_translate_and_ocr_reuse_the_gemini_paths(sa):
    g = FakeGoogle(text="  Hello  ")
    j = make_judge(sa, g)
    assert j.translate("नमस्ते") == "Hello"
    assert j.transcribe_image(b"\x89PNG....", "image/png") == "  Hello  "
    assert "inlineData" in g.gen_calls()[-1].data.decode()


# ---------------------------------------------------------------- failure handling
def test_401_pauses_provider_ten_minutes_and_failover_continues(sa):
    g = FakeGoogle(); g.gen_error = http_error(401)
    vj = make_judge(sa, g)
    nxt = type("N", (), {"name": "next", "models": ["m"], "failures": 0, "exhausted_until": 0.0,
                         "available": lambda s: True, "stance": lambda s, *a, **k: "contradicts"})()
    f = L.FailoverJudge([vj, nxt])
    assert f.stance(CLAIM, DEBUNK_T, DEBUNK_X) == "contradicts"
    assert not vj.available() and 500 < vj.exhausted_until - time.time() <= 601
    n = len(g.gen_calls())
    assert f.stance(CLAIM, DEBUNK_T, DEBUNK_X) == "contradicts"
    assert len(g.gen_calls()) == n                                    # paused: not called again

def test_403_also_pauses(sa):
    g = FakeGoogle(); g.gen_error = http_error(403)
    vj = make_judge(sa, g)
    with pytest.raises(Exception):
        vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert not vj.available()

def test_token_auth_failure_pauses_provider(sa):
    g = FakeGoogle(); g.token_error = http_error(400, V.TOKEN_URL)
    vj = make_judge(sa, g)
    with pytest.raises(Exception):
        vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert not vj.available() and not g.gen_calls()

def test_429_pauses_that_model_and_the_next_provider_answers(sa):
    g = FakeGoogle(); g.gen_error = http_error(429, headers={"retry-after": "42"})
    vj = make_judge(sa, g)
    nxt = type("N", (), {"name": "next", "models": ["m"], "failures": 0, "exhausted_until": 0.0,
                         "available": lambda s: True, "stance": lambda s, *a, **k: "confirms"})()
    assert L.FailoverJudge([vj, nxt]).stance(CLAIM, DEBUNK_T, DEBUNK_X) == "confirms"
    p = vj._pauses()
    assert set(p) == {"gemini-3.1-flash-lite", "gemini-3.8-flash"} and all(30 < t - time.time() <= 43 for t in p.values())
    assert not vj.available()                                         # every model paused, no usable model left

def test_5xx_fails_over_without_benching_the_key(sa):
    g = FakeGoogle(); g.gen_error = lambda url: http_error(503) if "3.1-flash-lite" in url else None
    g.text = REPLY
    vj = make_judge(sa, g)
    # model 1 gave 503, model 2 answered; with no third model the deterministic heuristic is the second opinion
    assert vj.stance(CLAIM, DEBUNK_T, DEBUNK_X, tier="pib_debunk") == "contradicts"
    assert vj.available()

def test_timeout_pauses_only_that_model(sa):
    g = FakeGoogle(); g.gen_error = lambda url: urllib.error.URLError(TimeoutError("t")) if "3.1-flash-lite" in url else None
    vj = make_judge(sa, g)
    vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert list(vj._pauses()) == ["gemini-3.1-flash-lite"] and vj.available()


# ---------------------------------------------------------------- spend guard
def test_daily_cap_blocks_calls_and_pauses_until_utc_midnight(sa, monkeypatch):
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "2")
    g = FakeGoogle(text="NEITHER")
    vj = make_judge(sa, g)
    vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)                              # 1 call (a 'none' needs no second opinion)
    vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)                              # 2
    assert len(g.gen_calls()) == 2 and vj.available()
    with pytest.raises(V.VertexCapReached):
        vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)                          # over the cap: no HTTP call at all
    assert len(g.gen_calls()) == 2
    left = vj.exhausted_until - time.time()
    assert 0 < left <= 86400 + 1 and not vj.available()
    u = V.usage()
    assert u["calls_today"] == 2 and u["max_per_day"] == 2 and u["skipped_over_cap_today"] >= 1

def test_cap_exhausted_provider_is_skipped_by_failover(sa, monkeypatch):
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "1")
    g = FakeGoogle(text="NEITHER")
    vj = make_judge(sa, g)
    seen = []
    nxt = type("N", (), {"name": "next", "models": ["m"], "failures": 0, "exhausted_until": 0.0,
                         "available": lambda s: True, "stance": lambda s, *a, **k: seen.append(1) or "none"})()
    f = L.FailoverJudge([vj, nxt])
    f.stance(CLAIM, DEBUNK_T, DEBUNK_X); f.stance(CLAIM, DEBUNK_T, DEBUNK_X); f.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert len(g.gen_calls()) == 1 and len(seen) == 2 and f.failures == 0
    assert dict(f.describe())["vertex"] == "cooling down"

def test_cap_counts_in_the_shared_store_and_zero_means_unlimited(sa, monkeypatch):
    from test_scale import FakeStore
    st = FakeStore()
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "3")
    now = 1_800_000_000.0
    for _ in range(3):
        V.reserve_call(st, now)
    with pytest.raises(V.VertexCapReached):
        V.reserve_call(st, now)
    assert V.usage(st, now)["calls_today"] == 3
    V.reserve_call(st, now + 86400)                                   # next UTC day: a fresh window
    assert V.usage(st, now + 86400)["calls_today"] == 1
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "0")
    for _ in range(10):
        V.reserve_call(FakeStore(), now)

def test_broken_store_falls_back_to_memory(monkeypatch):
    from test_scale import FakeStore
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "2")
    st = FakeStore(broken=True)
    V.reserve_call(st); V.reserve_call(st)
    with pytest.raises(V.VertexCapReached):
        V.reserve_call(st)

def test_default_cap_is_4000(monkeypatch):
    assert V.max_per_day() == 4000


# ---------------------------------------------------------------- wiring
def _env_keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "GEMINI_API_KEYS", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GROQ_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY",
              "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "ANTHROPIC_API_KEY", "SACH_JUDGE_ORDER"):
        monkeypatch.delenv(k, raising=False)

def test_vertex_first_only_when_configured(rsa, monkeypatch):
    _env_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g1"); monkeypatch.setenv("GROQ_API_KEY", "q"); monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    assert [j.name.split("-")[0] for j in L.build_judges()] == ["groq", "gemini", "openrouter"]          # off: no behaviour change
    monkeypatch.setenv("GOOGLE_SA_JSON", _sa_json(rsa))
    assert [j.name.split("-")[0] for j in L.build_judges()] == ["vertex", "groq", "gemini", "openrouter"]
    monkeypatch.setenv("SACH_JUDGE_ORDER", "groq,gemini,vertex")                                           # explicit order still wins
    assert [j.name.split("-")[0] for j in L.build_judges()] == ["groq", "gemini", "vertex", "openrouter"]
    assert L.DEFAULT_JUDGE_ORDER == "groq,gemini,openrouter,mistral,cloudflare,claude"

def test_vertex_alone_and_get_llm(rsa, monkeypatch):
    _env_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_SA_JSON", base64.b64encode(_sa_json(rsa).encode()).decode())
    f = L.get_llm()
    assert [j.name for j in f.judges] == ["vertex"] and f.models == ["gemini-3.1-flash-lite", "gemini-3.8-flash"]

def test_invalid_credential_is_simply_off(monkeypatch):
    _env_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_SA_JSON", "this is not json")
    assert L.build_judges() == [] and L.get_llm() is None


# ---------------------------------------------------------------- status
def test_status_row_has_counts_and_no_identity(sa, rsa, monkeypatch):
    g = FakeGoogle(text="NEITHER")
    vj = make_judge(sa, g)
    vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "10")
    f = type("F", (), {"judges": [vj]})()
    row = {r["provider"]: r for r in status.ai_providers(f)}["vertex"]
    assert row["configured"] is True and row["state"] == "ready" and row["calls_today"] == 1 and row["max_per_day"] == 10
    d = status.status_data(f, [])
    blob = json.dumps(d) + status.status_page(d).decode()
    for secret in (EMAIL, PROJECT, "proj-test", "FAKE-ACCESS", str(rsa["n"]), "BEGIN PRIVATE"):
        assert secret not in blob
    assert "1 of 10" in status.status_page(d).decode()

def test_status_row_when_off_and_when_cap_paused(sa, monkeypatch):
    off = {r["provider"]: r for r in status.ai_providers(type("F", (), {"judges": []})())}["vertex"]
    assert off["configured"] is False and off["state"] == "off" and off["calls_today"] == 0 and off["max_per_day"] == 4000
    monkeypatch.setenv("SACH_VERTEX_MAX_PER_DAY", "1")
    vj = make_judge(sa, FakeGoogle(text="NEITHER"))
    vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    with pytest.raises(V.VertexCapReached):
        vj.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    row = {r["provider"]: r for r in status.ai_providers(type("F", (), {"judges": [vj]})())}["vertex"]
    assert row["state"] == "paused" and row["calls_today"] == 1 and row["skipped_over_cap_today"] == 1


# ---------------------------------------------------------------- secrets never leak
def _everything(exc):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + repr(exc) + str(exc) + repr(getattr(exc, "headers", ""))

def test_secrets_never_in_errors_logs_or_reprs(sa, rsa, caplog, capsys):
    caplog.set_level("DEBUG")
    key_bits = ["".join(rsa["pkcs8_pem"].splitlines()[1:-2])[:60], str(rsa["d"])[:40], "BEGIN PRIVATE KEY"]
    captured = {}
    class Leaky(FakeGoogle):                                           # an opener whose exceptions echo the request, worst case
        def __call__(self, req, timeout=None):
            if req.full_url == V.TOKEN_URL:
                captured["jwt"] = req.data.decode()
                raise RuntimeError("boom " + req.data.decode() + " " + str(key_bits))
            captured["auth"] = req.get_header("Authorization")
            raise http_error(500, "https://x/?token=" + (req.get_header("Authorization") or ""), body=req.data)
    jud = make_judge(sa, Leaky())
    with pytest.raises(Exception) as ei:
        jud.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    text = _everything(ei.value)
    assert captured["jwt"].split("assertion=")[1][:40] not in text and not any(b in text for b in key_bits)
    # now the same for generateContent errors, where the token IS known
    g = FakeGoogle(); g.gen_error = lambda url: RuntimeError("boom Bearer " + g.token)
    jud = make_judge(sa, g)
    with pytest.raises(Exception) as ei:
        jud.stance(CLAIM, DEBUNK_T, DEBUNK_X)
    text = _everything(ei.value)
    assert g.token not in text and "Bearer" not in text
    g.gen_error = http_error(401, "https://x/" + g.token)
    with pytest.raises(Exception) as ei2:
        make_judge(sa, g).stance(CLAIM, DEBUNK_T, DEBUNK_X)
    assert g.token not in _everything(ei2.value)
    jwt = g.token_calls()[0].data.decode().split("assertion=")[1]
    out = capsys.readouterr()
    for blob in (caplog.text, out.out, out.err, _everything(ei2.value)):
        assert g.token not in blob and jwt[:30] not in blob and not any(b in blob for b in key_bits)

def test_status_and_judge_names_never_contain_credentials(sa, rsa):
    vj = make_judge(sa, FakeGoogle())
    assert vj.name == "vertex" and EMAIL not in vj.name + PROJECT * 0
    assert [n for n, _ in L.FailoverJudge([vj]).describe()] == ["vertex"]
