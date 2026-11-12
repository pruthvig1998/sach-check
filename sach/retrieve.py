"""Evidence retrieval. Priority: PIB -> official domains -> fact-checkers.
Every returned Evidence comes from a page that was actually fetched (has fetched_at)."""
from __future__ import annotations
import json, os, re, urllib.error, urllib.parse
from bs4 import BeautifulSoup
from .fetch import fetch, is_official, is_factchecker, FACTCHECKER_HOSTS, UA
from .models import Evidence, TIER_PIB, TIER_OFFICIAL, TIER_FACTCHECKER
from .pib import get_release, parse_release, rss_index, DEBUNK_MARKERS
from . import index as pib_index
from .stance import overlap, distinctive, tokens, _GENERIC

def _pib_evidence(rel: dict) -> Evidence:
    debunk = bool(DEBUNK_MARKERS.search(rel["title"]))
    return Evidence("PIB (Press Information Bureau)", rel["url"], TIER_PIB if debunk else TIER_OFFICIAL,
                    rel["fetched_at"], rel["title"], rel["body"])

def canonical_key(url: str) -> str:
    """Same PIB release can appear under many URLs (www., &reg=3&lang=1, Iframe pages): key them by PRID."""
    m = re.search(r"PRID=(\d+)", url, re.I)
    if m and urllib.parse.urlparse(url).hostname and urllib.parse.urlparse(url).hostname.endswith("pib.gov.in"):
        return "pib:" + m.group(1)
    return url.split("#")[0].rstrip("/").lower()

class PibRetriever:
    """Looks for a PIB press release matching the claim: hand-seeded debunks + live RSS index."""
    def __init__(self, seed_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seed_debunks.json"), use_rss=True, top_n=3, min_overlap=0.3):
        self.seed_path, self.use_rss, self.top_n, self.min_overlap = seed_path, use_rss, top_n, min_overlap

    def _candidates(self):
        c = {}
        if os.path.exists(self.seed_path):
            for it in json.load(open(self.seed_path, encoding="utf-8")):
                c[str(it["prid"])] = it.get("title", "")
        if self.use_rss:
            try:
                for it in rss_index():
                    c.setdefault(it["prid"], it["title"])
            except Exception:
                pass
        return c

    def search(self, claim: str) -> list[Evidence]:
        scored = {}
        for p, t in self._candidates().items():            # hand-seeded debunks + live RSS, matched on titles
            ov = overlap(claim, t)
            if ov >= self.min_overlap:
                scored[p] = ov
        for h in pib_index.search(claim, top_n=self.top_n + 2):   # local index of harvested PIB releases (title + excerpt)
            scored[str(h["prid"])] = max(scored.get(str(h["prid"]), 0), h["score"])
        out = []
        for prid, _ in sorted(scored.items(), key=lambda kv: -kv[1])[: self.top_n + 1]:
            try:
                rel = get_release(prid)
            except Exception:
                rel = None
            if not rel:
                continue
            out.append(_pib_evidence(rel))
        return out

def _page_text(html: str):
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style", "nav", "footer"]):
        t.decompose()
    title = s.title.get_text(" ", strip=True) if s.title else ""
    return title, re.sub(r"\s+", " ", s.get_text(" ", strip=True))[:20000]

import threading, time as _time
_brave_lock = threading.Lock()
_brave_last = [0.0]
BRAVE_MIN_INTERVAL_S = 1.1     # Brave free plan: ~1 request/second, shared by all concurrent claims

def _brave_throttle():
    with _brave_lock:
        wait = BRAVE_MIN_INTERVAL_S - (_time.monotonic() - _brave_last[0])
        if wait > 0:
            _time.sleep(wait)
        _brave_last[0] = _time.monotonic()

class BraveRetriever:
    """Optional live web search (needs BRAVE_API_KEY). Official domains first, then fact-checkers."""
    OFFICIAL_Q = ("(site:gov.in OR site:nic.in OR site:who.int OR site:rbi.org.in OR site:mygov.in OR site:sansad.in "
                  "OR site:bank.in OR site:licindia.in)")
    # whole-site fact-checkers plus newsmeter (its fact-check section); path-limited outlets are filtered after the search by is_factchecker
    FC_Q = "(" + " OR ".join(f"site:{d}" for d in (*FACTCHECKER_HOSTS, "newsmeter.in")) + ")"

    def __init__(self, key=None, per_query=3):
        self.key = key or os.environ.get("BRAVE_API_KEY")
        self.per_query = per_query

    def _search(self, q, count=8):
        import urllib.request
        url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "count": count})
        req = urllib.request.Request(url, headers={"X-Subscription-Token": self.key, "Accept": "application/json", "User-Agent": UA})
        for attempt in (0, 1):
            _brave_throttle()
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return [x["url"] for x in json.load(r).get("web", {}).get("results", [])]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    _time.sleep(1.5); continue        # rate limited: back off once
                raise

    @staticmethod
    def _short(claim: str, n: int = 14) -> str:
        return " ".join(claim.split()[:n])

    @staticmethod
    def _keywords(claim: str, n: int = 8) -> str:
        """Query-friendly keywords: the claim's distinctive words (original spelling, in order) plus its numbers."""
        d, seen, out = distinctive(claim), set(), []
        for w in re.findall(r"[A-Za-z][A-Za-z\-]+|\d[\d,\.]*", claim):
            key = w.lower()
            if key in seen:
                continue
            if w[0].isdigit() or tokens(w) & d:
                seen.add(key); out.append(w)
        return " ".join(out[:n]) or BraveRetriever._short(claim)

    def _evidence(self, url: str, tier: str):
        try:
            rec = fetch(url)
        except Exception:
            return None                       # unreachable / blocked page: skip, never crash a check
        if rec["status"] != 200:
            return None
        host = urllib.parse.urlparse(url).hostname or ""
        if host.endswith("pib.gov.in") and re.search(r"PRID=\d+", url, re.I):
            rel = parse_release(rec["body"])  # proper PIB parsing: real title/body, and debunk tiering
            if rel["title"] or rel["body"]:
                return _pib_evidence({**rel, "url": url, "fetched_at": rec["fetched_at"]})
        title, text = _page_text(rec["body"])
        return Evidence(host, url, tier, rec["fetched_at"], title, text)

    def _urls(self, q: str, check, limit: int, count: int = 10):
        try:
            return [u for u in self._search(q, count=count) if check(u)][:limit]
        except Exception:
            return []

    def search(self, claim: str) -> list[Evidence]:
        """PIB first, then the wider official pool (gov.in, nic.in, WHO, RBI, MyGov, Parliament); fact-checkers only if
        nothing authoritative was found (they can never decide a verdict, so skip the extra query otherwise)."""
        if not self.key:
            return []
        short, kw = self._short(claim), self._keywords(claim)
        is_pib = lambda u: (urllib.parse.urlparse(u).hostname or "").endswith("pib.gov.in")
        out, seen = [], set()

        def add(urls, tier):
            for u in urls:
                k = canonical_key(u)
                if k in seen:
                    continue
                seen.add(k)
                e = self._evidence(u, tier)
                if e:
                    out.append(e)

        pib_urls = self._urls(f"site:pib.gov.in {short}", is_pib, self.per_query + 1)
        if not pib_urls and kw != short:
            pib_urls = self._urls(f"site:pib.gov.in {kw}", is_pib, self.per_query)      # second PIB try, keyword form
        add(pib_urls, TIER_OFFICIAL)
        add([u for u in self._urls(f"{kw} {self.OFFICIAL_Q}", is_official, self.per_query + 2) if not is_pib(u)][: self.per_query], TIER_OFFICIAL)
        if not any(e.tier in (TIER_PIB, TIER_OFFICIAL) for e in out):
            add(self._urls(f"{short} {self.FC_Q}", is_factchecker, self.per_query), TIER_FACTCHECKER)
        return out

def default_retrievers():
    r = [PibRetriever()]
    if os.environ.get("BRAVE_API_KEY"):
        r.append(BraveRetriever())
    if os.environ.get("GOOGLE_FACTCHECK_API_KEY"):
        from .factcheck_api import FactCheckToolsRetriever
        r.append(FactCheckToolsRetriever())     # secondary tier only; one HTTPS call, 6 s cap
    return r
