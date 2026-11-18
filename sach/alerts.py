"""Official disaster and weather alerts in force, from the NDMA SACHET public feed (Common Alerting Protocol, marked "public domain" in the feed).

Why: cyclone, flood, heavy-rain and earthquake rumours are a staple of forwards, and the official alert for a district is the fastest check.
Show-only: when a claim names a hazard and a place that an alert in force also names, the alert is listed with its link. It never sets a
verdict. The feed is read only for claims that mention a hazard, with a short timeout; any failure means no panel.
Switch off with SACH_ALERTS=0."""
from __future__ import annotations
import os, re, time, urllib.request
import xml.etree.ElementTree as ET

FEED = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
TTL_S, TIMEOUT_S = 600, 5
_cache = {"at": 0.0, "items": []}

_HAZARD = re.compile(r"\b(cyclone|storm|thunderstorm|lightning|flood|floods|flooding|heavy rain|rainfall|cloudburst|landslide|earthquake|tsunami|"
                     r"heat ?wave|cold ?wave|hailstorm|red alert|orange alert|yellow alert)\b|चक्रवात|तूफान|बाढ़|भारी बारिश|भूकंप|सुनामी|भूस्खलन|"
                     r"తుఫాను|వరద|భారీ వర్ష|భూకంపం|సునామీ|పిడుగు", re.I)
# Words every alert shares: a match on these says nothing about the place.
_GENERIC = set("imd has issued forecast for light moderate heavy very rain rainfall with thunderstorm lightning which is likely to occur at a few "
               "places over in next hours issued public interest by and the of alert warning red orange yellow cyclone storm flood floods today "
               "tomorrow district districts state india government isolated many most gusty winds wind speed kmph during from till valid "
               "that this will have been says said people area areas near news message forward share please".split())


def enabled() -> bool:
    return os.environ.get("SACH_ALERTS", "1") != "0"


def mentions_hazard(text: str) -> bool:
    return bool(_HAZARD.search(text or ""))


def _words(t: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in _GENERIC}


def parse(xml_text: str) -> list:
    """[{title, url, published}] from the feed. Only links on the SACHET host are kept."""
    out = []
    try:
        for it in ET.fromstring(xml_text).iter("item"):
            title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
            if title and link.startswith("https://sachet.ndma.gov.in/"):
                out.append({"title": " ".join(title.split())[:400], "url": link, "published": (it.findtext("pubDate") or "").strip()})
    except ET.ParseError:
        return []
    return out


def _items() -> list:
    if os.environ.get("SACH_ALERTS_NO_NETWORK") == "1":   # tests
        return []
    if time.time() - _cache["at"] < TTL_S:
        return _cache["items"]
    try:
        req = urllib.request.Request(FEED, headers={"User-Agent": "Sach-check/0.1 (open-source fact-check research; MIT)"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            items = parse(r.read(2_000_000).decode("utf-8", "replace"))
    except Exception:
        items = _cache["items"]                           # keep the last good copy; a failed read is retried after the TTL
    _cache.update(at=time.time(), items=items)
    return items


def related(text: str, n: int = 3, items: list | None = None) -> list:
    """Alerts in force that name a place the text also names. Empty unless the text mentions a hazard."""
    if not enabled() or not mentions_hazard(text):
        return []
    mine = _words(text)
    if not mine:
        return []
    # a place name is a capitalised word in the alert ("Kamrup", "Chennai"); common words never count, so two texts about "schools" do not match
    places = lambda title: {w.lower() for w in re.findall(r"\b[A-Z][a-z]{3,}", title)} - _GENERIC
    hits = [(len(mine & places(a["title"])), a) for a in (items if items is not None else _items())]
    hits = [h for h in hits if h[0] >= 1]
    hits.sort(key=lambda h: -h[0])
    return [a for _, a in hits[:n]]
