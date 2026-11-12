from __future__ import annotations
from .i18n import *
from .lang import SUPPORTED
from .models import AUTHORITATIVE

def render_card(verdict: str, lang: str, citations: list) -> str:
    """Forwardable plain-text card: verdict first, one line of why, the citation link."""
    lang = lang if lang in SUPPORTED else "en"      # any supported language; a table with no entry for it falls back to English (tr)
    auth = [c for c in citations if c["tier"] in AUTHORITATIVE]
    lead = (auth or citations or [None])[0]
    src = lead["source"] if lead else ""
    why = tr(WHY, lang)[verdict].format(src=src)
    lines = [f"{EMOJI[verdict]} {tr(LABEL, lang)[verdict]}", why]
    if lead:
        note = tr(FC_NOTE, lang) + " - " if lead["tier"] not in AUTHORITATIVE else ""
        lines.append(f"{tr(SOURCE_LABEL, lang)}: {note}{lead['source']} - {lead['url']}")
    return "\n".join(lines)
