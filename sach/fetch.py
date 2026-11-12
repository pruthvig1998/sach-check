"""Polite cached fetcher. Every page is stored on disk with its fetch timestamp."""
from __future__ import annotations
import hashlib, json, os, time, urllib.request, urllib.error
from datetime import datetime, timezone
from urllib.parse import urlparse

UA = "Sach-check/0.1 (open-source fact-check research; MIT)"
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", "who.int")
OFFICIAL_HOSTS = {"pib.gov.in", "factcheck.pib.gov.in", "icmr.gov.in"}
# Official bodies whose domains do not end in .gov.in / .nic.in. Matched as the exact host or a true subdomain.
EXTRA_OFFICIAL = ("rbi.org.in", "mygov.in", "npci.org.in", "sansad.in", "nta.ac.in", "irctc.co.in", "epfindia.gov.in")
FACTCHECKER_HOSTS = ("altnews.in", "boomlive.in", "vishvasnews.com")

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()

def is_official(url: str) -> bool:
    h = host_of(url)
    return (h in OFFICIAL_HOSTS or any(h == s.lstrip(".") or h.endswith(s) for s in OFFICIAL_SUFFIXES)
            or any(h == d or h.endswith("." + d) for d in EXTRA_OFFICIAL))

def is_factchecker(url: str) -> bool:
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in FACTCHECKER_HOSTS)

def _cache_path(url: str) -> str:
    d = os.environ.get("SACH_CACHE_DIR", "cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")

def fetch(url: str, max_age_s: int = 6 * 3600, timeout: int = 25, delay_s: float = 0.5):
    """Return {url,status,fetched_at,body}. Uses disk cache; raises on network error with no cache."""
    p = _cache_path(url)
    if os.path.exists(p):
        rec = json.load(open(p, encoding="utf-8"))
        age = time.time() - datetime.fromisoformat(rec["fetched_at"]).timestamp()
        if age < max_age_s:
            return rec
    time.sleep(delay_s)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        body, status = "", e.code
    rec = {"url": url, "status": status, "body": body,
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump(rec, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return rec
