"""PIB press-release parsing and RSS index."""
from __future__ import annotations
import re
from bs4 import BeautifulSoup
from .fetch import fetch, http_host_of
from .langwords import DEBUNK_RE

PR_URL = "https://pib.gov.in/PressReleasePage.aspx?PRID={}"
RSS_URL = "https://www.pib.gov.in/RssMain.aspx?ModId={mod}&Lang={lang}&Regid={reg}"
DEBUNK_MARKERS = re.compile(
    r"\b(fake|false|misleading|baseless|fabricated|hoax|no such|#?PIBFactCheck|not true|incorrect|"
    r"clarif\w+|misinformation|rumou?rs?)\b|फर्जी|फ़र्ज़ी|झूठ|भ्रामक|अफवाह|నకిలీ|అబద్ధ|తప్పుడు|" + DEBUNK_RE, re.I)

def is_pib(url: str) -> bool:
    host = http_host_of(url)
    return host == "pib.gov.in" or host.endswith(".pib.gov.in")

def parse_release(html: str) -> dict:
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style"]):
        t.decompose()
    h = s.find(["h2", "h1"])
    title = h.get_text(" ", strip=True) if h else ""
    body_el = s.find(id="PdfDiv") or s.find(class_=re.compile("about-us-content-right"))
    body = body_el.get_text(" ", strip=True) if body_el else ""
    ministry = ""
    m = re.search(r"Ministry of [A-Z][A-Za-z ,&\-]+", s.get_text(" ", strip=True))
    if m:
        ministry = m.group(0).strip()
    date = ""
    m = re.search(r"Posted On:\s*([^\n|]{6,30}?\d{4})", s.get_text("\n", strip=True))
    if m:
        date = m.group(1).strip()
    return {"title": title, "body": re.sub(r"\s+", " ", body), "ministry": ministry, "posted_on": date}

def get_release(prid: int | str) -> dict | None:
    rec = fetch(PR_URL.format(prid))
    url = rec.get("final_url", "")
    if rec["status"] != 200 or not is_pib(url) or not rec["body"]:
        return None
    d = parse_release(rec["body"])
    if not d["title"] and not d["body"]:
        return None
    d.update(url=url, fetched_at=rec["fetched_at"], prid=str(prid))
    return d

def parse_rss(xml: str) -> list[dict]:
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        t = re.search(r"<title>(.*?)</title>", it, re.S)
        m = re.search(r"PRID=(\d+)", it)
        if t and m:
            out.append({"title": t.group(1).strip(), "prid": m.group(1)})
    return out

def rss_index(mods=(6,), langs=(1,), regs=(3,)) -> list[dict]:
    items = {}
    for mod in mods:
        for lang in langs:
            for reg in regs:
                rec = fetch(RSS_URL.format(mod=mod, lang=lang, reg=reg))
                if rec["status"] == 200 and is_pib(rec.get("final_url", "")):
                    for it in parse_rss(rec["body"]):
                        items[it["prid"]] = it
    return list(items.values())
