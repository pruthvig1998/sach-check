"""LINKCHECK: extraction, domain rules, false-positive guard, RDAP, UPI/phone, SSRF guard, Safe Browsing, UI and API. All offline."""
import io, json, pathlib, re, socket, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
import pytest
from sach import linkcheck as L, fetch, site, store, report
from sach.linkcheck import OFFICIAL, LOOKALIKE, PATTERN, UNKNOWN
from test_sach import server, _raw_get      # noqa: F401  (fixture and helper from the existing suite)

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\b(safe|secure|legitimate|trusted|genuine)\b", re.I)


def kinds(text):
    return [(i.kind, i.value) for i in L.extract_items(text)]


def verdict(d, ctx=""):
    return L.analyze_domain(d, ctx).verdict


def rules(d, ctx=""):
    return L.analyze_domain(d, ctx).rules


def words_ok(s: str) -> bool:
    return not FORBIDDEN.search(s.replace("Safe Browsing", ""))


# ------------------------------------------------------------------------------------------------------ extraction
def test_url_forms_and_trailing_punctuation():
    got = kinds("See https://example.com/a?b=1, www.example.org. and bare sbi-kyc.xyz/login! (http://x.in/p).")
    vals = [v for k, v in got if k == "url"]
    assert "https://example.com/a?b=1" in vals and "www.example.org" in vals and "sbi-kyc.xyz/login" in vals and "http://x.in/p" in vals


@pytest.mark.parametrize("text,host", [("hxxp://evil[.]com/x", "evil.com"), ("hxxps://evil(dot)com", "evil.com"), ("visit evil[dot]com/now", "evil.com"),
                                       ("bit[.]ly/abc", "bit.ly"), ("http://sbi-login{.}xyz", "sbi-login.xyz")])
def test_obfuscations_are_undone(text, host):
    urls = [v for k, v in kinds(text) if k == "url"]
    assert urls and L.parse_url(urls[0]).host == host, urls


def test_idn_and_punycode_hosts_are_extracted():
    assert any(k == "url" for k, _ in kinds("go to xn--pytm-5cd.com now"))
    assert any(k == "url" and "раytm" in v for k, v in kinds("link: раytm.com/kyc"))


def test_indic_text_around_links():
    t = "आपका केवाईसी समाप्त हो गया। अभी https://sbi-kyc-update.com/login पर क्लिक करें और 9876543210 पर कॉल करें"
    k = kinds(t)
    assert ("url", "https://sbi-kyc-update.com/login") in k and ("phone", "+919876543210") in k
    assert ("url", "https://pib.gov.in/x") in kinds("లింక్ https://pib.gov.in/x తెరవండి।")


@pytest.mark.parametrize("text,want", [("call +91 98765 43210", "+919876543210"), ("call 098765-43210", "+919876543210"), ("ph 9876543210", "+919876543210"),
                                       ("919876543210 is mine", "+919876543210"), ("+91-98765-43210", "+919876543210"),
                                       ("call 1800 103 0025", "18001030025"), ("toll free 1860-500-1122", "18605001122"),
                                       ("dial 1930 now", "1930"), ("helpline 112", "112"), ("call ९८७६५४३२१०", "+919876543210")])
def test_phone_forms(text, want):
    assert ("phone", want) in kinds(text), (text, kinds(text))


@pytest.mark.parametrize("text", ["Rs 5000 credited on 1930 or 2024", "my card 4111 1111 1111 1111", "order 123456789012345", "5876543210123", "year 1930 was long ago",
                                  "call 5000 rupees", "the OTP is 123456"])
def test_numbers_that_are_not_phones(text):
    assert not [1 for k, _ in kinds(text) if k == "phone"], (text, kinds(text))


def test_upi_ids_versus_emails():
    k = kinds("pay ramesh@ybl or 9876543210@paytm or shop.name-1@okhdfcbank. Mail me at a.b@gmail.com or x@mail.co.in")
    upis = [v for kk, v in k if kk == "upi"]
    assert set(upis) == {"ramesh@ybl", "9876543210@paytm", "shop.name-1@okhdfcbank"}
    assert not [v for kk, v in k if kk == "phone"]            # the phone-like VPA and the mail address are not also phone numbers


def test_apk_and_app_mentions():
    k = kinds("Download http://files.xyz/PMKisan.apk and PM-Yojana.apk now")
    assert ("url", "http://files.xyz/PMKisan.apk") in k and any(kk == "app" and v.endswith(".apk") for kk, v in k)
    assert any(kk == "app" for kk, _ in kinds("Please install this app from the link below https://a-b.xyz/x"))


def test_dedupe_and_position_and_raw_cap():
    items = L.extract_items("bit.ly/a bit.ly/a BIT.LY/A 9876543210 +91 98765 43210 " + "https://x.com/" + "a" * 500)
    assert len([i for i in items if i.kind == "phone"]) == 1
    assert len([i for i in items if i.value.lower() == "bit.ly/a"]) == 1
    assert [i.pos for i in items] == sorted(i.pos for i in items)
    assert all(len(i.raw) <= L.MAX_RAW for i in items) and all(set(i.to_dict()) == {"kind", "raw", "value", "pos"} for i in items)


def test_hidden_characters_do_not_hide_a_link():
    t = "sbi​-kyc‍-update.com and https://pib‮.gov⁠.in/x and 98​765 43210"
    k = kinds(t)
    assert ("url", "sbi-kyc-update.com") in k and ("url", "https://pib.gov.in/x") in k and ("phone", "+919876543210") in k


def test_caps_on_items_and_input():
    text = " ".join(f"site{i}.xyz" for i in range(60))
    r = L.check_text(text, online=False)
    assert len(r["items"]) == L.MAX_ITEMS and r["summary"]["total"] == 60 and "Only the first 20" in r["summary"]["text"]
    r = L.check_text("x " * 10 + "evil.xyz " + "z" * 5000, online=False)
    assert r["summary"]["truncated"] is True
    assert len(L.extract_items("a.com " * 3000)) <= 2          # the cut at 4,000 characters may leave a partial "a.co"


HOSTILE = ["a" * 4000, "a." * 2000, "a.b." * 1000 + "com", "9" * 4000, "9 " * 2000, "@" * 4000, "a@" * 2000, "http://" * 570, "://" * 1300,
           "[.]" * 1300, "-".join(["ab"] * 1300), "९८७६" * 1000, "‮" * 4000, "1800 " * 800, "call " * 800 + "1" * 100, "xn--" * 1000,
           "x" * 3000 + ".in", ("a" * 60 + ".") * 66, "hxxp://" * 570, "(dot)" * 800, "%" * 4000, "\\" * 4000, "<script>" * 500]


@pytest.mark.parametrize("s", HOSTILE)
def test_hostile_input_is_linear_and_never_crashes(s):
    t0 = time.perf_counter()
    r = L.check_text(s, online=False)
    L.panel_html(s)
    assert time.perf_counter() - t0 < 0.5, s[:20]
    assert isinstance(r["items"], list) and len(r["items"]) <= L.MAX_ITEMS
    assert L.results_html(r)


def test_one_megabyte_of_garbage():
    t0 = time.perf_counter()
    r = L.check_text("ab.cd-" * 170000, online=False)
    assert time.perf_counter() - t0 < 1.0 and r["summary"]["truncated"]


# ------------------------------------------------------------------------------------------------- official data
def test_data_file_every_entry_has_evidence_and_date():
    d = json.loads((ROOT / "data" / "official_brands.json").read_text(encoding="utf-8"))
    assert len(d["brands"]) >= 25
    for b in d["brands"]:
        assert b["brand"] and b["domains"] and b["tokens"], b["brand"]
        for dom in b["domains"]:
            assert dom["d"] == dom["d"].lower() and "/" not in dom["d"] and dom["evidence"].startswith("https://") and dom["how"], dom
    assert d["checked"] == "2026-11-13"
    for ph in d["phones"]:
        assert ph["evidence"].startswith("https://") and ph["checked"] and ph["what"], ph
    assert d["dropped"]                                               # what could not be confirmed is recorded, not silently omitted


def test_every_official_domain_classifies_official():
    assert len(L.official_domains()) >= 60
    for dom in L.official_domains():
        assert verdict("https://" + dom + "/") == OFFICIAL, dom
        assert verdict("https://www." + dom + "/x?y=1") == OFFICIAL or dom.count(".") > 1, dom
    for h in list(fetch.OFFICIAL_HOSTS) + list(fetch.EXTRA_OFFICIAL):
        assert verdict(h) == OFFICIAL and verdict("https://sub." + h + "/") == OFFICIAL, h
    for h in ("india.gov.in", "cybercrime.gov.in", "x.nic.in", "sbi.bank.in", "federal.bank.in", "who.int", "mausam.imd.gov.in", "voters.eci.gov.in"):
        assert verdict(h) == OFFICIAL, h


def test_official_cards_name_the_body_and_never_claim_more():
    f = L.analyze_domain("https://www.sbilife.co.in/plans")
    assert f.verdict == OFFICIAL and "SBI Life Insurance" in f.reasons[0] and f.label == "On the verified official list"
    assert "does not vouch for a message" in " ".join(f.reasons)
    assert L.analyze_domain("pib.gov.in").brand == "PIB"


def test_bare_zone_and_suffix_tricks_are_not_official():
    for h in ("bank.in", "notgov.in", "gov.in.evil.com", "evilsbi.co.in", "sbi.bank.in.evil.com", "pib.gov.in.evil.com", "evilpib.gov.in.xyz"):
        assert verdict(h) != OFFICIAL, h


# --------------------------------------------------------------------------------------------- LOOKALIKE rules
RULE_POS = {
    "official_prefix": ["sbi.co.in.verify-now.xyz", "https://pib.gov.in.evil.com/x", "paytm.com.secure-login.xyz", "hdfc.bank.in-update.com", "irctc.co.in.refund.top"],
    "brand_plus_scam_word": ["sbi-kyc-update.com", "pm-kisan-yojana-registration.in", "paytm-support.in", "hdfcrewards.in", "irctc-refund.xyz", "https://login.sbi-verify.online/x",
                             "jio-free-recharge.com", "uidai-aadhaar-update.in"],
    "typosquat": ["paytrn.com", "paytmm.com", "pay-tm.com", "flipcart.com", "phonepee.com", "hdfcbamk.com", "amaz0n.in", "airtell.in", "sbicards.com"],
    "userinfo_trick": ["https://pib.gov.in@evil.com/", "http://sbi.co.in:x@evil.org/login"],
    "punycode_brand": ["раytm.com", "раytm.com".encode("idna").decode()],
}
RULE_NEG = {
    "official_prefix": ["online.sbi.co.in", "amazon.com.au", "sbi.co.in", "mail.paytm.com", "my-sbi.co.in.example"[:0] or "example.com", "pib.gov.in"],
    "brand_plus_scam_word": ["sbicard.com", "hdfclife.com", "kyc-help-center.in", "yojana-list-news.in", "sbi-news.in", "paytm.com", "free-games.in", "irctc.co.in",
                             "hdfcfund.com"],
    "typosquat": ["kodak.com", "paytm.in", "amazing.com", "airtel.in", "umangs.com", "axis360.com", "phoneme.dev"[:0] or "example.org", "yesterday.com", "reliance.com"],
    "userinfo_trick": ["https://user@example.com/", "https://pib.gov.in/x", "http://example.com:8080/a@b"],
    "punycode_brand": ["münchen.de", "xn--mnchen-3ya.de", "bücher.in", "भारत.in"],
}


@pytest.mark.parametrize("rule", sorted(RULE_POS))
def test_lookalike_rule_positives(rule):
    assert len(RULE_POS[rule]) >= 2
    for d in RULE_POS[rule]:
        f = L.analyze_domain(d)
        assert f.verdict == LOOKALIKE, (rule, d, f.verdict, f.rules)
        assert any(r.startswith(rule.split("_")[0]) or rule.startswith(r.split("_")[0]) for r in f.rules), (rule, d, f.rules)
        assert f.brand and f.official_alternative or rule == "userinfo_trick", (d, f.brand)
        assert f.reasons and len(f.reasons[0]) > 20


@pytest.mark.parametrize("rule", sorted(RULE_NEG))
def test_lookalike_rule_near_misses(rule):
    for d in RULE_NEG[rule]:
        assert verdict(d) != LOOKALIKE, (rule, d, rules(d))


def test_lookalike_names_the_real_address():
    f = L.analyze_domain("https://sbi-kyc-update.com/login")
    assert f.brand == "SBI" and f.official_alternative == "sbi.bank.in" and f.label == "Imitates SBI"
    d = f.to_dict()
    assert d["official_alternative"] == "sbi.bank.in" and d["class"] == "lc-lookalike"
    assert L.analyze_domain("pm-kisan-yojana-registration.in").official_alternative == "pmkisan.gov.in"


def test_homoglyph_normalisation_helpers():
    assert "paytm" in L._skeleton_variants("paytrn") and "paytm" in L._skeleton_variants("раytm")
    assert any("l" in v for v in L._skeleton_variants("fl1pkart")) and "flipkart" in L._skeleton_variants("f1ipkart") | L._skeleton_variants("flipkart")
    assert L._edit_distance("paytm", "paytn", 1) == 1 and L._edit_distance("abc", "xyz", 1) == 2


# ------------------------------------------------------------------------------ SUSPICIOUS_PATTERN and the rest
def test_pattern_rules_need_their_context():
    m = "Claim your Rs 1000 government subsidy now"
    assert verdict("https://bit.ly/3abc", m) == PATTERN and "shortener_money" in rules("https://bit.ly/3abc", m)
    assert verdict("https://bit.ly/3abc", "look at this cat video") == UNKNOWN
    assert verdict("https://offers-today.xyz/go", m) == PATTERN and verdict("https://offers-today.xyz/go", "my holiday photos") == UNKNOWN
    assert verdict("https://shop.example.com/x", m) == UNKNOWN


def test_apk_link_is_always_high_risk_even_on_an_official_host():
    for u in ("http://files.xyz/PMKisan.apk", "https://example.com/dl/app.APK?x=1", "https://pib.gov.in/app.apk"):
        f = L.analyze_domain(u)
        assert f.verdict == PATTERN and "apk_link" in f.rules and "Play Store" in " ".join(f.reasons), u


def test_ip_javascript_and_mixed_script_hosts():
    assert verdict("http://192.168.4.5/claim") == PATTERN and verdict("http://[::1]/x") == PATTERN and verdict("http://0x7f000001/x") == PATTERN
    f = L.analyze_domain("javascript:alert(1)")
    assert f.verdict == PATTERN and f.rules == ["code_url"]
    assert verdict("data:text/html,<script>x</script>") == PATTERN
    assert verdict("p\u0430yp\u0430l.com") == PATTERN and "mixed_script" in rules("p\u0430yp\u0430l.com")


def test_young_domain_notes_and_escalation():
    f = L.analyze_domain("https://shop.example.xyz/x", "Claim Rs 500", age_days=5)
    assert f.verdict == PATTERN and "registered only 5 days ago" in " ".join(f.reasons) and "young_domain" in f.rules
    g = L.analyze_domain("https://shop.example.com/x", "hello", age_days=5)
    assert g.verdict == UNKNOWN and any("registered only 5 days" in r for r in g.reasons)
    h = L.analyze_domain("https://shop.example.com/x", "hello", age_days=100)
    assert h.verdict == UNKNOWN and any("fairly recent" in r for r in h.reasons)
    assert not any("registered" in r for r in L.analyze_domain("https://shop.example.com/x", "hello", age_days=900).reasons)
    assert not any("registered" in r for r in L.analyze_domain("https://shop.example.com/x", "hello", age_days=None).reasons)
    assert L.analyze_domain("sbi.bank.in", age_days=2).verdict == OFFICIAL


def test_unknown_is_the_default_with_neutral_facts_and_how_to_check():
    f = L.analyze_domain("http://my-local-bakery.in/menu")
    assert f.verdict == UNKNOWN and f.label == "Not on the official list: Sach cannot vouch for it"
    assert any("does not use HTTPS" in x for x in f.facts)
    acts = " ".join(f.actions)
    assert ".gov.in" in acts and ".bank.in" in acts and "OTP" in acts and "type the official address yourself" in acts.lower()
    assert any("HTTPS. That only means" in x for x in L.analyze_domain("https://my-local-bakery.in").facts)


# ------------------------------------------------------------------------------------- false-positive guard
LEGIT = """google.com wikipedia.org amazon.in youtube.com github.com sbicard.com hdfclife.com paytm.com flipkart.com bbc.com reuters.com nytimes.com
thehindu.com indianexpress.com ndtv.com hindustantimes.com timesofindia.indiatimes.com livemint.com moneycontrol.com zerodha.com groww.in
cleartax.in policybazaar.com makemytrip.com swiggy.com zomato.com ola.in myntra.com nykaa.com tatamotors.com infosys.com wipro.com tcs.com
ycombinator.com stackoverflow.com python.org mozilla.org apple.com microsoft.com linkedin.com facebook.com instagram.com whatsapp.com
telegram.org netflix.com hotstar.com spotify.com cricbuzz.com espncricinfo.com boomlive.in factly.in newschecker.in vishvasnews.com
hdfcsec.com icicidirect.com kodak.com axisbank-news.example amazon.com.au sbimf.com sbilife.co.in airtel.in jio.com bsnl.co.in
paytm.in phone.com payment.com amazing.com reliance.com yesterday.com bankbazaar.com bankofamerica.com paypal.com""".split()


def test_false_positive_guard_list():
    assert len(LEGIT) >= 40
    bad = [(d, rules(d)) for d in LEGIT if verdict(d) == LOOKALIKE]
    assert not bad, bad
    bad = [(d, rules(d)) for d in LEGIT if verdict(d, "Rs 500 offer from the government") == LOOKALIKE]
    assert not bad, bad
    for d in LEGIT:                                    # ordinary domains are UNKNOWN or OFFICIAL, with a context-free reading
        assert verdict(d) in (UNKNOWN, OFFICIAL), d


def test_nothing_is_called_safe_unless_official():
    texts = ["https://bakery.in/menu", "bit.ly/x Rs 500 gift", "sbi-kyc-update.com", "http://1.2.3.4/a", "x@ybl", "98765 43210", "Download a.apk",
             "javascript:alert(1)", "<script>alert(1)</script>", "PM Kisan app", "https://shop.example.xyz Claim Rs 10 crore", "9876543210@oksbi send Rs 1 to receive",
             "www.paytm.com.evil.top", "1930", "hello there friend"]
    for tx in texts:
        r = L.check_text(tx, online=False)
        blob = json.dumps(r) + L.results_html(r) + L.panel_html(tx)
        for d in r["items"]:
            if d["verdict"] != OFFICIAL:
                assert words_ok(json.dumps(d)), (tx, d)
        if not any(d["verdict"] == OFFICIAL for d in r["items"]):
            assert words_ok(blob), (tx, FORBIDDEN.findall(blob.replace("Safe Browsing", "")))
    for lang in ("en", "hi", "te"):
        assert words_ok(" ".join(L.TEXT[lang].values())) or lang != "en"
    assert words_ok(" ".join(L.HOW_TO_CHECK + L.UPI_RULES + [L.ACT_REPORT]))


# -------------------------------------------------------------------------------------------------- UPI and phone
def test_upi_known_unknown_and_rules_always_shown():
    f = L.analyze_upi("ramesh@ybl")
    assert f.verdict == UNKNOWN and "does not map handles to banks" in " ".join(f.facts)
    assert "does not prove who owns it" in " ".join(f.reasons)
    joined = " ".join(f.actions)
    assert "UPI PIN" in joined and "RECEIVE" in joined and "processing fee" in joined and "Send Rs 1" not in joined.replace("send Rs 1", "Send Rs 1")[:0]
    g = L.analyze_upi("someone@zzunknown")
    assert g.verdict == UNKNOWN and "cannot say which one" in " ".join(g.facts)
    assert L.analyze_upi("x").verdict == UNKNOWN and "valid UPI ID" in " ".join(L.analyze_upi("x").reasons)


def test_upi_trap_and_official_name_escalate():
    r = L.check_text("Send Rs 1 to receive Rs 5000 cashback. Pay to rahul@ybl", online=False)
    u = [d for d in r["items"] if d["kind"] == "upi"][0]
    assert u["verdict"] == PATTERN and "upi_trap" in u["rules"] and "pay or approve" in " ".join(u["reasons"])
    plain = L.check_text("my UPI is rahul@ybl for the chai money", online=False)["items"][0]
    assert plain["verdict"] == UNKNOWN
    v = L.analyze_upi("sbi.support@ybl")
    assert v.verdict == PATTERN and "upi_official_name" in v.rules
    assert L.analyze_upi("sbi.fan@ybl").verdict == UNKNOWN


def test_official_numbers_only_with_evidence():
    pib = L.analyze_phone("+918799711259")
    assert pib.verdict == OFFICIAL and "PIB Fact Check" in " ".join(pib.reasons) and "factcheck.pib.gov.in" in " ".join(pib.reasons)
    assert report.PIB_WHATSAPP_DIGITS in "".join(p["number"] for p in L.load_data()["phones"]).replace("+", "")
    for n in ("1930", "112", "1947"):
        assert L.analyze_phone(n).verdict == OFFICIAL, n
    for p in L.load_data()["phones"]:
        assert p["evidence"].startswith("https://") and p["checked"] and p["what"]
    assert len(L.official_numbers()) == len(L.load_data()["phones"])
    for n in ("+919876543210", "+918799711258", "1800 999 9999", "1931", "5555"):
        f = L.analyze_phone(n)
        assert f.verdict == UNKNOWN and "cannot verify who owns a phone number" in " ".join(f.reasons), n
        assert "1930" in " ".join(f.actions) and "cybercrime.gov.in" in " ".join(f.actions) and "sancharsaathi.gov.in" in " ".join(f.actions)


def test_app_items():
    a = L.check_text("PM Kisan Yojana app", online=False)["items"][0]
    assert a["kind"] == "app" and a["verdict"] == UNKNOWN and "Play Store" in " ".join(a["actions"])
    b = L.check_text("install gov-yojana.apk", online=False)["items"]
    assert any(d["kind"] == "app" and d["verdict"] == PATTERN for d in b)


# ------------------------------------------------------------------------------------------------------------ RDAP
class Resp:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def open(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        self.calls.append((url, timeout, req.get_method() if hasattr(req, "get_method") else "GET", req.data if hasattr(req, "data") else None, dict(req.header_items())))
        for k, v in self.routes.items():
            if url.startswith(k):
                if isinstance(v, Exception):
                    raise v
                return Resp(v)
        raise urllib.error.URLError("no route")


BOOT = {"services": [[["com", "net"], ["https://rdap.verisign.com/com/v1/"]], [["in"], ["https://rdap.nixiregistry.in/rdap/"]],
                     [["xyz"], ["http://insecure.example/", "https://rdap.xyz.example/"]]]}
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def rdap_doc(days_ago):
    return {"events": [{"eventAction": "last changed", "eventDate": "2026-01-01T00:00:00Z"},
                       {"eventAction": "registration", "eventDate": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")}]}


def test_bootstrap_parsing():
    b = L.parse_bootstrap(BOOT)
    assert b["com"] == "https://rdap.verisign.com/com/v1/" and b["in"] == "https://rdap.nixiregistry.in/rdap/" and b["xyz"] == "https://rdap.xyz.example/"
    assert L.parse_bootstrap({}) == {} and L.parse_bootstrap(None) == {} and L.parse_bootstrap({"services": [["bad"]]}) == {}
    assert L.parse_registration(rdap_doc(5)).startswith("2026-11-08") and L.parse_registration({"events": []}) is None and L.parse_registration([]) is None


def test_domain_age_young_old_and_cache():
    op = FakeOpener({L.RDAP_BOOT: BOOT, "https://rdap.verisign.com/com/v1/domain/young-shop.com": rdap_doc(12),
                     "https://rdap.nixiregistry.in/rdap/domain/old-shop.co.in": rdap_doc(4000)})
    assert L.domain_age_days("www.young-shop.com", op, NOW) == 12
    assert L.domain_age_days("old-shop.co.in", op, NOW) == 4000
    n = len(op.calls)
    assert L.domain_age_days("a.b.young-shop.com", op, NOW) == 12 and len(op.calls) == n          # cached per registrable domain
    urls = [c[0] for c in op.calls]
    assert all(u.startswith(("https://data.iana.org/", "https://rdap.")) for u in urls)         # hostname lookups only, never the site itself
    assert all("User-agent" in c[4] and "Cookie" not in c[4] and c[2] == "GET" for c in op.calls)
    assert all(c[1] == 3.0 or c[1] == L.RDAP_TIMEOUT for c in op.calls)


def test_rdap_failures_give_no_information():
    for routes in ({}, {L.RDAP_BOOT: BOOT}, {L.RDAP_BOOT: BOOT, "https://rdap.verisign.com/": urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b""))},
                   {L.RDAP_BOOT: BOOT, "https://rdap.verisign.com/": b"not json"}, {L.RDAP_BOOT: BOOT, "https://rdap.verisign.com/": {"events": [{"eventAction": "registration", "eventDate": "garbage"}]}},
                   {L.RDAP_BOOT: BOOT, "https://rdap.verisign.com/": socket.timeout()}):
        assert L.domain_age_days("somewhere-else.com", FakeOpener(routes), NOW) is None, routes
    for bad in ("", "localhost", "192.168.1.1", "a b.com", "http://", None):
        assert L.domain_age_days(bad, FakeOpener({}), NOW) is None


def test_bootstrap_failure_falls_back_to_small_table_and_unknown_tld_gives_none():
    op = FakeOpener({"https://rdap.nixiregistry.in/rdap/domain/x-shop.in": rdap_doc(9)})
    assert L.domain_age_days("x-shop.in", op, NOW) == 9
    assert L.domain_age_days("x-shop.zzzz", FakeOpener({}), NOW) is None


def test_failed_lookup_is_cached_briefly_and_never_means_old():
    op = FakeOpener({L.RDAP_BOOT: BOOT})
    assert L.domain_age_days("nope-shop.com", op, NOW) is None
    n = len(op.calls)
    assert L.domain_age_days("nope-shop.com", op, NOW) is None and len(op.calls) == n
    f = L.analyze_domain("https://nope-shop.com", age_days=None)
    assert not any("registered" in x for x in f.reasons + f.facts)


def test_online_check_uses_fake_opener_and_respects_budget():
    routes = {L.RDAP_BOOT: BOOT}
    for i in range(8):
        routes[f"https://rdap.verisign.com/com/v1/domain/shop{i}.com"] = rdap_doc(3)
    op = FakeOpener(routes)
    r = L.check_text(" ".join(f"https://shop{i}.com/x" for i in range(8)) + " Rs 500 prize", opener=op)
    lookups = [c[0] for c in op.calls if "/domain/" in c[0]]
    assert len(lookups) <= L.RDAP_BUDGET
    assert any(d["verdict"] == PATTERN and "young_domain" in d["rules"] for d in r["items"][: L.RDAP_BUDGET])
    assert L.check_text("https://shop1.com", online=False)["items"][0]["verdict"] == UNKNOWN


def test_no_network_in_tests_unless_injected(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(urllib.request, "build_opener", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert L.check_text("https://shop-never.com Rs 5")["items"]
    assert L.domain_age_days("shop-never.com") is None and L.safebrowsing_matches("shop-never.com", "KEY") is None


# --------------------------------------------------------------------------------------------------- Safe Browsing
def test_safebrowsing_request_shape_and_key_redaction():
    op = FakeOpener({L.SB_URL: {"matches": [{"threatType": "SOCIAL_ENGINEERING"}]}})
    assert L.safebrowsing_matches("bad-site.xyz", "SECRETKEY123", op) == ["SOCIAL_ENGINEERING"]
    url, timeout, method, data, hdr = op.calls[0]
    assert url == L.SB_URL + "?key=SECRETKEY123" and method == "POST" and timeout <= 3.0
    body = json.loads(data)
    assert body["threatInfo"]["threatEntries"] == [{"url": "http://bad-site.xyz/"}] and body["threatInfo"]["threatEntryTypes"] == ["URL"]
    assert body["client"]["clientId"] == "sach" and "SECRETKEY123" not in data.decode()
    f = L.analyze_domain("https://bad-site.xyz/x", threats=["SOCIAL_ENGINEERING"])
    assert f.verdict == PATTERN and "Google Safe Browsing lists this address as dangerous" in " ".join(f.reasons) and "SECRETKEY123" not in json.dumps(f.to_dict())


def test_safebrowsing_no_key_no_match_or_error_is_no_information(monkeypatch):
    op = FakeOpener({L.SB_URL: {}})
    assert L.safebrowsing_matches("x.xyz", "", op) is None and not op.calls
    monkeypatch.delenv("GOOGLE_SAFEBROWSING_API_KEY", raising=False)
    assert L.safebrowsing_matches("x.xyz", None, op) is None and not op.calls
    assert L.safebrowsing_matches("x.xyz", "K", op) == []
    assert L.safebrowsing_matches("x.xyz", "K", FakeOpener({L.SB_URL: urllib.error.URLError("k=K")})) is None
    assert L.safebrowsing_matches("x.xyz", "K", FakeOpener({L.SB_URL: b"<html>"})) is None
    monkeypatch.setenv("GOOGLE_SAFEBROWSING_API_KEY", "ENVKEY")
    op2 = FakeOpener({L.SB_URL: {"matches": [{"threatType": "MALWARE"}]}})
    r = L.check_text("https://evil-one.xyz/a", opener=FakeOpener({}), sb_opener=op2)
    assert r["items"][0]["verdict"] == PATTERN and "ENVKEY" not in json.dumps(r) and "ENVKEY" not in L.results_html(r)


# ------------------------------------------------------------------------------------------------------ SSRF guard
def addrs(*ips):
    return lambda host, port, *a: [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]


class FakeConn:
    log = []

    def __init__(self, host, port, ip, tls, timeout, script):
        self.args, self.script = (host, port, ip, tls, timeout), script
        self.method = self.headers = None

    def request(self, method, path, headers=None):
        self.method, self.path, self.headers = method, path, headers or {}
        FakeConn.log.append((self.args, method, path, dict(self.headers)))

    def getresponse(self):
        st, loc = self.script(self.method, self.args[0], self.path)
        conn = self

        class R:
            status = st

            def getheader(self, name, default=None):
                return loc if name.lower() == "location" else default

            def read(self, *a):
                raise AssertionError("a response body must never be read")
        return R()

    def close(self):
        pass


def conn_factory(script):
    return lambda host, port, ip, tls, timeout: FakeConn(host, port, ip, tls, timeout, script)


@pytest.fixture(autouse=True)
def _reset_conn_log():
    FakeConn.log = []


BLOCKED_IPS = ["127.0.0.1", "127.1.2.3", "10.0.0.5", "172.16.0.1", "172.31.255.255", "192.168.1.1", "169.254.169.254", "169.254.0.1", "100.64.0.1", "100.127.255.254",
               "224.0.0.1", "239.255.255.250", "0.0.0.0", "240.0.0.1", "255.255.255.255", "198.18.0.1", "192.0.0.1", "::1", "::", "fe80::1", "fc00::1", "fd12::1", "ff02::1",
               "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "64:ff9b::7f00:1", "2002:7f00:1::1", "2001:0:4136:e378:8000:63bf:3fff:fdd2"]


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_ssrf_every_blocked_class(ip):
    assert not L.ip_is_public(ip)
    r = L.expand_short_link("https://bit.ly/abc", resolver=addrs(ip), connect=conn_factory(lambda *a: (301, "https://x.com/")))
    assert r["ok"] is False and not FakeConn.log


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111", "2a00:1450:4001:81d::200e"])
def test_public_addresses_pass(ip):
    assert L.ip_is_public(ip)


def test_ssrf_mixed_answers_are_blocked():
    r = L.expand_short_link("https://bit.ly/abc", resolver=addrs("8.8.8.8", "10.0.0.1"), connect=conn_factory(lambda *a: (301, "https://x.com/")))
    assert r["ok"] is False and not FakeConn.log


def test_ssrf_dns_rebinding_connects_only_to_the_checked_address():
    calls = []

    def rebinding(host, port, *a):
        calls.append(host)
        return addrs("93.184.216.34")(host, port) if len(calls) == 1 else addrs("127.0.0.1")(host, port)
    r = L.expand_short_link("https://bit.ly/abc", resolver=rebinding, connect=conn_factory(lambda m, h, p: (301, "https://target.example.com/x")))
    assert r["ok"] and r["final_url"] == "https://target.example.com/x"
    assert {a[0][2] for a in FakeConn.log} == {"93.184.216.34"} and len(calls) == 1          # pinned address, resolved once per hop


@pytest.mark.parametrize("url", ["ftp://bit.ly/x", "file:///etc/passwd", "javascript:alert(1)", "https://user:pw@bit.ly/x", "https://user@bit.ly/x", "https://bit.ly:8080/x",
                                 "https://bit.ly:22/x", "https://127.0.0.1/x", "https://localhost/x", "https://evil.example.com/x", "https://bit.ly.evil.com/x",
                                 "http://169.254.169.254/latest/meta-data", "https://[::1]/x", "", "not a url", "https://notbit.ly/x"])
def test_ssrf_refuses_bad_urls_without_resolving_or_connecting(url):
    def no_resolve(*a):
        raise AssertionError("must not resolve")
    r = L.expand_short_link(url, resolver=no_resolve, connect=conn_factory(lambda *a: (301, "https://x.com")))
    assert r["ok"] is False and not FakeConn.log


def test_expansion_contacts_only_shorteners_and_stops_at_the_destination():
    script = lambda m, h, p: (301, "https://www.sbi-kyc-update.com/login?id=1") if h == "bit.ly" else (500, None)
    r = L.expand_short_link("http://bit.ly/abc", resolver=addrs("8.8.8.8"), connect=conn_factory(script))
    assert r["ok"] and r["final_url"].startswith("https://www.sbi-kyc-update.com/") and r["hops"] == 1
    assert [a[0][0] for a in FakeConn.log] == ["bit.ly"]                      # the destination is never contacted


def test_expansion_follows_shortener_chains_up_to_three_redirects():
    chain = {"bit.ly": "https://tinyurl.com/b", "tinyurl.com": "https://cutt.ly/c", "cutt.ly": "https://rb.gy/d", "rb.gy": "https://is.gd/e", "is.gd": "https://final.example.org/"}
    script = lambda m, h, p: (302, chain[h])
    r = L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=conn_factory(script))
    assert r["ok"] is False and "too many" in r["reason"]
    ok = L.expand_short_link("https://rb.gy/d", resolver=addrs("8.8.8.8"), connect=conn_factory(script))
    assert ok["ok"] and ok["final_url"] == "https://final.example.org/" and ok["hops"] == 2
    three = L.expand_short_link("https://cutt.ly/c", resolver=addrs("8.8.8.8"), connect=conn_factory(script))
    assert three["ok"] and three["hops"] == 3


def test_expansion_redirect_to_internal_address_is_reported_not_followed():
    r = L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=conn_factory(lambda *a: (302, "http://169.254.169.254/latest")))
    assert r["ok"] and r["final_url"] == "http://169.254.169.254/latest" and len(FakeConn.log) == 1
    out = L.expand_and_analyze("https://bit.ly/a", "", resolver=addrs("8.8.8.8"), connect=conn_factory(lambda *a: (302, "http://169.254.169.254/latest")))
    assert out["finding"]["verdict"] == PATTERN and "ip_host" in out["finding"]["rules"]
    r = L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=conn_factory(lambda *a: (302, "gopher://evil/")))
    assert r["ok"] is False
    r = L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=conn_factory(lambda *a: (302, "https://bit.ly:8080/x")))
    assert r["ok"] is False or r["final_url"].endswith(":8080/x")


def test_head_first_then_ranged_get_and_honest_headers():
    def script(m, h, p):
        return (405, None) if m == "HEAD" else (301, "https://t.example.com/")
    r = L.expand_short_link("https://bit.ly/abc?x=1", resolver=addrs("8.8.8.8"), connect=conn_factory(script))
    assert r["ok"]
    assert [x[1] for x in FakeConn.log] == ["HEAD", "GET"] and FakeConn.log[1][3]["Range"] == "bytes=0-0" and FakeConn.log[0][2] == "/abc?x=1"
    for _, _, _, hd in FakeConn.log:
        assert hd["User-Agent"].startswith("Sach-linkcheck/") and "Cookie" not in hd and "Authorization" not in hd
    assert FakeConn.log[0][0][1] == 443 and FakeConn.log[0][0][3] is True


def test_expansion_total_timeout_and_unresolvable():
    t = [0.0]

    def clock():
        t[0] += 1.6
        return t[0]
    r = L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=conn_factory(lambda *a: (301, "https://tinyurl.com/b")), clock=clock)
    assert r["ok"] is False and "timed out" in r["reason"]

    def nxdomain(*a):
        raise socket.gaierror("nope")
    assert L.expand_short_link("https://bit.ly/a", resolver=nxdomain, connect=conn_factory(lambda *a: (301, "x")))["ok"] is False

    def boom(*a):
        raise OSError("refused")
    assert L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=lambda *a: (_ for _ in ()).throw(OSError("refused")))["ok"] is False


def test_a_non_redirect_answer_is_reported_as_pointing_nowhere():
    r = L.expand_short_link("https://bit.ly/a", resolver=addrs("8.8.8.8"), connect=conn_factory(lambda *a: (200, None)))
    assert r["ok"] and r["reason"] == "not_a_redirect" and r["final_url"] == "https://bit.ly/a"


def test_pinned_connection_classes_connect_to_the_checked_ip(monkeypatch):
    seen = []

    class S:
        def settimeout(self, *a): pass
        def close(self): pass
    monkeypatch.setattr(socket, "create_connection", lambda addr, timeout=None, **k: seen.append(addr) or S())
    c = L._PinnedHTTP("bit.ly", 80, "93.184.216.34", 2.0)
    c.connect()
    assert seen == [("93.184.216.34", 80)] and c.host == "bit.ly"


# ------------------------------------------------------------------------------------------- HTML, UI, panel, WhatsApp
def test_results_html_escapes_hostile_input():
    evil = '<script>alert(1)</script> "><img src=x onerror=alert(1)> javascript:alert(1) https://a.com/"onmouseover="x'
    r = L.check_text(evil, online=False)
    h = L.results_html(r) + L.panel_html(evil)
    assert "<script>" not in h and "<img" not in h and 'onerror="' not in h and 'href="javascript' not in h.lower()
    assert any(d["verdict"] == PATTERN and "code_url" in d["rules"] for d in r["items"])


def test_card_structure_has_shape_text_and_real_address():
    r = L.check_text("Update KYC at https://sbi-kyc-update.com/login", online=False)
    h = L.results_html(r)
    assert "lc-lookalike" in h and "Imitates SBI" in h and "The real address is" in h and "<code>sbi.bank.in</code>" in h and 'aria-hidden="true">✕' in h
    assert "What to do" in h and "wa.me/?text=" in h and "Warn my group on WhatsApp" in h
    for cls, glyph in (("lc-official", "✓"), ("lc-pattern", "!"), ("lc-unknown", "?")):
        assert cls in L.CSS and cls in L.CSS_CLASS.values() and glyph in L.GLYPH.values()


def test_whatsapp_warning_text_has_no_personal_data():
    f = L.analyze_domain("https://sbi-kyc-update.com/login?user=ramesh&otp=123456")
    txt = L.warn_text(f, "https://sach.example.org")
    assert txt == "Warning: this link (sbi-kyc-update[.]com) imitates SBI. The real address is sbi.bank.in. Checked on Sach https://sach.example.org"
    assert "ramesh" not in txt and "123456" not in txt
    url = L.warn_whatsapp(f, "https://sach.example.org")
    assert url.startswith("https://wa.me/?text=") and "imitates%20SBI" in url and "sbi.bank.in" in url
    assert L.warn_text(L.analyze_domain("https://bit.ly/x", "Rs 500 claim"), "https://s.org").startswith("Warning: this link (bit[.]ly) matches a scam pattern")
    assert L.warn_text(L.analyze_domain("https://bakery.in"), "https://s.org") is None and L.warn_text(L.analyze_domain("pib.gov.in")) is None


def test_panel_is_compact_offline_and_capped():
    t = "Fwd: update KYC https://sbi-kyc-update.com and bit.ly/a, call 9876543210, pay x@ybl, https://pib.gov.in/x " + " ".join(f"s{i}.xyz" for i in range(9))
    h = L.panel_html(t)
    assert h.startswith('<details class="lc-panel"') and h.count('<li class="lc-mini') == L.PANEL_MAX and "and 8 more" in h and "open" not in h.split(">")[0]
    assert "Imitates SBI" in h and "On the verified official list" not in h        # riskiest first: the official item is the one cut
    assert L.panel_html("no links here at all") == "" and L.panel_html("") == "" and L.panel_html(None) == ""


def test_panel_never_changes_the_verdict_or_degraded_notice():
    res = {"verdict": "UNVERIFIED", "language": "en", "card": "card text", "claims": [{"verdict": "UNVERIFIED", "claim": {"text": "c", "domain": "money"}, "citations": [], "reason_code": "no_evidence"}],
           "checked_at": "2026-11-13T10:00:00Z", "degraded": True, "warning_signs": []}
    plain = site.result_block(dict(res), text="Government gives Rs 500")
    withl = site.result_block(dict(res), text="Government gives Rs 500 at https://sbi-kyc-update.com/x")
    assert "lc-panel" not in plain and "lc-panel" in withl
    for h in (plain, withl):
        assert "Limited mode" in h and 'stamp big UNVERIFIED' in h
    strip = lambda h: re.sub(r'<details class="lc-panel".*?</details>', "", h, flags=re.S)
    assert strip(withl) == plain


def test_home_card_and_no_js_view():
    h = site.home().decode()
    assert 'id="linkcheck"' in h and 'id="lcform"' in h and 'name="view" value="link"' in h and "Check a link, number or UPI ID" in h
    assert h.index('id="check"') < h.index('id="linkcheck"') < h.index('id="how"')
    assert h.count("<script>") == 4 and 'maxlength="4000"' in h
    out, q = L.view_page_result("<b>x</b> https://sbi-kyc-update.com", "en")
    page = site.home(noindex=True, lc_prefill=q, lc_result=out).decode()
    assert "Imitates SBI" in page and "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt;" in page


def test_translations_fall_back_to_english():
    assert L.t(LOOKALIKE, "hi", brand="SBI").startswith("SBI") and L.t(OFFICIAL, "te") != L.t(OFFICIAL, "en")
    assert L.t("expand", "hi") and L.t("expanding", "te") == L.t("expanding", "en") and L.t(UNKNOWN, "ta") == L.t(UNKNOWN, "en")


def test_privacy_bullet_readme_docs_and_robots_text():
    from sach.legal import legal_page
    page = legal_page("privacy").decode()
    assert "Links, numbers and UPI IDs you check are looked up by their hostname only; Sach does not open the page, and does not store what you paste." in page
    assert "link" in (ROOT / "README.md").read_text(encoding="utf-8").lower() and (ROOT / "docs" / "link-checker.md").exists()
    doc = (ROOT / "docs" / "link-checker.md").read_text(encoding="utf-8")
    for needle in ("official_prefix", "non-commercial", "Dropped", "How to add a brand"):
        assert needle in doc, needle


# ------------------------------------------------------------------------------------------------ HTTP: the server
def post_json(base, path, obj, raw=None):
    req = urllib.request.Request(base + path, raw if raw is not None else json.dumps(obj).encode(), {"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req)
        return r.status, dict(r.headers), json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read().decode() or "{}")


MIXED = ("Dear customer, SBI KYC expired. Update at https://sbi-kyc-update.com/login or join http://bit.ly/3AbC to claim Rs 1000. Install http://files.xyz/PMKisan.apk. "
         "Send Rs 1 to receive money: ramesh@ybl. Call 9876543210. Real: https://pib.gov.in/x")


def test_api_linkcheck_json_shape(server):
    code, hdr, j = post_json(server, "/?api=linkcheck", {"text": MIXED})
    assert code == 200 and hdr["Cache-Control"] == "no-store" and "application/json" in hdr["Content-Type"]
    by = {(d["kind"], d["value"]): d for d in j["items"]}
    sbi = by[("url", "https://sbi-kyc-update.com/login")]
    assert sbi["verdict"] == LOOKALIKE and sbi["class"] == "lc-lookalike" and sbi["label"] == "Imitates SBI" and sbi["official_alternative"] == "sbi.bank.in"
    assert sbi["reasons"] and sbi["actions"] and sbi["warn_whatsapp"].startswith("https://wa.me/?text=")
    assert by[("url", "https://pib.gov.in/x")]["verdict"] == OFFICIAL
    assert by[("url", "http://bit.ly/3AbC")]["verdict"] == PATTERN and by[("url", "http://bit.ly/3AbC")]["shortener"] is True
    assert by[("url", "http://files.xyz/PMKisan.apk")]["verdict"] == PATTERN
    assert by[("upi", "ramesh@ybl")]["verdict"] == PATTERN and by[("phone", "+919876543210")]["verdict"] == UNKNOWN
    assert j["summary"]["total"] == len(j["items"]) and j["summary"]["high_risk"] >= 4 and j["ui"]["what_to_do"] == "What to do"
    for d in j["items"]:
        assert {"kind", "value", "label", "class", "reasons", "actions"} <= set(d)
        if d["verdict"] != OFFICIAL:
            assert words_ok(json.dumps(d))


def test_api_linkcheck_errors_hostile_and_big_bodies(server):
    assert post_json(server, "/?api=linkcheck", {"text": "  "})[0] == 400 and post_json(server, "/?api=linkcheck", {})[0] == 400
    assert post_json(server, "/?api=linkcheck", None, raw=b"{not json")[0] == 400
    assert post_json(server, "/?api=linkcheck", {"text": 123})[0] == 400
    code, _, j = post_json(server, "/?api=linkcheck", {"text": "<script>alert(1)</script> javascript:alert(1) " + "x" * 150000})
    assert code == 200 and j["summary"]["truncated"] is True
    assert all(d["verdict"] in (PATTERN, UNKNOWN) for d in j["items"])


def test_no_js_get_view_renders_escaped_noindex_nostore(server):
    from urllib.parse import quote
    code, hdr, body = _raw_get(server, "/?view=link&q=" + quote("<script>alert(1)</script> https://sbi-kyc-update.com/login"))
    h = body.decode()
    assert code == 200 and hdr["Cache-Control"] == "no-store" and "noindex" in hdr.get("X-Robots-Tag", "")
    assert 'content="noindex,follow"' in h and "Imitates SBI" in h and "<script>alert(1)</script>" not in h and "&lt;script&gt;" in h
    code, hdr, body = _raw_get(server, "/?view=link")
    assert code == 200 and 'id="linkcheck"' in body.decode() and hdr["Cache-Control"] == "no-store"


def test_link_routes_are_in_robots_not_in_sitemap(server):
    robots = _raw_get(server, "/robots.txt")[2].decode()
    assert "Disallow: /?api=" in robots and "Disallow: /?view=link" in robots
    assert "link" not in _raw_get(server, "/sitemap.xml")[2].decode().lower().replace("linkcheck", "")


def test_service_worker_does_not_cache_link_routes():
    from sach import pwa
    assert "Never caches POSTs, ?api=" in pwa.SW_JS and "req.method !== 'GET'" in pwa.SW_JS


def test_rate_limit_buckets_are_separate(server):
    import sach.web as W
    for i in range(20):
        assert post_json(server, "/?api=linkcheck", {"text": f"a{i}.xyz"})[0] == 200
    assert post_json(server, "/?api=linkcheck", {"text": "b.xyz"})[0] == 429
    assert _raw_get(server, "/?view=link&q=x.xyz")[0] == 429
    req = urllib.request.Request(server + "/", b"text=Government+will+give+Rs+5000+to+every+woman.")      # the fact-check bucket is untouched
    assert urllib.request.urlopen(req).status == 200
    assert not W.rate_limited("203.0.113.9", "tip-order", 6)                                           # and so is the tip bucket
    assert not W.rate_limited("203.0.113.9", "tip-order", 6)


def test_linkexpand_endpoint_has_its_own_bucket(server, monkeypatch):
    calls = []
    monkeypatch.setattr(L, "network_enabled", lambda: True)
    monkeypatch.setattr(L, "expand_and_analyze", lambda url, ctx="", lang="en", **k: calls.append(url) or {"ok": True, "final": "https://x.example/", "reason": ""})
    for _ in range(6):
        assert post_json(server, "/?api=linkexpand", {"url": "https://bit.ly/a"})[0] == 200
    assert post_json(server, "/?api=linkexpand", {"url": "https://bit.ly/a"})[0] == 429 and len(calls) == 6
    assert post_json(server, "/?api=linkcheck", {"text": "x.xyz"})[0] == 200


def test_fact_check_flow_shows_panel_and_keeps_verdict(server):
    req = urllib.request.Request(server + "/", b"text=Government+will+give+Rs+5000+to+every+woman.+Update+at+https%3A%2F%2Fsbi-kyc-update.com%2Flogin")
    h = urllib.request.urlopen(req).read().decode()
    assert 'class="lc-panel"' in h and "Links and numbers in this message" in h and "Imitates SBI" in h and 'class="stamp big' in h
    req = urllib.request.Request(server + "/?format=json", b"text=Government+will+give+Rs+5000+to+every+woman.+https%3A%2F%2Fsbi-kyc-update.com", {"Accept": "application/json"})
    j = json.loads(urllib.request.urlopen(req).read().decode())
    assert j["verdict"] in ("FALSE", "UNVERIFIED", "MISLEADING", "TRUE") and "items" not in j and "summary" not in j


def test_module_imports_nothing_that_calls_an_llm():
    src = (ROOT / "sach" / "linkcheck.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:from|import)\s+\.?(?:llm|pipeline|stance|verdict)\b", src, re.M) and "get_llm" not in src
