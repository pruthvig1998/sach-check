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
from .search import (SearchChain, SearchRun, BRAVE_MIN_INTERVAL_S, _brave_last, _brave_throttle, grounded_credential_usable)   # noqa: F401 (re-exported: older tests patch them here)

class BraveRetriever:
    """Optional live web search (needs BRAVE_API_KEY and/or TAVILY_API_KEY; see sach/search.py for failover). Official
    domains first, then fact-checkers.

    Search status: `search_with_status(claim)` returns (evidence, SearchRun). The SearchRun is created per call and
    reached by `_search` through a thread-local (`_tls`), so claims running in parallel threads on one shared retriever
    never see each other's status. `search(claim)` keeps the plain list interface. The pipeline prefers
    `search_with_status`. A fake that overrides `_search` simply records nothing (status ok)."""
    OFFICIAL_Q = ("(site:gov.in OR site:nic.in OR site:who.int OR site:rbi.org.in OR site:mygov.in OR site:sansad.in "
                  "OR site:bank.in OR site:licindia.in)")
    # whole-site fact-checkers plus newsmeter (its fact-check section); path-limited outlets are filtered after the search by is_factchecker
    FC_Q = "(" + " OR ".join(f"site:{d}" for d in (*FACTCHECKER_HOSTS, "newsmeter.in")) + ")"

    def __init__(self, key=None, per_query=3, chain=None):
        self.key = key or os.environ.get("BRAVE_API_KEY")
        self.chain = chain or SearchChain.from_env(brave_key=self.key)
        self.per_query = per_query
        self._tls = threading.local()

    def _search(self, q, count=8):
        return self.chain.search(q, count, run=getattr(self._tls, "run", None))

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
        return self.search_with_status(claim)[0]

    def search_with_status(self, claim: str):
        """-> (evidence, SearchRun). PIB first, then the wider official pool (gov.in, nic.in, WHO, RBI, MyGov, Parliament);
        fact-checkers only if nothing authoritative was found (they can never decide a verdict, so skip the extra query)."""
        run = self.chain.new_run()
        if not self.chain.configured:
            return [], run                                   # status off: no search key is a deliberate configuration
        self._tls.run = run
        try:
            return self._search_claim(claim), run
        finally:
            self._tls.run = None

    def _search_claim(self, claim: str) -> list[Evidence]:
        short, kw = self._short(claim), self._keywords(claim)
        is_pib = lambda u: (urllib.parse.urlparse(u).hostname or "").endswith("pib.gov.in")
        out, seen = [], set()

        def add(urls, tier):
            todo = []
            for u in urls:
                k = canonical_key(u)
                if k in seen:
                    continue
                seen.add(k)
                todo.append(u)
            if not todo:
                return
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(4, len(todo))) as ex:   # pages fetched in parallel; results kept in search order
                for e in ex.map(lambda u: self._evidence(u, tier), todo):
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
    if os.environ.get("BRAVE_API_KEY") or os.environ.get("TAVILY_API_KEY") or grounded_credential_usable():   # an unparseable GOOGLE_SA_JSON is off (D4)
        r.append(BraveRetriever())              # web search: Grounded (Vertex), Brave, then Tavily (sach/search.py)
    if os.environ.get("GOOGLE_FACTCHECK_API_KEY"):
        from .factcheck_api import FactCheckToolsRetriever
        r.append(FactCheckToolsRetriever())     # secondary tier only; one HTTPS call, 6 s cap
    return r
