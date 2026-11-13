"""Live web search providers with failover, and an honest per-check status.

Providers (each only if its key is set): Grounded (Gemini on Vertex with Google Search, needs GOOGLE_SA_JSON; first when set), Brave Search
(BRAVE_API_KEY), then Tavily (TAVILY_API_KEY). Grounded is a "fallback" provider: when it finds no official URL the chain asks the next. Order can be changed
with SACH_SEARCH_ORDER=tavily,brave (listed providers first, in that order; configured providers not listed follow).

Failover rules (same idea as sach/llm.py, but per provider):
- HTTP 402 (out of credits), 401/403 (bad key), and Tavily's 432/433 (plan / pay-as-you-go limit exceeded) pause that
  provider for 6 hours. A paused provider is skipped without a call.
- HTTP 429 pauses that provider for its Retry-After seconds (default 60, clamped to 5..600).
- Timeouts, 5xx, 400 and network errors try the next provider for THIS query only; no long pause.
- Nothing is ever raised to the caller and no key ever appears in a message: errors are classified, never printed.

Status of one check (a SearchRun, one per retriever call so parallel claims never share it):
  ok       some provider answered every query (an answer with zero results still counts as an answer)
  partial  some queries got an answer, others got none
  down     no provider answered any query (credits gone, outage, every provider paused)
  off      no provider has a key: a deliberate configuration, not a failure
"""
from __future__ import annotations
import ipaddress, json, os, re, threading, time as _time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from .fetch import UA, is_official, is_factchecker, FACTCHECKER_PATHS
from . import vertex

PAUSE_AUTH_S = 6 * 3600            # out of credits / bad key: do not retry for 6 hours
OK, PARTIAL, DOWN, OFF = "ok", "partial", "down", "off"

# ---------------------------------------------------------------- helpers
def retry_after_s(err) -> float:
    """Seconds the provider asked us to wait (Retry-After, any header case), clamped to 5..600; a minute if absent."""
    try:
        h = getattr(err, "headers", None) or {}
        items = h.items() if hasattr(h, "items") else []
        v = float(next((val for k, val in items if str(k).lower() == "retry-after"), 0) or 0)
    except (TypeError, ValueError):
        v = 0
    return min(max(v, 5.0), 600.0) if v else 60.0

def combine_status(statuses) -> str:
    """Overall status of a whole check from its claims' statuses (None = unknown, ignored)."""
    vals = [s for s in statuses if s]
    bad = [s for s in vals if s in (DOWN, PARTIAL)]
    if not bad:
        return OK if OK in vals else OFF
    return DOWN if all(s == DOWN for s in vals) else PARTIAL

# ---------------------------------------------------------------- Brave
BRAVE_MIN_INTERVAL_S = 1.1     # Brave free plan: ~1 request/second, shared by all concurrent claims
_brave_lock = threading.Lock()
_brave_last = [0.0]

def _brave_throttle():
    with _brave_lock:
        wait = BRAVE_MIN_INTERVAL_S - (_time.monotonic() - _brave_last[0])
        if wait > 0:
            _time.sleep(wait)
        _brave_last[0] = _time.monotonic()

class BraveSearch:
    name = "brave"
    def __init__(self, key: str, opener=None, timeout: float = 20):
        self.key, self._opener, self.timeout = key, opener, timeout

    def search(self, query: str, count: int = 8) -> list[str]:
        url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": count})
        req = urllib.request.Request(url, headers={"X-Subscription-Token": self.key, "Accept": "application/json", "User-Agent": UA})
        for attempt in (0, 1):
            _brave_throttle()
            try:
                with (self._opener or urllib.request.urlopen)(req, timeout=self.timeout) as r:
                    return [x["url"] for x in json.load(r).get("web", {}).get("results", [])]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    _time.sleep(1.5); continue        # rate limited: back off once, then let the chain pause us
                raise

# ---------------------------------------------------------------- Tavily
TAVILY_ENDPOINT = "https://api.tavily.com/search"
# Zones (not single sites): Tavily's docs show include_domains with plain domains, paths and a "*.com" wildcard, but do
# not say whether "gov.in" matches its subdomains, so these are never sent as a hard filter (see TavilySearch._split).
_ZONES = {"gov.in", "nic.in"}

class TavilySearch:
    """POST https://api.tavily.com/search, header `Authorization: Bearer <key>`, JSON body
    {"query", "max_results" (0-20), "search_depth": "basic" (1 credit), "include_domains": [...],
     "include_domains_mode": "restrict"|"prefer"}; response {"results": [{"title", "url", "content", "score"}, ...]}.
    Docs: https://docs.tavily.com/documentation/api-reference/endpoint/search (endpoint, auth, body, response, error
    codes 401/429/432/433), https://docs.tavily.com/documentation/best-practices/best-practices-search (include_domains)."""
    name = "tavily"
    def __init__(self, key: str, opener=None, timeout: float = 12):
        self.key, self._opener, self.timeout = key, opener, timeout

    @staticmethod
    def _split(query: str):
        """Brave-style `site:a OR site:b` -> (plain query text, exact domains, partial?). `partial` is True when a zone
        such as gov.in was dropped from the filter; the caller then asks Tavily to only prefer the listed domains."""
        import re
        sites = re.findall(r"\bsite:([A-Za-z0-9.\-]+)", query)
        text = re.sub(r"\bsite:[A-Za-z0-9.\-]+|[()]", " ", query)
        text = re.sub(r"\s+", " ", re.sub(r"\bOR\b", " ", text)).strip()
        domains = [d.lower() for d in dict.fromkeys(sites) if d.lower() not in _ZONES]
        return text, domains, len(domains) < len(set(sites))

    def search(self, query: str, count: int = 8) -> list[str]:
        text, domains, partial = self._split(query)
        body = {"query": text or query, "max_results": max(1, min(int(count), 20)), "search_depth": "basic"}
        if domains:
            body["include_domains"] = domains
            if partial:
                body["include_domains_mode"] = "prefer"
        req = urllib.request.Request(TAVILY_ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json",
                                              "Accept": "application/json", "User-Agent": UA})
        with (self._opener or urllib.request.urlopen)(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        urls = [x["url"] for x in (data.get("results") or []) if isinstance(x, dict) and isinstance(x.get("url"), str)]
        if domains and not partial:          # hard filter requested: double-check, never trust the provider to have applied it
            urls = [u for u in urls if any((urllib.parse.urlparse(u).hostname or "").lower() == d
                                           or (urllib.parse.urlparse(u).hostname or "").lower().endswith("." + d) for d in domains)]
        return urls

# ---------------------------------------------------------------- Grounded (Gemini on Vertex + Google Search)
REDIRECT_HOST = "vertexaisearch.cloud.google.com"
_REDIRECT_PREFIX = "/grounding-api-redirect/"
_REDIRECT_CODES = (301, 302, 303, 307, 308)
MAX_REDIRECTS_RESOLVED = 12
RESOLVE_WORKERS = 6
RESOLVE_TIMEOUT_S = 3.0
GROUNDED_CACHE_S = 300
_BAD_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".test", ".invalid", ".example")

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None                         # never follow: the Location header is read from the 3xx itself

def _no_follow_open(req, timeout=None):
    return urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout)

class SearchPaused(Exception):
    """Raised by a provider that must be benched for `pause_s` seconds (e.g. its daily cap is used up)."""
    def __init__(self, msg, pause_s):
        super().__init__(msg)
        self.pause_s = pause_s

def public_https_url(url) -> str:
    """The URL if it is https, has no userinfo and a public hostname (no IP literal that is not global, no single-label or
    internal-looking name); else ''."""
    url = (url or "").strip()
    try:
        u = urllib.parse.urlparse(url)
        host = (u.hostname or "").lower().rstrip(".")
        port = u.port                                       # ValueError if malformed
    except ValueError:
        return ""
    if port not in (None, 443):                             # only the default https port: a Location on :8443 etc. is dropped
        return ""
    if u.scheme != "https" or not host or "@" in u.netloc or "\\" in url or any(c.isspace() or ord(c) < 32 for c in url):
        return ""
    try:
        return url if ipaddress.ip_address(host).is_global else ""
    except ValueError:
        pass
    if "." not in host or host.endswith(_BAD_SUFFIXES) or not re.fullmatch(r"[a-z0-9.\-]+", host):
        return ""
    return url

def resolve_redirect(uri: str, opener=None, timeout: float = RESOLVE_TIMEOUT_S) -> str:
    """One Google grounding redirect -> the real page URL, or '' on any failure. Only https://vertexaisearch.cloud.google.com/grounding-api-redirect/...
    is ever requested; redirects are not followed; the Location must be a public https URL."""
    try:
        u = urllib.parse.urlparse(uri)
        if u.scheme != "https" or (u.hostname or "").lower() != REDIRECT_HOST or u.username or u.port not in (None, 443) \
                or not u.path.startswith(_REDIRECT_PREFIX):
            return ""
        req = urllib.request.Request(uri, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            r = (opener or _no_follow_open)(req, timeout=timeout)
        except urllib.error.HTTPError as e:         # the normal case: a 302 raised because redirects are not followed
            if e.code not in _REDIRECT_CODES:
                return ""
            loc = e.headers.get("Location") if e.headers is not None else None
            try:
                e.close()
            except Exception:
                pass
        else:
            try:
                code = getattr(r, "status", None) or r.getcode()
                loc = r.headers.get("Location") if code in _REDIRECT_CODES else None
            finally:
                try:
                    r.close()
                except Exception:
                    pass
        if not isinstance(loc, str) or not loc.strip():
            return ""
        return public_https_url(urllib.parse.urljoin(uri, loc.strip()))
    except Exception:
        return ""

def _trusted(url: str) -> bool:
    return is_official(url) or is_factchecker(url)

class GroundedSearch:
    """Gemini on Vertex AI with Grounding with Google Search, used ONLY to find candidate pages. One grounded prompt per distinct
    search text (cached 5 minutes); the model's prose is ignored; each groundingChunks[].web.uri is a Google redirect that is
    resolved safely, and only URLs the host trust list accepts as official or fact-checker are returned. Same result shape as
    TavilySearch (a list of URL strings). `fallthrough_empty`: no URL means the chain asks the next provider."""
    name = "grounded"
    auth_pause_s = vertex.AUTH_PAUSE_S
    fallthrough_empty = True

    def __init__(self, client, model: str | None = None, opener=None, timeout: float = 12, st=None, clock=_time.time):
        self.client, self.model, self._opener, self.timeout, self._st, self._clock = client, model, opener, timeout, st, clock
        self._cache, self._lock = {}, threading.Lock()

    def __repr__(self):
        return "<GroundedSearch redacted>"

    @staticmethod
    def _skip_title(title: str) -> bool:
        """Chunk titles are bare domains: skip resolving one that cannot be trusted whatever its path."""
        t = (title or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}", t):
            return False
        u = "https://" + t + "/"
        return not (is_official(u) or is_factchecker(u) or any(t == d or t.endswith("." + d) for d in FACTCHECKER_PATHS))

    def search(self, query: str, count: int = 8) -> list[str]:
        text = TavilySearch._split(query)[0] or query
        now = self._clock()
        with self._lock:
            hit = self._cache.get(text)
            if hit and now - hit[0] < GROUNDED_CACHE_S:
                return list(hit[1])
        self.client.access_token(timeout=self.timeout)       # token first: a token failure must not use up the daily cap
        try:
            vertex.reserve_grounded(self._st, now)
        except vertex.VertexCapReached:
            raise SearchPaused("grounded: daily cap reached", vertex.seconds_to_utc_midnight(now)) from None
        try:
            chunks = vertex.generate_grounded(self.client, self.model or vertex.grounded_model(), text, timeout=self.timeout)
        except Exception as e:
            if vertex.not_billed(e):                          # never served by Google (timeout, network, 401/403, 5xx): give the slot back
                vertex.release_grounded(self._st, now)
            raise
        uris = list(dict.fromkeys(u for t, u in chunks if not self._skip_title(t)))[:MAX_REDIRECTS_RESOLVED]
        if uris:
            with ThreadPoolExecutor(max_workers=min(RESOLVE_WORKERS, len(uris))) as ex:
                real = list(ex.map(lambda x: resolve_redirect(x, self._opener), uris))
        else:
            real = []
        urls = list(dict.fromkeys(u for u in real if u and _trusted(u)))[:max(1, int(count))]
        with self._lock:
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[text] = (now, list(urls))
        return urls

# ---------------------------------------------------------------- chain + status
class SearchRun:
    """Outcome of one retriever call (one claim): thread-safe, never shared between claims."""
    def __init__(self, configured: bool = True):
        self._lock = threading.Lock()
        self.configured, self.total, self.answered, self.providers = configured, 0, 0, []

    def record(self, answered: bool, provider: str | None):
        with self._lock:
            self.total += 1
            if answered:
                self.answered += 1
                if provider and provider not in self.providers:
                    self.providers.append(provider)

    @property
    def status(self) -> str:
        if not self.configured:
            return OFF
        if self.total == 0 or self.answered == self.total:
            return OK
        return DOWN if self.answered == 0 else PARTIAL

    @property
    def provider(self) -> str:
        return ",".join(self.providers)

class SearchChain:
    def __init__(self, providers, clock=_time.time):
        self.providers, self._clock = list(providers), clock
        self._paused, self._lock = {}, threading.Lock()

    @classmethod
    def from_env(cls, brave_key: str | None = None, tavily_key: str | None = None, order: str | None = None, opener=None, grounded=None):
        """`grounded`: a ready GroundedSearch (tests); otherwise one is built when GOOGLE_SA_JSON is set and usable."""
        if grounded is None:
            try:
                sa = vertex.ServiceAccount.from_env()
                grounded = GroundedSearch(vertex.VertexClient(sa)) if sa else None
            except ValueError:
                grounded = None                                   # unusable credential: off, never an error here
        keys = {"grounded": grounded, "brave": brave_key or os.environ.get("BRAVE_API_KEY"), "tavily": tavily_key or os.environ.get("TAVILY_API_KEY")}
        make = {"grounded": lambda g: g, "brave": lambda k: BraveSearch(k, opener=opener), "tavily": lambda k: TavilySearch(k, opener=opener)}
        wanted = [n.strip().lower() for n in (order if order is not None else os.environ.get("SACH_SEARCH_ORDER", "grounded,brave,tavily")).split(",")]
        names = [n for n in dict.fromkeys(wanted) if n in make] + [n for n in make if n not in wanted]
        return cls([make[n](keys[n]) for n in names if keys[n]])

    @property
    def configured(self) -> bool:
        return bool(self.providers)

    def new_run(self) -> SearchRun:
        return SearchRun(configured=self.configured)

    def paused_until(self, name: str) -> float:
        with self._lock:
            return self._paused.get(name, 0.0)

    def _pause(self, name: str, secs: float):
        with self._lock:
            self._paused[name] = max(self._paused.get(name, 0.0), self._clock() + secs)

    def search(self, query: str, count: int = 8, run: SearchRun | None = None) -> list[str]:
        """URLs from the first provider that answers. [] when none does; `run` (if given) records whether one did. A provider with
        `fallthrough_empty` that answers with no URL hands over to the next one (its empty answer counts only if no other answers)."""
        empty_from, others_failed = None, False
        for p in self.providers:
            if self.paused_until(p.name) > self._clock():
                others_failed = True                        # skipped: it did not answer this query
                continue                                    # paused: skip without a call
            try:
                urls = p.search(query, count)
            except Exception as e:
                others_failed = True
                pause = getattr(e, "pause_s", None)
                code = getattr(e, "code", None)              # HTTPError and vertex.VertexError both carry the HTTP status
                if pause:
                    self._pause(p.name, float(pause))        # e.g. daily cap: until 00:00 UTC
                elif code in (401, 402, 403, 432, 433):
                    self._pause(p.name, getattr(p, "auth_pause_s", PAUSE_AUTH_S))   # out of credits / bad key
                elif code == 429:
                    self._pause(p.name, retry_after_s(e))
                continue                                    # 5xx, 400, timeout, network, bad JSON: next provider, this query only
            if not urls and getattr(p, "fallthrough_empty", False):
                empty_from = empty_from or p.name
                continue
            if run is not None:
                run.record(True, p.name)
            return urls
        if empty_from is not None and not others_failed:
            if run is not None:
                run.record(True, empty_from)                 # the empty grounded answer stands only when nothing else failed
            return []
        if run is not None:
            run.record(False, None)
        return []
