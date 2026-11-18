"""Recent official disaster and weather alerts, from the NDMA SACHET public feed (Common Alerting Protocol, marked "public domain" in the feed).

Why: cyclone, flood, heavy-rain and earthquake rumours are a staple of forwards, and the official alert for a district is the fastest check.
Show-only: when a claim names a hazard and a place, and an alert issued in the last 24 hours is about the same kind of hazard in that place,
the alert is listed with its issue time and link. It never sets a verdict. The feed is read only for claims that mention a hazard, with a
short timeout; any failure means no panel (never an old copy).
Switch off with SACH_ALERTS=0."""
from __future__ import annotations
import os, re, time, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

FEED = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
TTL_S, TIMEOUT_S, RECENT_H = 600, 5, 24
_cache = {"at": 0.0, "items": []}

# Hazard families: an alert is only related to a claim about the same kind of hazard.
_FAMILY = {"rain": r"rain|thunderstorm|lightning|hail|cloudburst|shower", "storm": r"cyclone|storm|squall|gale", "flood": r"flood|inundat",
           "quake": r"earthquake|tremor", "tsunami": r"tsunami", "heat": r"heat ?wave", "cold": r"cold ?wave|fog|frost", "slide": r"landslide"}
# Capitalised words in an area phrase that are not places.
_NOT_PLACE = set("north south east west central coastal interior upper lower parts districts district region regions state isolated places "
                 "many most light moderate heavy very thunderstorm lightning rain rainfall metropolitan".split())


def enabled() -> bool:
    return os.environ.get("SACH_ALERTS", "1") != "0"


def _families(t: str) -> set:
    return {k for k, pat in _FAMILY.items() if re.search(pat, t or "", re.I)}


def mentions_hazard(text: str) -> bool:
    return bool(_families(text))


def _area(title: str) -> set:
    """Place words of an alert: the capitalised words of its area phrase ("... over Kamrup and Kamrup Metropolitan in next 3 hours").
    Alerts written any other way give no place, so they are never matched. The issuing office ("IMD Guwahati") is not part of the area."""
    m = re.search(r" over (.+?)(?: in (?:the )?next| during| till| from |\.|$)", title or "")
    return {w.lower() for w in re.findall(r"\b[A-Z][a-z]{3,}", m.group(1))} - _NOT_PLACE if m else set()


def _recent(published: str, now: float) -> bool:
    try:
        return 0 <= now - parsedate_to_datetime(published).timestamp() <= RECENT_H * 3600
    except Exception:
        return False


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
        items = []                                        # no stale copy: an old alert shown as current would mislead
    _cache.update(at=time.time(), items=items)
    return items


def related(text: str, n: int = 3, items: list | None = None, now: float | None = None) -> list:
    """Alerts issued in the last 24 hours, about the same kind of hazard, whose area names a place the text also names."""
    fam = _families(text) if enabled() else set()
    if not fam:
        return []
    mine = set(re.findall(r"[a-z]{4,}", (text or "").lower()))
    now = time.time() if now is None else now
    out = []
    for a in (items if items is not None else _items()):
        if _recent(a.get("published", ""), now) and fam & _families(a["title"]) and mine & _area(a["title"]):
            out.append(a)
    return out[:n]
