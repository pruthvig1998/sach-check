"""INDEXGROW: the 8 PIB releases added by scripts/add_pib_debunks.py (each fetched live from pib.gov.in on 2026-11-13).
Offline: reads only data/pib_index.jsonl. Paraphrases must hit the PIB record; near-misses must NOT match anything (a false match is the worst bug)."""
import json, os, re
import pytest
from sach import match, index

NEW_PRIDS = {"1980375", "2085532", "1563836", "2163332", "2104089", "2009349", "1781247", "1513134"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _rows():
    return [json.loads(l) for l in open(index.INDEX_PATH, encoding="utf-8") if l.strip()]

def test_new_records_are_complete():
    rows = {str(r["prid"]): r for r in _rows()}
    assert NEW_PRIDS <= set(rows)
    recs = {r["prid"]: r for r in match.load_pib_records()}
    for p in NEW_PRIDS:
        r = rows[p]
        assert r["title"].strip() and r["excerpt"].strip()
        assert re.match(r"https://(www\.)?pib\.gov\.in/PressReleasePage\.aspx\?PRID=%s$" % p, r["url"])
        assert ISO.match(match._pib_date(r["posted_on"]))
        assert p in recs, "must be loadable by the match layer"
        assert match.pib_claim_from_title(r["title"])
        assert match.host_of(recs[p]["url"]) in match.PIB_HOSTS

def test_no_duplicate_prid_or_url():
    rows = _rows()
    prids = [str(r["prid"]) for r in rows]
    urls = [r["url"] for r in rows]
    assert len(prids) == len(set(prids))
    assert len(urls) == len(set(urls))

# (claim as a forward might word it, PIB release ids that are acceptable)
PARAPHRASES = [
    ("Airport Authority of India cautions about recruitments", {"1980375"}),
    ("Airport Authority of India recruitments cautions", {"1980375"}),
    ("appointment letter for appointment of Director (M&CP) in Food Corporation of India", {"1563836"}),
    ("Appointment letter for the appointment of Director M&CP in Food Corporation of India", {"1563836"}),
    ("Ministry of Labour & Employment Cautions Citizens Against PMVBRY Portals", {"2163332"}),
    ("Recruitment drive by National Rural Development and Recreation Mission NRDRM in the name of Ministry of Rural Development",
     {"2104089", "2118851"}),   # 2118851 is the earlier PIB release on the same fake NRDRM drive
    ("Recruitment notification for 4208 post of Constable and 452 Sub-inspectors in RPF on website of RTUEXAM.NET", {"2009349"}),
    ("RPF recruitment notification for 4208 posts of Constable and 452 Sub-inspectors on RTUEXAM.NET website", {"2009349"}),
    ("4208 Constable and 452 Sub-inspector posts in RPF recruitment notification on RTUEXAM.NET", {"2009349"}),
    ("RPF recruitment 4208 Constable and 452 Sub-Inspector posts, apply on RTUEXAM.NET", {"2009349"}),
    ("Recruitments by unknown person in the name of AICTE", {"1781247"}),
    ("Recruitment by an unknown person in the name of AICTE", {"1781247"}),
    ("AICTE recruitments by unknown persons", {"1781247"}),
    ("WCD Ministry cautions general public against filling up forms in name of BBBP", {"1513134"}),
    ("Filling up forms in name of BBBP, WCD Ministry cautions general public", {"1513134"}),
]

# (original-language text, the English a translator would give, acceptable ids). The English is what the pipeline's translator step supplies.
MULTILINGUAL = [
    ("एआईसीटीई के नाम पर अज्ञात व्यक्ति द्वारा भर्ती", "Recruitment by an unknown person in the name of AICTE", {"1781247"}),
    ("AICTE పేరుతో తెలియని వ్యక్తి ద్వారా నియామకాలు", "Recruitments by unknown person in the name of AICTE", {"1781247"}),
    ("AICTE பெயரில் அறியப்படாத நபரால் ஆட்சேர்ப்புகள்", "Recruitments by unknown person in the name of AICTE", {"1781247"}),
    ("AICTE-র নামে অজানা ব্যক্তির দ্বারা নিয়োগ", "Recruitment by an unknown person in the name of AICTE", {"1781247"}),
    ("RTUEXAM.NET वेबसाइट पर आरपीएफ में कांस्टेबल के 4208 पद और उप-निरीक्षक के 452 पदों की भर्ती अधिसूचना",
     "Recruitment notification for 4208 posts of Constable and 452 Sub-inspectors in RPF on website of RTUEXAM.NET", {"2009349"}),
    ("RTUEXAM.NET వెబ్‌సైట్‌లో RPFలో 4208 కానిస్టేబుల్ మరియు 452 సబ్-ఇన్‌స్పెక్టర్ పోస్టుల నియామక ప్రకటన",
     "RPF recruitment notification for 4208 posts of Constable and 452 Sub-inspectors on RTUEXAM.NET website", {"2009349"}),
    ("भारतीय खाद्य निगम में निदेशक (M&CP) की नियुक्ति के लिए नियुक्ति पत्र",
     "Appointment letter for the appointment of Director M&CP in Food Corporation of India", {"1563836"}),
    ("இந்திய விமான நிலைய ஆணையம் ஆட்சேர்ப்புகள் குறித்து எச்சரிக்கிறது", "Airport Authority of India cautions about recruitments", {"1980375"}),
    ("भारतीय विमानपत्तन प्राधिकरण भर्तियों के बारे में सावधान करता है", "Airport Authority of India cautions about recruitments", {"1980375"}),
    ("মহিলা ও শিশু বিকাশ মন্ত্রক বিবিবিপি-র নামে ফর্ম পূরণ করার বিরুদ্ধে জনসাধারণকে সতর্ক করছে",
     "WCD Ministry cautions general public against filling up forms in name of BBBP", {"1513134"}),
]

# Must NOT match any PIB record: number changed, other body, other place/year, negated, direction flipped, TRUE statements on the same topic,
# and the famous laptop forward (PIB's laptop debunks were published on X, not as pib.gov.in releases, so there is no record to match).
NEAR_MISSES = [
    "Recruitment notification for 4309 posts of Constable and 452 Sub-inspectors in RPF on website of RTUEXAM.NET",
    "Recruitment notification for 4208 posts of Constable and 542 Sub-inspectors in RPF on website of RTUEXAM.NET",
    "Recruitment notification for 4208 posts of Constable and 452 Sub-inspectors in CRPF on website of RTUEXAM.NET",
    "Recruitments by known persons in the name of UGC",
    "Recruitments by unknown person in the name of NCERT",
    "No recruitments by unknown person in the name of AICTE",
    "Airport Authority of India has published a genuine recruitment notification on its official website",
    "Airport Authority of Pakistan cautions about recruitments",
    "Free medical treatment during Maha Kumbh Mela",
    "Free travel during Kumbh Mela in Nashik",
    "Appointment letter for appointment of Director (M&CP) in Central Warehousing Corporation",
    "Appointment letter for appointment of Director (Finance) in Food Corporation of India",
    "Labour Ministry launches PMVBRY portal for registration",
    "Ministry of Labour & Employment Cautions Citizens Against EPFO Portals",
    "Recruitment drive by National Urban Livelihood Mission in the name of Ministry of Housing and Urban Affairs",
    "WCD Ministry cautions general public against filling up forms in name of PM Matru Vandana Yojana",
    "WCD Ministry invites general public to fill up forms in name of BBBP",
    "Beti Bachao Beti Padhao scheme was launched in 2015 by the Prime Minister",
    "Airport Authority of India recruits Junior Executives through GATE scores",
    "Railway Protection Force conducts recruitment of Constables through computer based test",
    "AICTE approves technical institutions across India",
    "Food Corporation of India appoints Directors through Public Enterprises Selection Board",
    "Free laptops under PM Students Laptop Scheme 2026",
    "Recruitment drive by National Rural Development & Recreation Mission in the name of Ministry of Rural Development in Bihar",
    "AICTE recruiting 4208 officers for all vacancies",
    "Recruitments by AICTE through official portal aicte-india.org",
    "Central Government is giving free laptops to all students under the PM Students Laptop Scheme 2026",
]

@pytest.fixture(scope="module")
def matcher():
    return match.Matcher(pib_records=match.load_pib_records())

def _prid(hit):
    return hit["review_url"].rsplit("PRID=", 1)[-1]

@pytest.mark.parametrize("claim,ids", PARAPHRASES)
def test_paraphrase_matches_pib(matcher, claim, ids):
    hit = matcher.match(claim)
    assert hit is not None and hit["checker"] == match.PIB_NAME
    assert _prid(hit) in ids and hit["review_url"].startswith("https://pib.gov.in/")

@pytest.mark.parametrize("original,english,ids", MULTILINGUAL)
def test_multilingual_matches_pib(matcher, original, english, ids):
    hit = matcher.match(original, english)
    assert hit is not None and _prid(hit) in ids

@pytest.mark.parametrize("claim", NEAR_MISSES)
def test_near_miss_is_not_matched(matcher, claim):
    assert matcher.match(claim) is None
