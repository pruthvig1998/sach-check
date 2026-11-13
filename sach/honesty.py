"""Display-only honesty notes for the result page (used by sach/site.py result_block).

Nothing here changes a verdict, a claim list, the cache or the ledger. Every helper returns '' (or the caller's existing markup)
when its condition is not met, so results without the new fields render exactly as before.
Counts come only from the trace and the result dict; nothing is estimated."""
from __future__ import annotations
import html
from datetime import date, datetime

from . import timefmt
from .i18n import UNVERIFIED_PANEL, tr
from .models import TIER_OFFICIAL, TIER_PIB, UNVERIFIED

_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
OLD_AFTER_MONTHS = 12          # a matched review older than this gets the 'debunk from' notice
EXTRACT_SHOWN = 3              # skipped sentences listed under 'Not checked'
_NEUTRAL = "background:var(--paper2);padding:14px 18px;border-radius:2px;margin:18px 0 0"


def _e(s) -> str:
    return html.escape(str(s), quote=True)


# ------------------------------------------------------------------ 1. UNVERIFIED on a live check
def _live_unverified(res: dict) -> bool:
    if res.get("no_claims") or res.get("verdict") != UNVERIFIED or res.get("layer") != "live":
        return False
    if res.get("degraded") or res.get("search_status") != "ok":
        return False                                  # limited mode or search down: an incomplete check, not this panel
    return not any(c.get("reason_code") == "timed_out" for c in (res.get("claims") or []))


def _trace_counts(res: dict) -> tuple[int, int]:
    """(official pages judged with stance 'none', PIB pages judged), summed over the claims' traces."""
    official_none = pib = 0
    for c in res.get("claims") or []:
        for s in ((c.get("trace") or {}).get("sources") or []):
            if (s.get("judged") or {}).get("outcome") != "answered":
                continue                              # only pages the AI judge actually answered on
            if s.get("tier") == TIER_OFFICIAL and s.get("stance") == "none":
                official_none += 1
            if s.get("tier") == TIER_PIB:
                pib += 1
    return official_none, pib


def unverified_panel(res: dict) -> str:
    if not _live_unverified(res):
        return ""
    lang = res.get("language", "en")
    t = tr(UNVERIFIED_PANEL, lang)
    official_none, pib = _trace_counts(res)
    n_claims = len(res.get("claims") or [])
    return (f'<section class="unv-panel" aria-labelledby="unv-h" style="{_NEUTRAL}">'
            f'<p id="unv-h" style="margin:0 0 6px"><b>{_e(t["title"])}</b></p>'
            f'<ul class="note" style="margin:0 0 12px;padding-left:18px">'
            f'<li>{_e(t["claims"].format(n=n_claims))}</li>'
            f'<li>{_e(t["official"].format(n=official_none))}</li>'
            f'<li>{_e(t["pib"].format(n=pib))}</li></ul>'
            f'<p style="margin:0 0 4px"><b>{_e(t["meaning_title"])}</b></p><p class="note" style="margin:0 0 12px">{_e(t["meaning"])}</p>'
            f'<p style="margin:0 0 4px"><b>{_e(t["next_title"])}</b></p><p class="note" style="margin:0 0 4px">{_e(t["next"])}</p>'
            f'<p class="note" style="margin:0">{_e(t["scope"])}</p></section>')


# ------------------------------------------------------------------ 2. old matched debunk, and the citation word
def cite_word(claim: dict) -> str:
    """'reviewed' for a MATCH claim's citation row, 'accessed' otherwise. The stored date_accessed key is not changed."""
    return "reviewed" if claim.get("layer") == "match" else "accessed"


def _months_before(today: date, months: int) -> date:
    y, m = today.year - months // 12, today.month - months % 12
    if m <= 0:
        y, m = y - 1, m + 12
    try:
        return today.replace(year=y, month=m)
    except ValueError:                                # 29-31 of a shorter month
        return date(y, m, 28)


def _review_day(value) -> date | None:
    d = timefmt.to_ist(value)                         # date-only inputs stay date-only (no time, no zone shift)
    return d.date() if d is not None else None


def old_debunk_notice(res: dict, today: date | None = None) -> str:
    today = today or datetime.now(timefmt.IST).date()
    cutoff = _months_before(today, OLD_AFTER_MONTHS)
    days = []
    for c in res.get("claims") or []:
        if c.get("layer") == "match" and c.get("match"):
            d = _review_day((c["match"] or {}).get("review_date"))
            if d is not None and d < cutoff:
                days.append(d)
    if not days:
        return ""
    oldest = min(days)
    label = f"{_MON[oldest.month - 1]} {oldest.year}"
    return (f'<p class="note" role="note" style="margin:12px 0 0">This is a debunk from {_e(label)}. Rumours return: '
            f'if the forward has new details, do not rely on it alone.</p>')


# ------------------------------------------------------------------ 3. what was not checked
def extraction_html(res: dict) -> str:
    ex = res.get("extraction")
    if not isinstance(ex, dict):
        return ""
    n, m = ex.get("sentences"), ex.get("checked")
    if not (isinstance(n, int) and isinstance(m, int)) or n <= m:
        return ""                                     # everything seen was checked, and no cap applied
    skipped = [s for s in (ex.get("skipped") or []) if isinstance(s, str) and s][:EXTRACT_SHOWN]
    items = "".join(f"<li>{_e(s)}</li>" for s in skipped)
    more = (n - m) - len(skipped)
    if more > 0:
        items += f'<li class="note">and {more} more</li>'
    listing = f'<p class="note" style="margin:8px 0 4px">Not checked:</p><ul class="note" style="margin:0;padding-left:18px">{items}</ul>' if items else ""
    return f'<details class="extract" style="margin-top:14px"><summary>Checked {m} of {n} sentences</summary>{listing}</details>'


# ------------------------------------------------------------------ 4. scam-shaped message with no checkable claim
SCAM_STAMP = '<div class="stamp big MISLEADING">Scam warning</div>'
SCAM_LEAD = ('<p class="scamlead" style="margin:0 0 10px"><b>No checkable fact here, but this looks like a scam pattern. '
             'Do not click links or share personal details.</b></p>')
