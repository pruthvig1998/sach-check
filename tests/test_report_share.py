"""PIB report flow and shareable verdict image: offline tests (no browser, no network)."""
import ast, copy, json, pathlib, re
from urllib.parse import unquote, urlparse, parse_qs
import pytest
from sach import report
from sach.report import build_report, BODY_MAX
from sach.site import result_block, layout, home
from sach.i18n import LABEL

CITE = {"source": "PIB (Press Information Bureau)", "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=1618590&x=1#a",
        "tier": "pib_debunk", "date_accessed": "2026-11-10", "fetched_at": "2026-11-10T08:00:00+00:00"}
CITE2 = {"source": "Ministry of Finance", "url": "https://finmin.gov.in/notice.pdf", "tier": "official",
         "date_accessed": "2026-11-11", "fetched_at": "2026-11-11T08:00:00+00:00"}
FC = {"source": "Alt News", "url": "https://altnews.in/story", "tier": "factchecker", "date_accessed": "2026-11-11", "fetched_at": "x"}


def claim(text, verdict="FALSE", cites=(CITE,)):
    return {"claim": {"text": text, "domain": "scheme"}, "verdict": verdict, "english": "", "reason_code": "official_contradiction",
            "citations": [dict(c) for c in cites], "trace": {}}


def mk(claims, verdict="FALSE", lang="en", **kw):
    r = {"language": lang, "input_language": lang, "verdict": verdict, "claims": claims, "checked_at": "2026-11-12T09:30:00+00:00",
         "card": f"❌ {LABEL[lang][verdict]}\nPIB says this claim is false.\nSource: PIB - {CITE['url']}", "degraded": False,
         "trace": {"claims_extracted": len(claims), "overall_rule": "x"}}
    r.update(kw)
    return r


FALSE = mk([claim("Government will give Rs 5000 to every woman. Forward to all groups!")])


# ------------------------------------------------------------ build_report
def test_build_report_shape_and_roundtrip():
    r = build_report(FALSE)
    assert set(r) == {"subject", "body", "whatsapp_url", "mailto_url", "portal_url"}
    assert "Government will give Rs 5000 to every woman. Forward to all groups!" in r["body"]
    assert "Sach's verdict: FALSE. An official source contradicts this claim." in r["body"]
    assert f"{CITE['source']}: {CITE['url']} (accessed 2026-11-10)" in r["body"]
    assert "Checked with Sach (https://" in r["body"] and "on 2026-11-12. Sach is an independent open-source tool, not a government service." in r["body"]
    wa = urlparse(r["whatsapp_url"])
    assert (wa.scheme, wa.netloc, wa.path) == ("https", "wa.me", "/918799711259")
    assert parse_qs(wa.query, keep_blank_values=True)["text"] == [r["body"]]
    assert unquote(r["whatsapp_url"].split("text=", 1)[1]) == r["body"]
    m = r["mailto_url"]
    assert m.startswith("mailto:socialmedia@pib.gov.in?subject=")
    subj, body = re.match(r"mailto:[^?]+\?subject=([^&]*)&body=(.*)$", m, re.S).groups()
    assert unquote(subj) == r["subject"]
    assert unquote(body).replace("\r\n", "\n") == r["body"]
    assert r["portal_url"] == "https://factcheck.pib.gov.in/"


def test_only_verified_channels_appear():
    r = build_report(FALSE)
    blob = json.dumps(r) + report.report_html(FALSE)
    assert "gmail" not in blob and "pibfactcheck@" not in blob
    assert report.PIB_EMAIL.endswith("@pib.gov.in")
    assert "8799711259" in blob and not re.search(r"wa\.me/\+", blob)         # digits only


def test_only_false_claims_citations_in_body():
    res = mk([claim("False one", "FALSE", (CITE, FC)), claim("True one", "TRUE", (CITE2,)), claim("Unknown", "UNVERIFIED", ())])
    b = build_report(res)["body"]
    assert "False one" in b and CITE["url"] in b
    assert "True one" not in b and CITE2["url"] not in b and "Unknown" not in b
    assert b.index(CITE["url"]) < b.index(FC["url"])                 # official before fact-checker


def test_no_false_claims_gives_empty():
    assert build_report(mk([claim("x", "TRUE")], verdict="TRUE")) == {}


def test_length_cap_and_urls_never_split():
    cites = [dict(CITE, url=f"https://pib.gov.in/PressReleasePage.aspx?PRID={i}", source=f"Source number {i}") for i in range(30)]
    res = mk([claim("word " * 400, "FALSE", cites), claim("Another long claim " * 60), claim("Third " * 100)])
    r = build_report(res)
    assert len(r["body"]) <= BODY_MAX
    urls = re.findall(r"https://pib\.gov\.in/\S+", r["body"])
    assert urls and all(re.fullmatch(r"https://pib\.gov\.in/PressReleasePage\.aspx\?PRID=\d+", u) for u in urls)
    assert "Sach's verdict" in r["body"] and "Checked with Sach" in r["body"]
    assert "…" in r["body"]


def test_huge_url_is_dropped_not_cut():
    big = dict(CITE, url="https://pib.gov.in/" + "a" * 900)
    b = build_report(mk([claim("c", "FALSE", (big, CITE2))]))["body"]
    assert "a" * 50 not in b and CITE2["url"] in b


@pytest.mark.parametrize("text", ["सरकार कोरोना सहायता योजना के तहत सभी को 1000 रुपये दे रही है। जल्दी रजिस्टर करें।",
                                  "కేంద్ర ప్రభుత్వ ఉద్యోగుల పదవీ విరమణ వయస్సు 50 సంవత్సరాలకు తగ్గిస్తున్నారు అని సందేశం"])
def test_indic_claims_preserved_and_encoded(text):
    r = build_report(mk([claim(text)], lang="hi"))
    assert text in r["body"]
    assert unquote(r["whatsapp_url"].split("text=", 1)[1]) == r["body"]
    assert len(r["whatsapp_url"]) < 8000


def test_long_indic_claim_stays_within_encoded_limit_and_valid_unicode():
    r = build_report(mk([claim("క్షమించండి " * 300)]))
    assert len(r["body"]) <= BODY_MAX
    assert len(r["whatsapp_url"]) < 7000
    r["body"].encode("utf-8")


def test_hostile_claim_roundtrips_and_cannot_inject_headers():
    evil = "<script>alert(1)</script>\nBcc: x@y.z\r\n&amp; #hash ?q=1 %41 \x00"
    r = build_report(mk([claim(evil)]))
    assert "\x00" not in r["body"] and "\nBcc:" not in r["subject"] and "\n" not in r["subject"]
    assert "<script>alert(1)</script> Bcc: x@y.z &amp; #hash ?q=1 %41" in r["body"]
    assert unquote(r["whatsapp_url"].split("text=", 1)[1]) == r["body"]
    assert "\n" not in r["mailto_url"] and "&body=" in r["mailto_url"] and r["mailto_url"].count("?") == 1
    assert "#" not in r["whatsapp_url"] and "<" not in r["whatsapp_url"]


# ------------------------------------------------------------ result_block: report
def html_of(res):
    return result_block(res)


def test_report_present_only_for_false():
    h = html_of(FALSE)
    assert '<details class="report"' in h and "Report this to PIB Fact Check" in h
    assert "PIB Fact Check handles claims about the Government of India. For a state government matter, contact that state&#x27;s own office." in h
    assert '<textarea id="rpt-text" class="rpt-text" readonly' in h
    for ident in ("rpt-copy", "rpt-portal", "rpt-wa", "rpt-mail"):
        assert f'id="{ident}"' in h
    assert 'href="https://factcheck.pib.gov.in/"' in h
    assert re.search(r'id="rpt-wa" href="https://wa\.me/918799711259\?text=[^"]+" target="_blank" rel="noopener"', h)
    assert 'id="rpt-mail" href="mailto:socialmedia@pib.gov.in?subject=' in h


@pytest.mark.parametrize("v", ["TRUE", "MISLEADING", "UNVERIFIED"])
def test_report_absent_for_other_verdicts(v):
    res = mk([claim("x", v, (CITE2,))], verdict=v)
    h = html_of(res)
    assert "rpt-" not in h and "Report this to PIB" not in h and "details class=\"report\"" not in h


def test_report_absent_for_no_claims_and_degraded():
    nc = {"language": "en", "verdict": "UNVERIFIED", "no_claims": True, "claims": [], "card": "NO CLAIM\nx", "checked_at": "2026-11-12T00:00:00"}
    assert "rpt-" not in html_of(nc)
    assert "rpt-" not in html_of(mk([claim("x")], degraded=True))


def test_ids_unique_and_no_collision_with_existing():
    h = html_of(FALSE)
    ids = re.findall(r'\bid="([^"]+)"', h)
    assert len(ids) == len(set(ids))
    for must in ("copy", "dl", "cardtext", "img-share", "sach-card-data"):
        assert must in ids
    assert all(i.startswith("rpt-") for i in ids if "rpt" in i)


def test_report_textarea_is_escaped_and_no_script_breakout():
    evil = '</textarea><script>alert(1)</script><img src=x onerror=alert(2)>"\'&'
    res = mk([claim(evil)])
    h = html_of(res)
    assert "<script>alert(1)" not in h and "onerror=alert(2)>" not in h and "</textarea><script" not in h
    assert h.count("<textarea") == 1 and h.count("</textarea>") == 1
    page = layout(h).decode()
    assert page.count("<script") == page.count("</script>") == 6         # CHANGED (SHARE package): + the share-data JSON block (analytics, app, voice, install/history, card data, share data)
    assert "<script>alert" not in page and "<img src=x" not in page


# ------------------------------------------------------------ result_block: image data + controls
def card_json(h):
    m = re.search(r'<script type="application/json" id="sach-card-data">(.*?)</script>', h, re.S)
    assert m
    return json.loads(m.group(1)), m.group(1)


def test_card_data_matches_result_and_controls_present():
    res = mk([claim("Government will give Rs 5000", "FALSE", (CITE2, CITE))], lang="te")
    h = html_of(res)
    d, raw = card_json(h)
    assert d["verdict"] == "FALSE" and d["word"] == LABEL["te"]["FALSE"] and d["word_en"] == "FALSE" and d["lang"] == "te"
    assert d["claim"] == "Government will give Rs 5000" and d["why"] == "PIB says this claim is false."
    assert d["source"] == CITE["source"] or d["source"] == CITE2["source"]        # authoritative citation, first in order
    assert d["date"] in ("2026-11-10", "2026-11-11")
    assert 'id="dl"' in h and 'id="img-share"' in h and "hidden" in h.split('id="img-share"')[1][:40]
    assert "<" not in raw and ">" not in raw


@pytest.mark.parametrize("v", ["TRUE", "MISLEADING", "UNVERIFIED"])
def test_card_data_present_for_every_verdict(v):
    d, _ = card_json(html_of(mk([claim("c", v, (CITE2,))], verdict=v)))
    assert d["verdict"] == v and d["word"] == LABEL["en"][v]


@pytest.mark.parametrize("lang,claim_text", [("hi", "सरकार सभी को 1000 रुपये दे रही है"), ("te", "ప్రభుత్వం అందరికీ డబ్బు ఇస్తోంది")])
def test_hindi_telugu_results_render(lang, claim_text):
    h = html_of(mk([claim(claim_text)], lang=lang))
    d, raw = card_json(h)
    assert d["claim"] == claim_text and d["word"] == LABEL[lang]["FALSE"] and d["lang"] == lang
    assert claim_text in h and claim_text in report.build_report(mk([claim(claim_text)], lang=lang))["body"]


def test_hostile_claim_cannot_break_out_of_json_block():
    evil = '</script><script>alert(1)</script>"\\   & <!-- '
    h = html_of(mk([claim(evil)]))
    d, raw = card_json(h)
    assert d["claim"] == " ".join(evil.split())
    assert "</script><script>" not in h and "<script>alert" not in h
    assert " " not in raw
    page = layout(h).decode()
    assert page.count("</script>") == page.count("<script")


def test_page_script_has_drawing_code_and_no_old_stub():
    js = layout(html_of(FALSE)).decode()
    for piece in ("1080", "1350", "measureText", "document.fonts.load", "navigator.canShare", "navigator.share", "toBlob",
                  "getComputedStyle", "sach-card-data", "'sach-'+D.verdict.toLowerCase()+'.png'", "location.origin", "rpt-copy"):
        assert piece in js
    assert "sach-verdict.png" not in js and "x.fillText(l.slice(0,70)" not in js


# ------------------------------------------------------------ Sach sends nothing
def test_report_module_imports_no_network_code():
    tree = ast.parse(pathlib.Path(report.__file__).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
            mods |= {(n.module or "") + "." + a.name for a in n.names}
    banned = ("urllib.request", "http.client", "socket", "requests", "httpx", "smtplib", "ssl", "urllib3", "aiohttp")
    assert not [m for m in mods if any(m == b or m.startswith(b + ".") for b in banned)], mods
    assert {m for m in mods if m.startswith("urllib")} <= {"urllib.parse", "urllib.parse.quote"}
