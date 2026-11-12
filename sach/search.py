"""Live web search providers with failover, and an honest per-check status.

Providers (each only if its key is set): Brave Search (BRAVE_API_KEY), then Tavily (TAVILY_API_KEY). Order can be changed
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
import json, os, threading, time as _time, urllib.error, urllib.parse, urllib.request
from .fetch import UA

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
    def from_env(cls, brave_key: str | None = None, tavily_key: str | None = None, order: str | None = None, opener=None):
        keys = {"brave": brave_key or os.environ.get("BRAVE_API_KEY"), "tavily": tavily_key or os.environ.get("TAVILY_API_KEY")}
        make = {"brave": lambda k: BraveSearch(k, opener=opener), "tavily": lambda k: TavilySearch(k, opener=opener)}
        wanted = [n.strip().lower() for n in (order if order is not None else os.environ.get("SACH_SEARCH_ORDER", "brave,tavily")).split(",")]
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
        """URLs from the first provider that answers. [] when none does; `run` (if given) records whether one did."""
        for p in self.providers:
            if self.paused_until(p.name) > self._clock():
                continue                                    # paused: skip without a call
            try:
                urls = p.search(query, count)
            except urllib.error.HTTPError as e:
                if e.code in (401, 402, 403, 432, 433):
                    self._pause(p.name, PAUSE_AUTH_S)       # out of credits / bad key
                elif e.code == 429:
                    self._pause(p.name, retry_after_s(e))
                continue                                    # 5xx, 400 and the rest: next provider, this query only
            except Exception:
                continue                                    # timeout / network / bad JSON: next provider, no pause
            if run is not None:
                run.record(True, p.name)
            return urls
        if run is not None:
            run.record(False, None)
        return []
