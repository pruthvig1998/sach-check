"""Google Fact Check Tools retriever (SECONDARY tier only). Enabled when GOOGLE_FACTCHECK_API_KEY is set.

API: GET https://factchecktools.googleapis.com/v1alpha1/claims:search?query=&languageCode=&pageSize=&key=
Response: {"claims": [{"text", "claimant", "claimDate", "claimReview": [{"publisher": {"name", "site"}, "url", "title",
"reviewDate", "textualRating", "languageCode"}]}]}   (reference: developers.google.com/fact-check/tools/api/reference/rest)

Safety rules, enforced here and tested in tests/test_sources.py:
- every Evidence is tier `factchecker`, even when the review URL is on an official domain: this API is an index of
  fact-checkers, so it can never produce TRUE or FALSE (sach/verdict.py)
- only reviews whose URL is on our verified fact-checker list are kept (sach.fetch.is_factchecker)
- the API key is sent only in the request and never appears in an Evidence, a log line or an exception message
- any failure (network, quota, non-200, bad JSON) returns []
"""
from __future__ import annotations
import json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from .fetch import is_factchecker, host_of, UA
from .models import Evidence, TIER_FACTCHECKER
from .stance import overlap, subject_coverage

ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
TIMEOUT_S = 6
MAX_BYTES = 1_000_000

def _language(text: str) -> str:
    """BCP-47 code for the query text. Only script-based (Telugu, Devanagari); everything else asks for English."""
    te = len(re.findall(r"[ఀ-౿]", text))
    hi = len(re.findall(r"[ऀ-ॿ]", text))
    return "te" if te > 5 and te >= hi else "hi" if hi > 5 else "en"

class FactCheckToolsRetriever:
    def __init__(self, key: str | None = None, opener=None, page_size: int = 8, max_results: int = 3,
                 min_overlap: float = 0.35, min_subject: float = 0.5, timeout: float | None = None):
        self.key = key if key is not None else os.environ.get("GOOGLE_FACTCHECK_API_KEY", "")
        self._open = opener or urllib.request.urlopen
        self.page_size, self.max_results = page_size, max_results
        self.min_overlap, self.min_subject = min_overlap, min_subject
        self.timeout = timeout or TIMEOUT_S

    def _call(self, query: str, language: str):
        params = {"query": query, "languageCode": language, "pageSize": self.page_size, "key": self.key}
        req = urllib.request.Request(ENDPOINT + "?" + urllib.parse.urlencode(params),
                                     headers={"Accept": "application/json", "User-Agent": UA})
        with self._open(req, timeout=self.timeout) as r:
            if getattr(r, "status", 200) != 200:
                return None
            data = json.loads(r.read(MAX_BYTES).decode("utf-8", "replace"))
        return data if isinstance(data, dict) else None

    def search(self, query: str, language: str | None = None) -> list[Evidence]:
        """`query` may be in any language (the pipeline can pass the original-language claim as well as its English
        rendering); `language` overrides the guess from the script. Never raises."""
        try:
            if not self.key or not isinstance(query, str) or not query.strip():
                return []
            data = self._call(query.strip()[:300], language or _language(query))
            if not data:
                return []
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            found, seen = [], set()
            for claim in data.get("claims") or []:
                if not isinstance(claim, dict):
                    continue
                ctext, claimant = str(claim.get("text") or ""), str(claim.get("claimant") or "")
                for rv in claim.get("claimReview") or []:
                    if not isinstance(rv, dict):
                        continue
                    url = str(rv.get("url") or "")
                    if not url.startswith("https://") or url in seen or not is_factchecker(url):
                        continue                                    # off-list publisher: drop
                    title = str(rv.get("title") or "")
                    ctx = f"{ctext} {title}"
                    if overlap(query, ctx) < self.min_overlap or subject_coverage(query, ctx) < self.min_subject:
                        continue                                    # not plausibly the same claim
                    seen.add(url)
                    pub = rv.get("publisher") if isinstance(rv.get("publisher"), dict) else {}
                    parts = [f"Claim reviewed: {ctext}"]
                    if claimant:
                        parts.append(f"Claimant: {claimant}")
                    if rv.get("textualRating"):
                        parts.append(f"Rating: {rv['textualRating']}")
                    if rv.get("reviewDate"):
                        parts.append(f"Reviewed: {str(rv['reviewDate'])[:10]}")
                    found.append((overlap(query, ctx), Evidence(str(pub.get("name") or host_of(url)), url, TIER_FACTCHECKER,
                                                               fetched_at, title, " | ".join(parts))))
            found.sort(key=lambda t: -t[0])
            return [e for _, e in found[: self.max_results]]
        except Exception:
            return []          # deliberately no message: urllib errors can embed the request URL, which carries the key

    def claim_reviews(self, query: str, language: str | None = None) -> list[dict]:
        """Raw, unfiltered reviews for the instant-match layer (sach/match.py), which does its own publisher and similarity checks.
        Each item: reviewed_claim, claimant, publisher, site, url, title, review_date, rating. Never raises; no key = []."""
        try:
            if not self.key or not isinstance(query, str) or not query.strip():
                return []
            data = self._call(query.strip()[:300], language or _language(query))
            out = []
            for claim in (data or {}).get("claims") or []:
                if not isinstance(claim, dict):
                    continue
                for rv in claim.get("claimReview") or []:
                    if not isinstance(rv, dict):
                        continue
                    pub = rv.get("publisher") if isinstance(rv.get("publisher"), dict) else {}
                    out.append({"reviewed_claim": str(claim.get("text") or ""), "claimant": str(claim.get("claimant") or ""),
                                "publisher": str(pub.get("name") or ""), "site": str(pub.get("site") or ""),
                                "url": str(rv.get("url") or ""), "title": str(rv.get("title") or ""),
                                "review_date": str(rv.get("reviewDate") or "")[:10], "rating": str(rv.get("textualRating") or "")})
            return out
        except Exception:
            return []          # no message: urllib errors can embed the request URL, which carries the key
