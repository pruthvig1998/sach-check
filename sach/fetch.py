"""Polite cached fetcher. Every page is stored on disk with its fetch timestamp."""
from __future__ import annotations
import hashlib, json, os, posixpath, time, urllib.request, urllib.error
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

UA = "Sach-check/0.1 (open-source fact-check research; MIT)"
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", "who.int")
OFFICIAL_HOSTS = {"pib.gov.in", "factcheck.pib.gov.in", "icmr.gov.in"}
# Zones where the registry only lets the named kind of body register. Only true subdomains match (never the bare zone).
# .bank.in: RBI circular RBI/2025-26/28 (22 Apr 2025) made it the exclusive domain for banks, IDRBT is the sole registrar.
OFFICIAL_ZONES = ("bank.in",)
# Official bodies whose domains do not end in .gov.in / .nic.in. Matched as the exact host or a true subdomain.
# Every entry, and the evidence for it, is listed in docs/sources.md. Add nothing from memory.
EXTRA_OFFICIAL = ("rbi.org.in", "mygov.in", "npci.org.in", "sansad.in", "nta.ac.in", "irctc.co.in", "epfindia.gov.in",
                  "licindia.in", "sbi.co.in", "onlinesbi.sbi", "aiims.edu", "pfrda.org.in", "aicte-india.org",
                  "rbiretaildirect.org.in", "ugc.ac.in", "jansuraksha.in")

# Fact-checkers are SECONDARY: shown as labelled citations, never able to produce TRUE or FALSE (sach/verdict.py).
# Whole-site entries: the outlet is a fact-checking organisation, every page counts.
FACTCHECKER_HOSTS = ("altnews.in", "boomlive.in", "vishvasnews.com", "factly.in", "factcrescendo.com",
                     "newschecker.in", "youturn.in")
# General news sites with a fact-check section: only URLs under these path prefixes count (segment-aware, see _path_ok).
FACTCHECKER_PATHS = {
    "newsmeter.in": ("/fact-check", "/fact-check-health", "/ai-deepfake"),
    "newsmobile.in": ("/nm-fact-checker",),
    "telugupost.com": ("/factcheck", "/english-factcheck", "/ai-factcheck"),
    "indiatoday.in": ("/fact-check",),
    "thequint.com": ("/news/webqoof",),
    "ptinews.com": ("/factcheck",),
}

def _parts(url: str):
    """(host, normalised path). Empty host for anything a browser could read differently from urlparse."""
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower()
    except ValueError:
        return "", ""
    if not host or "\\" in u.netloc or any(c.isspace() or ord(c) < 32 or c == "%" for c in u.netloc):
        return "", ""                  # e.g. https://evil.com\@rbi.org.in/ : urlparse says rbi.org.in, browsers say evil.com
    path = posixpath.normpath(unquote(u.path)).lower() if u.path else "/"
    return host, path

def host_of(url: str) -> str:
    return _parts(url)[0]

def _under(h: str, d: str) -> bool:
    return h == d or h.endswith("." + d)

def is_official(url: str) -> bool:
    h = host_of(url)
    return bool(h) and (h in OFFICIAL_HOSTS or any(h == s.lstrip(".") or h.endswith("." + s.lstrip(".")) for s in OFFICIAL_SUFFIXES)
            or any(h.endswith("." + z) for z in OFFICIAL_ZONES)
            or any(_under(h, d) for d in EXTRA_OFFICIAL))

def _path_ok(path: str, prefixes) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)

def is_factchecker(url: str) -> bool:
    h, path = _parts(url)
    if not h:
        return False
    if any(_under(h, d) for d in FACTCHECKER_HOSTS):
        return True
    return any(_under(h, d) and _path_ok(path, pre) for d, pre in FACTCHECKER_PATHS.items())

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
