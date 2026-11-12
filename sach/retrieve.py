"""Evidence retrieval. Priority: PIB -> official domains -> fact-checkers.
Every returned Evidence comes from a page that was actually fetched (has fetched_at)."""
from __future__ import annotations
import json, os, re, urllib.parse
from bs4 import BeautifulSoup
from .fetch import fetch, is_official, is_factchecker, UA
from .models import Evidence, TIER_PIB, TIER_OFFICIAL, TIER_FACTCHECKER
from .pib import get_release, rss_index, DEBUNK_MARKERS
from .stance import overlap

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
        scored = sorted(((overlap(claim, t), p) for p, t in self._candidates().items()), reverse=True)
        out = []
        for ov, prid in scored[: self.top_n]:
            if ov < self.min_overlap:
                break
            try:
                rel = get_release(prid)
            except Exception:
                rel = None
            if not rel:
                continue
            debunk = bool(DEBUNK_MARKERS.search(rel["title"]))
            out.append(Evidence("PIB (Press Information Bureau)", rel["url"],
                                TIER_PIB if debunk else TIER_OFFICIAL, rel["fetched_at"], rel["title"], rel["body"]))
        return out

def _page_text(html: str):
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style", "nav", "footer"]):
        t.decompose()
    title = s.title.get_text(" ", strip=True) if s.title else ""
    return title, re.sub(r"\s+", " ", s.get_text(" ", strip=True))[:20000]

class BraveRetriever:
    """Optional live web search (needs BRAVE_API_KEY). Official domains first, then fact-checkers."""
    OFFICIAL_Q = "(site:gov.in OR site:nic.in OR site:who.int)"
    FC_Q = "(site:altnews.in OR site:boomlive.in OR site:vishvasnews.com)"

    def __init__(self, key=None, per_query=3):
        self.key = key or os.environ.get("BRAVE_API_KEY")
        self.per_query = per_query

    def _search(self, q):
        import urllib.request
        url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "count": 8})
        req = urllib.request.Request(url, headers={"X-Subscription-Token": self.key, "Accept": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return [x["url"] for x in json.load(r).get("web", {}).get("results", [])]

    def search(self, claim: str) -> list[Evidence]:
        if not self.key:
            return []
        out = []
        for q, check, tier in ((f"{claim} {self.OFFICIAL_Q}", is_official, TIER_OFFICIAL),
                               (f"{claim} {self.FC_Q}", is_factchecker, TIER_FACTCHECKER)):
            try:
                urls = [u for u in self._search(q) if check(u)][: self.per_query]
            except Exception:
                continue
            for u in urls:
                try:
                    rec = fetch(u)
                except Exception:
                    continue  # unreachable / blocked page: skip, never crash a check
                if rec["status"] != 200:
                    continue
                title, text = _page_text(rec["body"])
                host = urllib.parse.urlparse(u).hostname
                out.append(Evidence(host, u, tier, rec["fetched_at"], title, text))
        return out

def default_retrievers():
    r = [PibRetriever()]
    if os.environ.get("BRAVE_API_KEY"):
        r.append(BraveRetriever())
    return r
