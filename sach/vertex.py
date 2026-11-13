"""Google Cloud Vertex AI (Gemini) as an AI-judge transport, paid from the owner's Google Cloud credit instead of the exhausted free tier.

Who calls it: sach/llm.py (VertexJudge, build_judges) and sach/status.py (usage). Off unless GOOGLE_SA_JSON is set: with no credential
nothing here runs and the judge chain behaves exactly as before.

Facts (tested by the project owner with a real token):
- Endpoint: POST https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google/models/{MODEL}:generateContent
  with `Authorization: Bearer <OAuth2 access token>`. Only the `global` location serves our models (regional ones return 404).
  A plain API key is NOT accepted by Vertex (401): OAuth is required. The body and the response have the same shape as the AI Studio
  Gemini API (`candidates[0].content.parts[0].text`), so VertexJudge reuses the Gemini judge's parsing.
- Auth: a service-account JSON key (`client_email`, `private_key` PEM PKCS#8 RSA, `project_id`). A JWT (RS256) is exchanged at
  https://oauth2.googleapis.com/token for a one-hour access token (grant_type urn:ietf:params:oauth:grant-type:jwt-bearer).
- The runtime is stdlib-only (no `cryptography`), so RS256 is implemented here: a small DER reader, EMSA-PKCS1-v1_5 with SHA-256, and
  `pow(m, d, n)` with base blinding and a verification of the result before it is used (protects against faulty signatures).
  The service account should hold ONLY roles/aiplatform.user.

Spend guard: Vertex is billed. A daily call cap (SACH_VERTEX_MAX_PER_DAY, default 4000, 0 = unlimited) is counted with the shared
counter in sach/store.py on UTC-day keys (same pattern as sach/limits.py, memory fallback when no store). Attempts are counted, failed
ones are not given back (conservative: the cap is a spend ceiling).

Secrets: the private key, the JWT and the access token never appear in a log line, an exception message, a repr or a return value of
anything public. Every error raised from here is a VertexError (or TimeoutError) with a generic message built by this module, never the
text of an underlying exception, which could echo a request. stdlib only."""
from __future__ import annotations
import base64, hashlib, json, os, re, secrets, threading, time, urllib.error, urllib.parse, urllib.request
from . import limits, store

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
HOST = "https://aiplatform.googleapis.com"
DEFAULT_MODELS = "gemini-3.1-flash-lite,gemini-3.8-flash"
DEFAULT_MAX_PER_DAY = 4000
REFRESH_MARGIN_S = 300            # a token is replaced 5 minutes before it expires
FAILED_REFRESH_S = 30             # a failed token refresh is remembered this long so a broken credential does not hammer Google
AUTH_PAUSE_S = 600                # 401/403 from Vertex: the provider is benched this long
MAX_RESPONSE = 2_000_000

_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")   # DER DigestInfo prefix for SHA-256
_RSA_OID = bytes.fromhex("06092a864886f70d010101")                          # rsaEncryption


class VertexError(Exception):
    """Generic failure. `code` is the HTTP status when there was one; `headers` carries the response headers (Retry-After). The message is
    always written by this module."""
    def __init__(self, msg, code=None, headers=None):
        super().__init__(msg)
        self.code, self.headers = code, headers or {}


class VertexCapReached(VertexError):
    """The daily call cap is used up: the provider is paused until 00:00 UTC."""


# ---------------------------------------------------------------- RS256 (stdlib only)
def _der(buf: bytes, pos: int):
    """One DER element at `pos` -> (tag, content_start, content_end)."""
    if pos + 2 > len(buf):
        raise ValueError("der")
    tag, ln, pos = buf[pos], buf[pos + 1], pos + 2
    if ln & 0x80:
        nb = ln & 0x7F
        if nb == 0 or nb > 4 or pos + nb > len(buf):
            raise ValueError("der")
        ln, pos = int.from_bytes(buf[pos:pos + nb], "big"), pos + nb
    if pos + ln > len(buf):
        raise ValueError("der")
    return tag, pos, pos + ln

def _children(buf: bytes, start: int, end: int) -> list:
    out, pos = [], start
    while pos < end:
        tag, s, e = _der(buf, pos)
        out.append((tag, s, e))
        pos = e
    if pos != end:
        raise ValueError("der")
    return out

def parse_private_key_der(der: bytes) -> tuple:
    """PKCS#8 PrivateKeyInfo (or a bare PKCS#1 RSAPrivateKey) -> (n, e, d)."""
    tag, s, e = _der(der, 0)
    if tag != 0x30 or e != len(der):
        raise ValueError("der")
    kids = _children(der, s, e)
    if len(kids) >= 3 and kids[1][0] == 0x30 and kids[2][0] == 0x04:         # PKCS#8: version, AlgorithmIdentifier, OCTET STRING
        if _RSA_OID not in der[kids[1][1]:kids[1][2]]:
            raise ValueError("not an RSA key")
        inner = der[kids[2][1]:kids[2][2]]
        tag, s, e = _der(inner, 0)
        if tag != 0x30 or e != len(inner):
            raise ValueError("der")
        kids, der = _children(inner, s, e), inner
    if len(kids) < 4 or any(k[0] != 0x02 for k in kids[:4]):                  # RSAPrivateKey: version, n, e, d, ...
        raise ValueError("der")
    n, pub, d = (int.from_bytes(der[k[1]:k[2]], "big") for k in kids[1:4])
    if n.bit_length() < 1024 or not (1 < pub < n) or not (1 < d < n):
        raise ValueError("weak or malformed key")
    return n, pub, d

def parse_private_key_pem(pem: str) -> tuple:
    m = re.search(r"-----BEGIN (?:RSA )?PRIVATE KEY-----(.*?)-----END (?:RSA )?PRIVATE KEY-----", pem or "", re.S)
    if not m:
        raise ValueError("pem")
    return parse_private_key_der(base64.b64decode("".join(m.group(1).split()), validate=True))

def rs256_sign(message: bytes, key: tuple) -> bytes:
    """RSASSA-PKCS1-v1_5 with SHA-256. `key` = (n, e, d)."""
    n, e, d = key
    k = (n.bit_length() + 7) // 8
    t = _SHA256_PREFIX + hashlib.sha256(message).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    m = int.from_bytes(em, "big")
    r = secrets.randbelow(n - 3) + 2                                           # blinding: the private exponent never meets m directly
    while True:
        try:
            rinv = pow(r, -1, n)
            break
        except ValueError:
            r = secrets.randbelow(n - 3) + 2
    s = (pow(m * pow(r, e, n) % n, d, n) * rinv) % n
    if pow(s, e, n) != m:                                                      # a faulty computation is never released
        raise VertexError("vertex: signing failed")
    return s.to_bytes(k, "big")

def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


# ---------------------------------------------------------------- credential
class ServiceAccount:
    """The parts of a service-account key we need. Never printable: repr and str hide everything."""
    __slots__ = ("client_email", "project_id", "_key", "_fp")

    def __init__(self, client_email: str, project_id: str, key: tuple):
        self.client_email, self.project_id, self._key = client_email, project_id, key
        self._fp = hashlib.sha256(("%s\x00%s\x00%d" % (client_email, project_id, key[0])).encode()).hexdigest()[:16]

    def __repr__(self):
        return "<ServiceAccount redacted>"
    __str__ = __repr__

    @property
    def fingerprint(self) -> str:
        return self._fp

    def sign(self, message: bytes) -> bytes:
        return rs256_sign(message, self._key)

    @classmethod
    def from_json(cls, raw: str) -> "ServiceAccount":
        """`raw` is the key file's JSON, or base64 of it. A generic ValueError on anything wrong (the content is never echoed)."""
        try:
            text = (raw or "").strip()
            if not text.startswith("{"):
                text = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_" if ("-" in text or "_" in text) else None).decode("utf-8")
            info = json.loads(text)
            email, project, pem = info["client_email"], info["project_id"], info["private_key"]
            if not all(isinstance(x, str) and x for x in (email, project, pem)):
                raise ValueError
            if "\n" not in pem:
                pem = pem.replace("\\n", "\n")                                # a pasted key whose newlines were escaped twice
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,100}", project) or not re.fullmatch(r"[^\s@]{1,100}@[^\s@]{1,200}", email):
                raise ValueError
            return cls(email, project, parse_private_key_pem(pem))
        except Exception:
            raise ValueError("GOOGLE_SA_JSON is not a valid service-account key") from None

    @classmethod
    def from_env(cls, env=None):
        """-> ServiceAccount, or None when GOOGLE_SA_JSON is not set. Raises ValueError (generic text) when it is set but unusable."""
        raw = (env if env is not None else os.environ).get("GOOGLE_SA_JSON", "")
        return cls.from_json(raw) if raw.strip() else None


def configured(env=None) -> bool:
    return bool(((env if env is not None else os.environ).get("GOOGLE_SA_JSON") or "").strip())


# ---------------------------------------------------------------- HTTP helper: generic errors only
def _call(opener, req, timeout, what, auth=False):
    """-> parsed JSON. Any failure becomes a VertexError/TimeoutError with a generic message; the original exception (which may echo a
    request) is dropped, not chained. `auth` marks the token endpoint: its 400/401/403 mean the credential is bad (code 401)."""
    code = headers = None
    kind = ""
    try:
        with opener(req, timeout=timeout) as r:
            return json.loads(r.read(MAX_RESPONSE).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        code = int(e.code)
        try:
            headers = {"retry-after": e.headers.get("retry-after")} if e.headers is not None and e.headers.get("retry-after") else {}
        except Exception:
            headers = {}
        kind = "http"
    except (TimeoutError, OSError) as e:                                         # socket.timeout is TimeoutError; URLError is an OSError
        reason = getattr(e, "reason", e)
        kind = "timeout" if isinstance(e, TimeoutError) or isinstance(reason, TimeoutError) else "network"
    except Exception:
        kind = "other"
    if kind == "timeout":
        raise TimeoutError("vertex: %s timed out" % what)
    if kind == "http":
        if auth and code in (400, 401, 403):
            code = 401
        raise VertexError("vertex: %s failed with HTTP %d" % (what, code), code, headers)
    raise VertexError("vertex: %s failed (%s)" % (what, "network error" if kind == "network" else "unreadable reply"))


# ---------------------------------------------------------------- token cache
class TokenProvider:
    """OAuth2 access token for a service account, cached in memory. Thread-safe; only one refresh runs at a time (the others wait and
    then use its result). A failed refresh is remembered for FAILED_REFRESH_S and re-raised without calling Google."""
    def __init__(self, sa: ServiceAccount, opener=None, clock=time.time):
        self._sa, self._opener, self._clock = sa, opener or urllib.request.urlopen, clock
        self._lock = threading.Lock()
        self._token, self._expires, self._fail_until, self._fail = "", 0.0, 0.0, None
        self.refreshes = 0

    def __repr__(self):
        return "<TokenProvider redacted>"

    def _mint_jwt(self, now: float) -> str:
        head = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        iat = int(now)
        claims = _b64u(json.dumps({"iss": self._sa.client_email, "scope": SCOPE, "aud": TOKEN_URL, "iat": iat, "exp": iat + 3600},
                                  separators=(",", ":")).encode())
        signing_input = ("%s.%s" % (head, claims)).encode()
        return "%s.%s" % (signing_input.decode(), _b64u(self._sa.sign(signing_input)))

    def token(self, timeout=10) -> str:
        with self._lock:
            now = self._clock()
            if self._token and now < self._expires - REFRESH_MARGIN_S:
                return self._token
            if now < self._fail_until and self._fail is not None:
                code, headers = self._fail
                raise VertexError("vertex: token unavailable (recent refresh failed)", code, headers)
            try:
                body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                               "assertion": self._mint_jwt(now)}).encode()
                req = urllib.request.Request(TOKEN_URL, body, {"Content-Type": "application/x-www-form-urlencoded",
                                                               "User-Agent": "Sach-check/0.1"}, method="POST")
                data = _call(self._opener, req, timeout, "token request", auth=True)
                tok = data.get("access_token") if isinstance(data, dict) else None
                if not isinstance(tok, str) or not tok:
                    raise VertexError("vertex: token reply had no access token", 401)
                try:
                    ttl = float(data.get("expires_in") or 3600)
                except (TypeError, ValueError):
                    ttl = 3600.0
            except TimeoutError:
                self._fail_until, self._fail = now + FAILED_REFRESH_S, (None, {})
                raise
            except VertexError as e:
                self._fail_until, self._fail = now + FAILED_REFRESH_S, (e.code, e.headers)
                raise
            except Exception:                                                     # e.g. a signing problem: generic, key never echoed
                self._fail_until, self._fail = now + FAILED_REFRESH_S, (401, {})
                err = True
            else:
                err = False
            if err:
                raise VertexError("vertex: could not build a token request", 401)
            self._token, self._expires, self._fail_until, self._fail = tok, now + max(ttl, 60.0), 0.0, None
            self.refreshes += 1
            return tok


_providers: dict = {}
_providers_lock = threading.Lock()

def shared_provider(sa: ServiceAccount) -> TokenProvider:
    """One token cache per credential for the whole process (build_judges may run more than once)."""
    with _providers_lock:
        p = _providers.get(sa.fingerprint)
        if p is None:
            p = _providers[sa.fingerprint] = TokenProvider(sa)
        return p

def reset_providers() -> None:
    with _providers_lock:
        _providers.clear()


# ---------------------------------------------------------------- generateContent
_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")

class VertexClient:
    def __init__(self, sa: ServiceAccount, tokens: TokenProvider = None, opener=None):
        self._sa = sa
        self._tokens = tokens or shared_provider(sa)
        self._opener = opener or urllib.request.urlopen

    def __repr__(self):
        return "<VertexClient redacted>"

    def url(self, model: str) -> str:
        if not _MODEL_RE.fullmatch(model or ""):
            raise VertexError("vertex: bad model name")
        return "%s/v1/projects/%s/locations/global/publishers/google/models/%s:generateContent" % (
            HOST, urllib.parse.quote(self._sa.project_id, safe=":"), model)

    def access_token(self, timeout: float = 10) -> str:
        """The bearer token, cached or freshly minted. Callers that bill per call fetch it first, so a token failure costs no cap."""
        return self._tokens.token(timeout=min(timeout, 10))

    def generate(self, model: str, body: dict, timeout: float = 15) -> dict:
        """POST a Gemini-shaped body to the global endpoint and return the parsed JSON reply (candidates[0].content.parts[0].text)."""
        tok = self.access_token(timeout)
        req = urllib.request.Request(self.url(model), json.dumps(body).encode(), {
            "Content-Type": "application/json", "Authorization": "Bearer " + tok, "User-Agent": "Sach-check/0.1"}, method="POST")
        out = _call(self._opener, req, timeout, "generateContent")
        if not isinstance(out, dict):
            raise VertexError("vertex: unexpected reply shape")
        return out


# ---------------------------------------------------------------- spend guard
def max_per_day() -> int:
    return limits._env_int("SACH_VERTEX_MAX_PER_DAY", DEFAULT_MAX_PER_DAY)

def _day_key(now: float) -> str:
    return "vx:d:%d" % int(now // 86400)

def seconds_to_utc_midnight(now: float) -> float:
    return 86400 - (now % 86400)

def models() -> list:
    return [m.strip() for m in os.environ.get("SACH_VERTEX_MODELS", DEFAULT_MODELS).split(",") if m.strip()]

def reserve_call(st=None, now=None) -> None:
    """Count one billed call against today's cap. Raises VertexCapReached when the cap is used up (the attempt is given back, a
    'skipped' counter is bumped). Never raises anything else: a broken store only makes the cap per-instance."""
    cap = max_per_day()
    if cap <= 0:
        return
    now = time.time() if now is None else now
    try:
        st = st or store.get_store()
    except Exception:
        st = None
    key = _day_key(now)
    n, _ = limits._incr(st, key, 2 * 86400) if st is not None else (limits._mem_incr(key), False)
    if n > cap:
        try:
            if st is not None and getattr(st, "remote", False):
                st.incr(key, -1)
            else:
                limits._mem_incr(key, -1)
            limits._incr(st, "vx:skipped:%d" % int(now // 86400), 2 * 86400) if st is not None else None
        except Exception:
            pass
        raise VertexCapReached("vertex: daily call cap reached (resumes 00:00 UTC)")

def usage(st=None, now=None) -> dict:
    """For the status page: counts only, never any credential material."""
    now = time.time() if now is None else now
    out = {"calls_today": 0, "max_per_day": max_per_day(), "skipped_over_cap_today": 0}
    try:
        st = st or store.get_store()
        kd, ks = _day_key(now), "vx:skipped:%d" % int(now // 86400)
        c = st.counters([kd, ks]) if getattr(st, "remote", False) else {}
        with limits._mem_lock:
            mem = dict(limits._mem)
        out["calls_today"] = max(int(c.get(kd, 0) or 0), int(mem.get(kd, 0)), 0)
        out["skipped_over_cap_today"] = max(int(c.get(ks, 0) or 0), int(mem.get(ks, 0)), 0)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- Grounding with Google Search (used by sach/search.py)
GROUNDED_DEFAULT_MODEL = "gemini-3.1-flash-lite"
GROUNDED_DEFAULT_MAX_PER_DAY = 160

def grounded_model() -> str:
    m = (os.environ.get("SACH_GROUNDED_MODEL") or "").strip()
    return m if _MODEL_RE.fullmatch(m) else GROUNDED_DEFAULT_MODEL

def grounded_max_per_day() -> int:
    """SACH_GROUNDED_MAX_PER_DAY: 0 = unlimited. Only plain ASCII decimal digits, optionally surrounded by whitespace, are accepted (round 5,
    D3). Anything else ('1_000', '+3', '1e3', '2.5', '-5', '', 'abc') is invalid and gives the default 160 (fail safe)."""
    raw = (os.environ.get("SACH_GROUNDED_MAX_PER_DAY") or "").strip()
    if not re.fullmatch(r"[0-9]+", raw):
        return GROUNDED_DEFAULT_MAX_PER_DAY
    return int(raw)

class GroundedCounterDown(Exception):
    """The shared store that counts grounded prompts did not answer. The attempt is refused; nothing is counted in memory."""

# Memory counter for the grounded cap, used only when no shared store is configured (get_store() then returns a non-remote store).
# Its own dict, keyed by UTC day, holding only today: the shared limits._mem flood rule never touches it (round 4, C1).
_grounded_mem: dict = {}
_grounded_lock = threading.Lock()

def _grounded_mem_day(day: int) -> dict:
    """Caller holds _grounded_lock. Keeps the entry for `day` and drops every other day."""
    for d in [d for d in _grounded_mem if d != day]:
        del _grounded_mem[d]
    return _grounded_mem.setdefault(day, {"calls": 0, "skipped": 0})

def reset_grounded_memory() -> None:
    with _grounded_lock:
        _grounded_mem.clear()

def reserve_grounded(st=None, now=None) -> None:
    """One grounded prompt against SACH_GROUNDED_MAX_PER_DAY (0 = unlimited). Every attempt that reaches this step counts, whatever its
    outcome. With a shared store (remote): one atomic incr on gr:d:<UTC day>; an over-cap attempt is taken back from that same counter; a
    failed incr raises GroundedCounterDown and the attempt is refused (never counted in memory, so no double count). Without a shared store:
    the module's own memory counter. Raises VertexCapReached (cap used up) or GroundedCounterDown."""
    cap = grounded_max_per_day()
    if cap <= 0:
        return
    now = time.time() if now is None else now
    try:
        st = st or store.get_store()
    except Exception:
        st = None
    day = int(now // 86400)
    key, skey = "gr:d:%d" % day, "gr:skipped:%d" % day
    if st is not None and getattr(st, "remote", False):
        try:
            n = st.incr(key, 1)
        except Exception:
            n = 0
        if not (isinstance(n, int) and n > 0):
            raise GroundedCounterDown("grounded search: shared counter unavailable, attempt refused")
        if n == 1:
            try:
                st.expire(key, 2 * 86400)
            except Exception:
                pass
        if n > cap:
            try:
                st.incr(key, -1)                  # take back this over-cap attempt: it is our own increment
            except Exception:
                pass
            try:
                if st.incr(skey, 1) == 1:
                    st.expire(skey, 2 * 86400)
            except Exception:
                pass
            raise VertexCapReached("grounded search: daily call cap reached (resumes 00:00 UTC)")
        return
    with _grounded_lock:
        slot = _grounded_mem_day(day)
        if slot["calls"] + 1 > cap:
            slot["skipped"] += 1
            raise VertexCapReached("grounded search: daily call cap reached (resumes 00:00 UTC)")
        slot["calls"] += 1

def grounded_usage(st=None, now=None) -> dict:
    """For the status page: counts only."""
    now = time.time() if now is None else now
    cap = grounded_max_per_day()
    day = int(now // 86400)
    kd, ks = "gr:d:%d" % day, "gr:skipped:%d" % day
    out = {"calls_today": 0, "max_per_day": cap, "skipped_over_cap_today": 0}
    try:
        st = st or store.get_store()
        if getattr(st, "remote", False):
            c = st.counters([kd, ks])
            out["calls_today"] = max(int(c.get(kd, 0) or 0), 0)
            out["skipped_over_cap_today"] = max(int(c.get(ks, 0) or 0), 0)
        else:
            with _grounded_lock:
                slot = dict(_grounded_mem.get(day, {}))
            out["calls_today"] = int(slot.get("calls", 0))
            out["skipped_over_cap_today"] = int(slot.get("skipped", 0))
    except Exception:
        pass
    return out

def grounded_body(text: str) -> dict:
    return {"contents": [{"role": "user", "parts": [{"text":
            "Find official Indian government sources (pib.gov.in, gov.in, nic.in) that confirm or deny this claim. Claim: " + text}]}],
            "tools": [{"google_search": {}}]}

def grounded_chunks(reply) -> list:
    """-> [(title, uri)] from candidates[0].groundingMetadata.groundingChunks[].web. The model's prose is ignored."""
    out = []
    try:
        for ch in reply["candidates"][0]["groundingMetadata"]["groundingChunks"]:
            w = ch.get("web") if isinstance(ch, dict) else None
            if isinstance(w, dict) and isinstance(w.get("uri"), str):
                out.append((w.get("title") if isinstance(w.get("title"), str) else "", w["uri"]))
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return out

def generate_grounded(client: "VertexClient", model: str, text: str, timeout: float = 12) -> list:
    """One grounded prompt (billed once however many searches the model runs) -> [(title, redirect_uri)]."""
    return grounded_chunks(client.generate(model, grounded_body(text), timeout=timeout))
