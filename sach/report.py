"""Report-to-PIB flow and the data behind the shareable verdict image.

Sach NEVER sends anything. Every control built here only opens a channel (PIB portal, the person's own WhatsApp,
the person's own mail app) with a prefilled, human-readable message that the person reviews and sends themselves.
This module does no I/O of any kind and imports nothing that can touch the network (a test enforces that).

PIB Fact Check channels, verified from official PIB pages on 2026-11-12 (fetched with curl, honest User-Agent):
  * WhatsApp  +91 87997 11259 -> https://factcheck.pib.gov.in/  ("fact checked through the following number - WhatsApp +91-8799711259")
  * Email     socialmedia@pib.gov.in -> same page: "...or email: socialmedia[at]pib[dot]gov[dot]in" (the page obfuscates it)
  * Portal    https://factcheck.pib.gov.in/ (query form: https://factcheck.pib.gov.in/feedbacklogin.aspx, needs email + OTP)
  * https://pib.gov.in/aboutfactchecke.aspx confirms "Users send requests over WhatsApp, email or a web portal" and that only
    queries about the Government of India are actionable. It lists a second address, factcheck@pib.gov.in, under "Contact Us"
    for "further information about our work" (the Director's contact). That is NOT the submission address, so it is not used.
  * pibfactcheck@gmail.com (from the original brief) appears on no official PIB page, so it is deliberately NOT used.
"""
from __future__ import annotations
import html, json, unicodedata
from urllib.parse import quote
from .i18n import LABEL, text_lang
from .models import AUTHORITATIVE
from .siteurl import site_url

PIB_WHATSAPP_DISPLAY = "+91 87997 11259"
PIB_WHATSAPP_DIGITS = "918799711259"
PIB_EMAIL = "socialmedia@pib.gov.in"
PIB_PORTAL = "https://factcheck.pib.gov.in/"
SCOPE_NOTE = ("PIB Fact Check handles claims about the Government of India. "
              "For a state government matter, contact that state's own office.")

BODY_MAX = 1500            # characters in the plain-text report
ENCODED_MAX = 6000         # characters in the percent-encoded body (Hindi/Telugu expand ~9x), keeps wa.me / mailto links usable
URL_MAX = 300              # a citation whose URL is longer than this is left out rather than ever being cut
WHY_LINE = "An official source contradicts this claim."
_MARKS = ("Mn", "Mc", "Cf")
_VIRAMAS = ("्", "్")


def _clean(text) -> str:
    """Collapse whitespace/newlines to single spaces and drop control characters; every other character is kept as forwarded."""
    s = "".join(ch for ch in str(text) if unicodedata.category(ch) != "Cc" or ch.isspace())
    return " ".join(s.split())


def _clip(text: str, limit: int) -> str:
    """Shorten at a word boundary with an ellipsis; never leaves a dangling combining mark or virama."""
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    if cut < limit // 2:
        cut = limit - 1
        while cut > 0 and (unicodedata.category(text[cut]) in _MARKS or text[cut - 1] in _VIRAMAS):
            cut -= 1
    return text[:cut].rstrip() + "…"


def false_claims(result: dict) -> list:
    # a matched claim is a fact-checker's verdict, not Sach's: it is never reported to PIB as "Sach's verdict"
    return [c for c in (result.get("claims") or []) if c.get("verdict") == "FALSE" and c.get("layer", "live") != "match"]


def _sources(claims: list) -> list:
    """Citations that drove the FALSE verdicts: citations of the FALSE claims, official ones first, de-duplicated by URL."""
    seen, out = set(), []
    pool = [x for c in claims for x in (c.get("citations") or [])]
    for x in sorted(pool, key=lambda x: x.get("tier") not in AUTHORITATIVE):       # stable: keeps claim order inside a tier
        url = str(x.get("url", ""))
        if not url or url in seen or len(url) > URL_MAX:
            continue
        seen.add(url)
        out.append({"source": _clean(x.get("source", "")), "url": url, "date": str(x.get("date_accessed", ""))[:10]})
    return out


def _compose(claims: list, srcs: list, claim_limit: int, checked: str) -> str:
    quoted = [f"Claim {i}: \"{_clip(_clean(c['claim']['text']), claim_limit)}\"" if len(claims) > 1
              else f"Claim: \"{_clip(_clean(c['claim']['text']), claim_limit)}\"" for i, c in enumerate(claims, 1)]
    parts = ["Please fact-check this claim that is being forwarded on WhatsApp.", "\n".join(quoted),
             f"Sach's verdict: FALSE. {WHY_LINE}"]
    if srcs:
        lines = [f"- {s['source']}: {s['url']}" + (f" (accessed {s['date']})" if s["date"] else "") for s in srcs]
        parts.append("Sources:\n" + "\n".join(lines))
    parts.append(f"Checked with Sach ({site_url()}) on {checked}. Sach is an independent open-source tool, not a government service.")
    return "\n\n".join(parts)


def build_report(result: dict, lang: str = "en") -> dict:
    """Prefilled PIB submission for a result with FALSE claims. Always English (PIB works in English); the claim text is quoted
    in its original language. `lang` is accepted for symmetry with the card and deliberately not used.
    Returns {"subject", "body", "whatsapp_url", "mailto_url", "portal_url"} ({} when there is no FALSE claim)."""
    claims = false_claims(result)
    if not claims:
        return {}
    checked = str(result.get("checked_at", ""))[:10]
    srcs = _sources(claims)
    # Trim least important first: extra citation lines, then claim length, then extra claims. URLs are whole lines' tails: never cut.
    plans = [(len(claims), 600, k) for k in range(len(srcs), 0, -1)] + [(len(claims), n, min(1, len(srcs))) for n in (400, 250, 150, 90)]
    plans += [(n, 90, min(1, len(srcs))) for n in range(len(claims) - 1, 0, -1)] + [(1, 60, 0)]
    body = ""
    for ncl, limit, ns in plans:
        body = _compose(claims[:ncl], srcs[:ns], limit, checked)
        if len(body) <= BODY_MAX and len(quote(body, safe="")) <= ENCODED_MAX:
            break
    subject = "Fact-check request: " + _clip(_clean(claims[0]["claim"]["text"]), 80)
    return {"subject": subject, "body": body,
            "whatsapp_url": f"https://wa.me/{PIB_WHATSAPP_DIGITS}?text=" + quote(body, safe=""),
            "mailto_url": f"mailto:{PIB_EMAIL}?subject=" + quote(subject, safe="") + "&body=" + quote(body.replace("\n", "\r\n"), safe=""),
            "portal_url": PIB_PORTAL}


def report_html(res: dict) -> str:
    """The `<details class="report">` block. Only for a FALSE verdict that is not degraded; otherwise ''. Works without JavaScript."""
    if res.get("verdict") != "FALSE" or res.get("degraded") or res.get("no_claims"):
        return ""
    r = build_report(res)
    if not r:
        return ""
    e = html.escape
    return (f'<details class="report" id="rpt-box"><summary>Report this to PIB Fact Check<span class="rpt-scope">{e(SCOPE_NOTE)}</span></summary>'
            f'<p class="note">Sach sends nothing. Copy this text, or use a button to open PIB&#39;s own channel with it filled in; you review and send it yourself.</p>'
            f'<textarea id="rpt-text" class="rpt-text" readonly rows="12" aria-label="Report text for PIB Fact Check">{e(r["body"])}</textarea>'
            f'<div class="row rpt-row"><button class="btn" id="rpt-copy" type="button">Copy text</button>'
            f'<a class="btn ghost" id="rpt-portal" href="{e(r["portal_url"])}" target="_blank" rel="noopener">Open PIB Fact Check portal</a>'
            f'<a class="btn ghost" id="rpt-wa" href="{e(r["whatsapp_url"])}" target="_blank" rel="noopener">Send on WhatsApp</a>'
            f'<a class="btn ghost" id="rpt-mail" href="{e(r["mailto_url"])}">Send by email</a></div>'
            f'<p class="note">PIB WhatsApp: {e(PIB_WHATSAPP_DISPLAY)} · email: {e(PIB_EMAIL)}</p></details>')


# ---------------------------------------------------------------- shareable verdict image
def card_data(res: dict) -> dict:
    """Everything the client-side canvas needs, taken from the real result (never hard-coded)."""
    v = res["verdict"]
    lang = res.get("language", "en")
    labels = LABEL.get(lang, LABEL["en"])
    lines = str(res.get("card", "")).split("\n")
    claims = res.get("claims") or []
    cites = [x for c in claims for x in (c.get("citations") or [])]
    lead = ([x for x in cites if x.get("tier") in AUTHORITATIVE] or cites or [None])[0]
    ms = [c for c in claims if c.get("layer") == "match" and c.get("match")]
    if ms:       # a matched verdict is THEIR verdict: the image names the checker, the review date and their rating, never Sach's label
        c0 = next((c for c in ms if c["verdict"] == v), ms[0])
        m = c0["match"]
        word = str(m.get("rating_text", ""))
        return {"verdict": c0["verdict"], "word": word, "word_en": word, "lang": "en",
                "why": f'Checked by {m["checker"]} on {m["review_date"]}: rated "{word}". Sach did not run its own check.',
                "claim": _clean(c0["claim"]["text"]), "source": _clean(m["checker"]) + " fact-check", "date": str(m["review_date"])[:10],
                "match": {"checker": m["checker"], "review_url": m["review_url"], "review_date": m["review_date"], "rating_text": word}}
    return {"verdict": v, "word": labels.get(v, v), "word_en": LABEL["en"].get(v, v), "lang": text_lang(lang),
            "why": lines[1] if len(lines) > 1 else "",
            "claim": _clean(claims[0]["claim"]["text"]) if claims else "",
            "source": _clean(lead.get("source", "")) if lead else "",
            "date": str(lead.get("date_accessed", ""))[:10] if lead else ""}


def card_data_script(res: dict) -> str:
    """JSON in a non-executable script element; `<`, `>`, `&` and line separators are \\u-escaped so claim text cannot break out."""
    s = json.dumps(card_data(res), ensure_ascii=False)
    for ch, rep in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        s = s.replace(ch, rep)
    return f'<script type="application/json" id="sach-card-data">{s}</script>'
