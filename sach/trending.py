"""'What India is checking this week': the most-checked claims in the public ledger over the last 7 days.

Who calls this: sach/site.py (`home`, top HOME_TOP), sach/impact.py (impact page, top IMPACT_TOP), sach/web.py (`/?view=trending&format=json`).
Nothing existing serves the purpose. Reads the ledger and the share store; writes nothing. Everything is computed at request time from
ledger rows: nothing is typed in. A "check" here is one ledger row (one claim of one forward), so a forward holding two claims counts
once for each claim.

Rules: rows are grouped by the cache normaliser (cache.normalise: NFKC, case-folded, whitespace collapsed) with edge punctuation
trimmed; only rows from the last WINDOW_DAYS count; claims that look like personal data (an e-mail address, or 8 or more digits in a row
once spaces and hyphens between digits are removed, i.e. phone numbers and ID numbers) are never listed; a group's verdict is that of
its latest row; matched results (layer "match" or an attribution field) show "Checked by <checker>" instead of a Sach verdict stamp.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone
from . import cache, claimreview, ledger
from .lang import NAMES, to_ascii_digits
from .siteurl import site_url

WINDOW_DAYS = 7
HOME_TOP = 5
IMPACT_TOP = 10
EMPTY = "Nothing trending yet this week"
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_DIGITS = re.compile(r"\d{8,}")


def looks_personal(text: str) -> bool:
    t = to_ascii_digits(str(text))
    if _EMAIL.search(t):
        return True
    return bool(_DIGITS.search(re.sub(r"(?<=\d)[\s\-.]+(?=\d)", "", t)))


def norm(text: str) -> str:
    return re.sub(r"^[\W_]+|[\W_]+$", "", cache.normalise(text))


def _when(row) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(row.get("checked_at")).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def checker_name(row) -> str | None:
    """Who made a matched verdict, or None for Sach's own. Field names are read defensively (layer/attribution are owned elsewhere)."""
    if not claimreview.is_foreign(row):
        return None
    for k in ("attribution", "match", "matched_from", "matched_by", "checker"):
        v = row.get(k)
        if isinstance(v, dict):
            v = v.get("checker") or v.get("name") or v.get("source") or v.get("org")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "another fact-checker"


def top(limit: int = HOME_TOP, now: datetime | None = None, with_links: bool = True) -> list:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WINDOW_DAYS)
    groups: dict = {}
    for r in ledger.load():
        if not isinstance(r, dict) or not str(r.get("claim") or "").strip() or not r.get("verdict"):
            continue
        t = _when(r)
        if t is None or t < cutoff or t > now + timedelta(days=1) or looks_personal(r["claim"]):
            continue
        k = norm(r["claim"])
        if k:
            groups.setdefault(k, []).append((t, r))
    items = []
    for k, rs in groups.items():
        rs.sort(key=lambda x: x[0])
        t, last = rs[-1]
        langs = sorted({str(r.get("language") or "en") for _, r in rs})
        cites = claimreview._cites(last)
        items.append({"claim": str(last["claim"]).strip(), "count": len(rs), "verdict": str(last["verdict"]),
                      "languages": langs, "last_checked": t.isoformat(timespec="seconds"),
                      "citation": cites[0] if cites else None, "checked_by": checker_name(last), "link": None, "_raw": {"claim": last["claim"], "checked_at": last.get("checked_at")}})
    items.sort(key=lambda i: (i["count"], i["last_checked"]), reverse=True)
    items = items[:max(0, limit)]
    site = site_url()
    for i in items:
        if with_links and not i["checked_by"]:
            i["link"] = claimreview.share_link_for(i["claim"], i["languages"][0], site)
        if not i["link"]:
            i["link"] = f"{site}/?view=ledger#{claimreview.row_id(i['_raw'])}"
    for i in items:
        i.pop("_raw", None)
    return items


def data(limit: int = IMPACT_TOP) -> dict:
    return {"window_days": WINDOW_DAYS, "generated_at": ledger.now(), "items": top(limit),
            "how": "Ledger rows from the last %s days, grouped by normalised claim text; count = rows in the group." % WINDOW_DAYS}


CSS = """<style>
.trend{border:2px solid var(--rule);border-radius:6px;padding:14px 16px;margin:0}
.trend ol{list-style:none;margin:10px 0 0;padding:0}.trend li{padding:12px 0;border-bottom:1px solid color-mix(in srgb,var(--ink) 25%,transparent);overflow-wrap:anywhere}
.trend li:last-child{border-bottom:0}.trend .tm{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;margin-top:6px}
.trend .stamp{font-size:13px}.trend a{overflow-wrap:anywhere}
</style>"""


def section_html(limit: int = HOME_TOP) -> str:
    """The compact section (escaped). Never raises: an error shows the empty state."""
    from .site import esc, stamp                       # site imports this module lazily, so import it lazily too
    try:
        items = top(limit)
    except Exception:
        items = []
    if not items:
        body = '<p class="note">%s.</p>' % esc(EMPTY)
    else:
        li = ""
        for i in items:
            st = ('<span class="note"><b>Checked by %s</b></span>' % esc(i["checked_by"]) if i["checked_by"]
                  else (stamp(i["verdict"], "sm") if i["verdict"] in ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED") else ""))
            c = i["citation"]
            cite = (' · <a href="%s" rel="noopener">%s</a>' % (esc(c["url"], quote=True), esc(c["source"] or c["url"])) if c else "")
            lg = ", ".join(esc(NAMES.get(x, x)) for x in i["languages"])
            li += ('<li><a href="%s">%s</a><div class="tm">%s<span class="note">Checked %s time%s · %s%s</span></div></li>'
                   % (esc(i["link"], quote=True), esc(i["claim"]), st, i["count"], "" if i["count"] == 1 else "s", lg, cite))
        body = "<ol>%s</ol>" % li
    return ('%s<section id="trending"><div class="wrap"><h2>What India is checking this week</h2>'
            '<p class="sub">The claims checked most often on Sach in the last %s days, counted from the public ledger.</p>'
            '<div class="trend">%s</div></div></section>') % (CSS, WINDOW_DAYS, body)
