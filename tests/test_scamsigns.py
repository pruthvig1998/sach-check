"""Warning signs: deterministic scam-pattern hints. Advice only, never part of the verdict."""
import json, os, pathlib, threading, time, urllib.parse, urllib.request
import pytest
from sach.scamsigns import analyze, signs_html, MAX_SHOWN
from sach import site, store
from sach.models import Evidence, TIER_PIB

ROOT = pathlib.Path(__file__).resolve().parents[1]


def ids(t):
    return {s["id"] for s in analyze(t)}


def ev_of(t, sid):
    return next(s for s in analyze(t) if s["id"] == sid)["evidence"]


POS = {
    "asks_secret": ["Share your OTP to get the refund now", "अपना ओटीपी बताएं और इनाम पाएं", "మీ ఓటీపీ చెప్పండి వెంటనే",
                    "OTP bhejo warna kaam nahi hoga", "Install AnyDesk and tell us the code", "Please send your CVV and card number"],
    "upi_trap": ["Send Rs 1 to receive Rs 5000 in your account", "Enter your UPI PIN to receive the money", "Please approve the collect request to get cashback",
                 "Pay Rs 99 processing fee to release your prize", "₹1 भेजें और पैसे पाने के लिए तैयार रहें", "Rs 1 bhejo paise paane ke liye"],
    "claim_prize": ["Congratulations! You have won a lottery of Rs 25 lakh", "Free recharge for everyone this month", "मुफ्त रिचार्ज पाएं आज ही",
                    "మీరు గెలిచారు ఒక లాటరీ", "Aap ne jeeta hai iPhone", "Rs 5000 will be credited to your account if you register now"],
    "click_register": ["Click the link to register for the scheme", "Register using this link before the seats finish", "लिंक पर क्लिक करें और रजिस्टर करें",
                       "లింక్ క్లిక్ చేయండి", "link pe click karo aur apply karo", "Limited seats, hurry"],
    "urgency_threat": ["Last date is today for KYC", "Your SBI account will be blocked within 24 hours", "आखिरी तारीख आज है",
                       "మీ ఖాతా బ్లాక్ అవుతుంది, చివరి తేదీ ఈరోజు", "account block ho jayega aaj", "KYC expired, update immediately",
                       "Legal action will be taken against you"],
    "forward_chain": ["Forward this to 10 people", "Share with all your groups", "सबको शेयर करें", "అందరికీ షేర్ చేయండి", "sabko forward karo",
                      "andariki forward cheyandi", "If you don't share this you will have bad luck"],
    "shortened_link": ["Join now https://bit.ly/3AbCdE", "tinyurl.com/yc8abc is the link", "see t.co/Xy12Zq and cutt.ly/AbCd1"],
    "apk_download": ["Download http://files.example.com/PMKisan.apk now", "Install the apk to get the benefit", "app: gov-yojana.apk"],
    "lookalike_domain": ["Visit pm-kisan-yojana.in today", "Update at https://sbi-kyc-update.com/login", "https://pib.gov.in.verify-now.xyz/x",
                         "https://pib.gov.in@evil.com/", "https://evil.com\\@pib.gov.in/", "Claim Rs 5000 subsidy at http://192.168.4.5/claim",
                         "Claim Rs 5000 free at https://offer-now.xyz/go"],
    "impersonation": ["Official message from PIB. Details at https://help-center.example.com/a",
                      "This is an official government message, see http://news-update.in/x",
                      "सरकारी संदेश: देखें http://help-desk.example.com/a"],
}


@pytest.mark.parametrize("sid", sorted(POS))
def test_rule_positive_messages_and_verbatim_evidence(sid):
    assert len(POS[sid]) >= 3
    for t in POS[sid]:
        assert sid in ids(t), (sid, t, analyze(t))
        e = ev_of(t, sid)
        assert e in t and 0 < len(e) <= 80, (sid, t, e)


def test_sign_shape_severity_and_dedup():
    t = "Share your OTP. Send your PIN. Click the link to register. Click here to claim. Forward to 10 people"
    s = analyze(t)
    assert len({x["id"] for x in s}) == len(s)
    sev = [x["severity"] for x in s]
    assert sev[0] == "high" and sev == sorted(sev, key=lambda v: v != "high")
    for x in s:
        assert set(x) == {"id", "severity", "title", "why", "evidence"} and x["severity"] in ("high", "medium")
    assert ev_of(t, "asks_secret") == "Share your OTP"            # first evidence wins


def test_negated_bank_warning_is_not_flagged():
    for t in ("Never share your OTP with anyone. Banks never ask for your PIN.", "कभी किसी को ओटीपी न बताएं", "ఓటీపీ ఎవరికీ చెప్పకండి",
              "Do not share your password."):
        assert "asks_secret" not in ids(t), t


def test_wa_me_is_not_a_shortener_and_empty_inputs():
    assert analyze("Chat with us https://wa.me/message/ABC123") == []
    assert analyze("") == [] and analyze(None) == [] and analyze("   ") == []


# ---- lookalike domains
@pytest.mark.parametrize("u", ["pm-kisan-yojana.in", "sbi-kyc-update.com", "pib.gov.in.verify-now.xyz", "https://pib.gov.in@evil.com/",
                               "https://evil.com\\@pib.gov.in/"])
def test_lookalike_triggers(u):
    assert "lookalike_domain" in ids("Please open " + u + " now")


@pytest.mark.parametrize("u", ["https://pmkisan.gov.in/", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", "https://www.incometax.gov.in/iec/foportal",
                               "https://www.rbi.org.in/", "https://sbi.bank.in/", "https://factcheck.pib.gov.in/", "https://uidai.gov.in/en/",
                               "https://www.onlinesbi.sbi/", "https://sbi.co.in/web/", "https://mygov.in/", "https://wa.me/message/ABC",
                               "https://www.indiatoday.in/fact-check/x", "https://www.thehindu.com/news/national/x"])
def test_genuine_links_never_flagged_high(u):
    s = analyze("The notification is published at " + u + " for all citizens.")
    assert not [x for x in s if x["severity"] == "high"], (u, s)
    assert not {x["id"] for x in s} & {"lookalike_domain", "impersonation"}


def test_lookalike_evidence_is_the_hostname_and_unusual_tld_needs_context():
    assert ev_of("go to sbi-kyc-update.com", "lookalike_domain") == "sbi-kyc-update.com"
    assert "lookalike_domain" not in ids("my blog is at https://cats-and-dogs.xyz/post")
    assert "lookalike_domain" in ids("Get Rs 5000 at https://cats-and-dogs.xyz/post")


def test_impersonation_needs_a_nonofficial_only_link():
    assert "impersonation" not in ids("Official message from PIB. Read https://pib.gov.in/x")
    assert "impersonation" not in ids("This is an official government message.")


# ---- false positives
GENUINE = [
    "Cabinet approved MSP for rabi crops for the marketing season 2026-27.", "The Reserve Bank of India kept the repo rate unchanged at 6.5 per cent.",
    "PM-KISAN instalment of Rs 2,000 was released to 9 crore farmers on 1 August.", "The Union Cabinet has approved a scheme with an outlay of Rs 37,500 crore.",
    "Parliament passed the Finance Bill after a debate in the Lok Sabha.", "Income tax return filing last date for FY 2025-26 is 31 July as notified by CBDT.",
    "The Supreme Court on Monday reserved its verdict on the petitions.", "Police arrested five men in connection with the robbery on Tuesday.",
    "Banks never ask for your OTP, PIN or password. Do not share them with anyone.", "The government has launched a new portal for farmers to check subsidy status.",
    "India beat Australia by 6 wickets in the second T20 international.", "Download the official form from https://incometax.gov.in/iec/foportal",
    "Check your PM-KISAN status at https://pmkisan.gov.in/", "RBI press release at https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
    "Net banking users can log in at https://sbi.bank.in/ using their own credentials.", "Ration cards are issued by state food departments under the NFSA.",
    "Weather: heavy rain expected in Hyderabad over the next three days.", "प्रधानमंत्री ने आज नई रेल लाइन का उद्घाटन किया।",
    "ప్రభుత్వం కొత్త పథకాన్ని ప్రకటించింది.", "Visit https://www.indiatoday.in/fact-check/ for the full report.",
]


def test_ordinary_news_and_official_links_trigger_nothing():
    for t in GENUINE:
        assert analyze(t) == [], (t, analyze(t))


def test_eval_set_and_red_team_false_positives():
    """Eval claims are real announcements / debunk paraphrases. Allowed triggers: a genuine chain-forward or click-to-register phrase
    copied from the viral message, and the one red-team row that contains a fake pib.gov.in.verify-now lookalike link."""
    ev = json.load(open(ROOT / "data/eval_set.json", encoding="utf-8"))
    rt = json.load(open(ROOT / "data/red_team.json", encoding="utf-8"))
    hits = {}
    for r in ev:
        for s in analyze(r["claim"]):
            assert s["evidence"] in r["claim"]
            hits.setdefault(s["id"], []).append(("eval", s["evidence"]))
    for r in rt:
        for s in analyze(r["text"]):
            assert s["evidence"] in r["text"]
            hits.setdefault(s["id"], []).append((r["id"], s["evidence"]))
    assert set(hits) <= {"forward_chain", "click_register", "lookalike_domain"}, hits
    assert all(i == "authority-fake-url" for i, _ in hits.get("lookalike_domain", []))


# ---- performance
def test_adversarial_input_is_fast():
    bait = ("share " * 3300 + "otp " * 2000 + "(a+)+" * 1000 + "Rs 1 " * 1500 + "click " * 1500 + "x" * 2000 + "http://" * 400 + "a-" * 800 + ".xyz " * 500)
    for t in (bait[:20000], "forward " * 2500, "never share your otp " * 900, ("a" * 30 + ".") * 650, "https://" + "pm-kisan." * 2200, bait + "z" * 50000):
        t0 = time.perf_counter()
        analyze(t)
        assert time.perf_counter() - t0 < 0.5


# ---- rendering
def sign(sid="asks_secret", sev="high", ev="Share your OTP"):
    return {"id": sid, "severity": sev, "title": "t", "why": "w", "evidence": ev}


def test_signs_html_escapes_and_labels():
    h = signs_html([sign(ev="<script>alert(1)</script>")], "en")
    assert "<script>" not in h and "&lt;script&gt;" in h
    assert "Warning signs in this message" in h and 'aria-labelledby="signs-h"' in h and 'id="signs-h"' in h
    assert "never change the verdict above" in h and "Do not share OTPs or PINs" in h
    assert signs_html([], "en") == "" and signs_html(None, "hi") == ""


def test_signs_html_summary_caps_at_five_high_first_and_localised():
    ss = [sign(i, "medium", f"m{n}") for n, i in enumerate(("click_register", "urgency_threat", "forward_chain", "shortened_link", "impersonation"))]
    ss.append(sign("upi_trap", "high", "HIGHONE"))
    ss.append(sign("apk_download", "high", "HIGHTWO"))
    h = signs_html(ss, "en")
    # compact box: every sign is still listed (first two open, the rest in <details>); the one-line summary names at most MAX_SHOWN
    assert h.count("<li>") == 7 and MAX_SHOWN == 5 and "and 2 more" in h and "Show all 7 signs" in h
    assert h.index("HIGHONE") < h.index("HIGHTWO") < h.index("m0")
    hi, te = signs_html([sign()], "hi"), signs_html([sign()], "te")
    assert "चेतावनी" in hi and "ఈ సందేశంలో" in te and "Warning signs" not in hi + te
    assert "Warning signs" in signs_html([sign()], "tl")            # falls back to English


BASE = {"verdict": "TRUE", "language": "en", "card": "TRUE card",
        "claims": [{"claim": {"text": "c", "domain": "d"}, "verdict": "TRUE", "reason_code": "official_confirms",
                    "citations": [{"url": "https://pib.gov.in/x", "source": "PIB", "tier": "pib", "date_accessed": "2026-11-12"}]}],
        "checked_at": "2026-11-12T10:00:00+00:00"}


@pytest.mark.parametrize("verdict", ["TRUE", "FALSE", "MISLEADING", "UNVERIFIED"])
def test_result_block_shows_box_for_every_verdict(verdict):
    res = dict(BASE, verdict=verdict, warning_signs=[sign()])
    assert "Warning signs in this message" in site.result_block(res)
    assert "Warning signs" not in site.result_block(dict(BASE, verdict=verdict))
    assert "Warning signs" not in site.result_block(dict(res, warning_signs=[]))


def test_result_block_shows_box_when_no_claims():
    res = {"verdict": "UNVERIFIED", "no_claims": True, "language": "en", "card": "x", "claims": [], "checked_at": "2026-11-12T10:00:00",
           "warning_signs": [sign()]}
    h = site.result_block(res)
    assert "Warning signs in this message" in h and h.index("Nothing to check") < h.index("Warning signs")
    assert "Warning signs" not in site.result_block(dict(res, warning_signs=[]))


def test_box_sits_below_verdict_card_above_trace():
    h = site.result_block(dict(BASE, warning_signs=[sign()]))
    assert h.index('id="cardtext"') < h.index('class="signs"') < h.index("How this verdict was reached")


def test_css_included():
    assert ".signs{" in site.CSS


# ---- web integration
class Fake:
    def __init__(self, ev):
        self.ev = ev

    def search(self, c):
        return list(self.ev)


class JudgeLLM:
    """PIB debunk contradicts; failures stays 0 so results are not degraded (degraded results are never cached)."""
    failures = 0

    def stance(self, claim, title, text, tier=None):
        return "contradicts" if tier == TIER_PIB else "none"


PIB_EV = Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, "2026-11-12T10:00:00+00:00",
                  "Fake claim: government will give Rs 5000 to every woman", "Fake message claims government will give Rs 5000 to every woman")


@pytest.fixture
def server(monkeypatch):
    from http.server import ThreadingHTTPServer
    import sach.web as W
    for k in ("SACH_NO_CACHE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_URL", "KV_REST_API_TOKEN", "SACH_STORE_DIR"):
        monkeypatch.delenv(k, raising=False)
    store.reset()
    W._hits.clear()
    W.Handler.retrievers, W.Handler.llm = [Fake([PIB_EV])], JudgeLLM()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    store.reset()


def post_json(base, text):
    req = urllib.request.Request(base + "/?format=json", json.dumps({"text": text}).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def post_form(base, text):
    return urllib.request.urlopen(urllib.request.Request(base + "/", urllib.parse.urlencode({"text": text}).encode())).read().decode()


CLAIM = "Government will give Rs 5000 to every woman."


def test_json_api_includes_warning_signs_and_html_box(server):
    r = post_json(server, CLAIM + " Share your OTP to receive it.")
    assert isinstance(r["warning_signs"], list) and r["warning_signs"][0]["id"] == "asks_secret"
    assert post_json(server, CLAIM)["warning_signs"] == []
    assert "Warning signs in this message" in post_form(server, CLAIM + " Click the link to register.")
    assert "Warning signs" not in post_form(server, CLAIM)


def test_cached_repeat_gets_signs_from_current_text(server):
    a = CLAIM + " Share your OTP."
    first = post_json(server, a)
    second = post_json(server, a.upper().replace("RS", "Rs"))          # same cache key after normalising, different evidence text
    third = post_json(server, CLAIM)                                    # no scam phrase now: no signs, whatever the cache holds
    assert second.get("cached") is True
    assert first["warning_signs"][0]["evidence"] == "Share your OTP"
    assert second["warning_signs"][0]["evidence"] == "SHARE YOUR OTP"
    assert third["warning_signs"] == []


def test_signs_never_in_ledger_or_cache(server):
    from sach import ledger, cache
    t = CLAIM + " Share your OTP. Click the link to register."
    post_json(server, t)
    blob = json.dumps(ledger.load())
    p = os.environ["SACH_LEDGER"]
    if os.path.exists(p):
        blob += open(p, encoding="utf-8").read()
    assert "warning_signs" not in blob and "OTP" not in blob and "asks_secret" not in blob
    cached = store.get_store().get(cache.key(t, None))
    assert cached is None or "warning_signs" not in cached


# ---- verdict independence
def test_verdict_modules_do_not_import_scamsigns():
    for f in ("pipeline", "verdict", "stance", "cache", "ledger", "store", "retrieve", "llm"):
        assert "scamsigns" not in (ROOT / "sach" / f"{f}.py").read_text(encoding="utf-8"), f


def test_same_verdict_with_and_without_scam_call_to_action():
    from sach.pipeline import check_forward
    a = check_forward(CLAIM, [Fake([PIB_EV])], JudgeLLM(), log=False)
    b = check_forward(CLAIM + " Click the link to register. Forward to 10 groups.", [Fake([PIB_EV])], JudgeLLM(), log=False)
    assert a["verdict"] == b["verdict"] and "warning_signs" not in a and "warning_signs" not in b
