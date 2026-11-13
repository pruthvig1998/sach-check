"""Sach's own verdicts as schema.org ClaimReview (a JSON feed, and JSON-LD on shared result pages).

Who calls this: sach/web.py (`GET /?view=claimreview`, and the JSON-LD on `/?r=<id>`), sach/site.py (the anchor id on each ledger row).
Nothing existing serves the purpose: the ledger was only readable as an HTML table. Reads the ledger and, for permalinks, the share
store; writes nothing. stdlib only.

Properties used, and where they were confirmed (read 2026-11-13):
- Google Search Central, "Fact Check (ClaimReview) structured data"
  https://developers.google.com/search/docs/appearance/structured-data/factcheck
  Required: `claimReviewed`, `reviewRating` (a Rating), `url`. Recommended: `author` (the publisher of the fact check, not the
  claimant), `itemReviewed` (a Claim; `author`, `datePublished`, `appearance` only if known), and on the Rating `alternateName`
  (the text shown), `ratingValue`, `bestRating`, `worstRating` (worstRating >= 1, best > worst). Google asks publishers to document the
  scale: Sach uses 1 = False, 3 = Misleading, 5 = True (no 2 or 4: Sach has no "mostly" verdicts).
- schema.org/ClaimReview https://schema.org/ClaimReview : own property `claimReviewed`; `url`, `author`, `datePublished`,
  `inLanguage` and `citation` are inherited from Thing/CreativeWork, so they are valid here. `isBasedOn` is also valid but would only
  repeat `citation`, so it is not emitted.

Honest notes: (1) Google only shows ClaimReview rich results for publishers that meet its fact-check eligibility rules (several marked-up
pages, a corrections policy, no political entities, and so on), and its page says Google is phasing out ClaimReview in Search; it remains
read by the Fact Check Explorer and by other aggregators. Sach does not claim eligibility; the feed is open data either way.
(2) The `url` must be on the publisher's own domain: it is the share permalink or a ledger anchor, both on `site_url()`.
(3) The claimant is never invented: `itemReviewed` carries only `@type` and nothing else, because the ledger does not record who said it.

Attribution rule: only Sach's OWN live verdicts are published. A row whose `layer` is "match" (another checker's verdict), or that
carries an attribution/match field, is skipped, as is any row without a citation and any UNVERIFIED row (no rating to give).
"""
from __future__ import annotations
import hashlib, json, re
from . import cache, ledger, share
from .lang import BCP47
from .siteurl import site_url
from .report import driver_index

DEFAULT_LIMIT = 200
LINK_LOOKUPS = 50                       # share-permalink lookups per feed (each may be a remote store read)
MAX_CITATIONS = 5
CLAIM_MAX = 300
RATING = {"FALSE": (1, "False"), "MISLEADING": (3, "Misleading"), "TRUE": (5, "True")}
BEST, WORST = 5, 1
FOREIGN_FIELDS = ("attribution", "match", "matched_from", "matched_by", "checker")


def is_foreign(d) -> bool:
    """True for another checker's verdict (layer 'match' or any attribution/match field): never published as Sach's."""
    if not isinstance(d, dict):
        return True
    if str(d.get("layer") or "").lower() == "match":
        return True
    return any(d.get(k) for k in FOREIGN_FIELDS)


def _cites(row) -> list:
    out = []
    for c in row.get("citations") or []:
        u = str(c.get("url") or "") if isinstance(c, dict) else ""
        if u.lower().startswith(("http://", "https://")):
            out.append({"source": str(c.get("source") or ""), "url": u})
    return out


def qualifies(row) -> bool:
    return (isinstance(row, dict) and row.get("verdict") in RATING and not is_foreign(row)
            and bool(str(row.get("claim") or "").strip()) and bool(_cites(row)))


def row_id(row: dict) -> str:
    """Stable anchor id for a ledger row (also set on the ledger page's <tr>)."""
    k = (str(row.get("claim") or "") + "\x00" + str(row.get("checked_at") or "")).encode("utf-8")
    return "c-" + hashlib.sha1(k).hexdigest()[:12]


def language_tag(code) -> str | None:
    c = str(code or "")
    if c == "tl":
        return "te-Latn"                # Tinglish: Telugu in Latin letters (lang.BCP47 maps it to the speech voice te-IN)
    return BCP47.get(c) or (c if re.fullmatch(r"[a-z]{2,3}", c) else None)


def _clip(s: str, n: int = CLAIM_MAX) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def build(claim: str, verdict: str, date: str, lang, cites: list, url: str, site: str) -> dict | None:
    if verdict not in RATING or not claim or not cites:
        return None
    val, name = RATING[verdict]
    o = {"@type": "ClaimReview", "url": url, "claimReviewed": _clip(claim),
         "itemReviewed": {"@type": "Claim"},
         "author": {"@type": "Organization", "name": "Sach", "url": site},
         "reviewRating": {"@type": "Rating", "ratingValue": val, "bestRating": BEST, "worstRating": WORST, "alternateName": name}}
    if date:
        o["datePublished"] = date
    tag = language_tag(lang)
    if tag:
        o["inLanguage"] = tag
    o["citation"] = [{"@type": "CreativeWork", **({"name": c["source"]} if c["source"] else {}), "url": c["url"]} for c in cites[:MAX_CITATIONS]]
    return o


def _permalink(row: dict, site: str):
    for rl in (None, row.get("language")):
        try:
            rid = share.share_id(cache.key(row["claim"], rl))
            if share.load_share(rid):
                return share.permalink(rid, site)
        except Exception:
            pass
    return None


def share_link_for(claim: str, lang, site: str):
    """The share permalink for a single-claim forward, if one is stored (shared by trending)."""
    return _permalink({"claim": claim, "language": lang}, site)


def review_for_row(row: dict, site: str, lookup: bool = True) -> dict | None:
    if not qualifies(row):
        return None
    url = (_permalink(row, site) if lookup else None) or f"{site}/?view=ledger#{row_id(row)}"
    return build(row["claim"], row["verdict"], str(row.get("checked_at") or ""), row.get("language"), _cites(row), url, site)


def feed(limit: int = DEFAULT_LIMIT, site: str | None = None) -> dict:
    site = site or site_url()
    rows = sorted((r for r in ledger.load() if qualifies(r)), key=lambda r: str(r.get("checked_at") or ""), reverse=True)[:max(0, limit)]
    graph = []
    for i, r in enumerate(rows):
        o = review_for_row(r, site, lookup=i < LINK_LOOKUPS)
        if o:
            graph.append(o)
    return {"@context": "https://schema.org", "@graph": graph}


def feed_bytes(limit: int = DEFAULT_LIMIT) -> bytes:
    return json.dumps(feed(limit), ensure_ascii=False).encode("utf-8")


def result_review(res: dict, link: str, site: str | None = None) -> dict | None:
    """One ClaimReview for a shared live result, or None (match layer, UNVERIFIED, no claims, no citations)."""
    try:
        v = res.get("verdict")
        claims = res.get("claims") or []
        if v not in RATING or not claims or is_foreign(res) or any(is_foreign(c) for c in claims):
            return None
        pick = claims[driver_index(res)]                # the claim behind the overall verdict (report.driver_index), never claims[0] by default
        text = ((pick.get("claim") or {}).get("text")) or ""
        cites = _cites(pick)
        date = str(res.get("first_checked_at") or res.get("checked_at") or "")
        return build(text, v, date, res.get("language") or res.get("input_language"), cites, link, site or site_url())
    except Exception:
        return None


def ld_script(obj: dict) -> str:
    """A <script type="application/ld+json"> that cannot be broken out of: '<', '>', '&' and line separators are \\u-escaped."""
    s = json.dumps(obj, ensure_ascii=False)
    for a, b in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        s = s.replace(a, b)
    return '<script type="application/ld+json">%s</script>' % s


def json_ld_for_result(res: dict, link: str) -> str:
    o = result_review(res, link)
    if not o:
        return ""
    return ld_script({"@context": "https://schema.org", **o})
