"""PIB Fact Check posts on X as MATCH-layer records (sach/pibposts.py, data/pib_posts.jsonl). All offline."""
import re
import pytest
from sach import match, pibposts
from sach.models import Claim

RECS = [r for r in match.load_pib_records() if r.get("kind") == "post"]
LAPTOP_ID = "2048690628415148453"


def _hits(text):
    return [c for c in match._pib_candidates([text], RECS)]


def _tweet(**kw):
    t = {"id": "2048690628415148453", "author": {"screen_name": "PIBFactCheck"}, "created_at": "Mon Apr 27 09:08:03 +0000 2026",
         "text": "Free laptops for students?\n\nA WhatsApp message is circulating claiming that the Government is accepting applications for free laptops under the 'National Student Laptop Scheme 2026'.\n\n#PIBFactCheck:\n\n❌ This claim is FAKE.\n\n✅ The Government of India has NOT announced any such scheme."}
    t.update(kw)
    return t


# ---- records -------------------------------------------------------------------------------------------------------------------
def test_there_are_post_records_and_all_are_valid():
    assert len(RECS) >= 20
    raw = pibposts.load()
    assert len(raw) == len(RECS)
    for r in raw:
        assert pibposts.valid(r)
        assert re.fullmatch(r"https://x\.com/PIBFactCheck/status/\d{15,20}", r["url"]) and r["url"].endswith(r["id"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"]) and r["verdict"] in ("FALSE", "MISLEADING") and r["kind"] == "post"
        assert len(r["claim"].split()) >= 6


def test_no_duplicate_ids_or_urls():
    ids = [r["id"] for r in pibposts.load()]
    assert len(ids) == len(set(ids))


def test_a_post_is_never_listed_as_a_press_release():
    for r in RECS:
        assert r["prid"] == "" and "pib.gov.in" not in r["url"] and r["url"].startswith("https://x.com/PIBFactCheck/status/")


# ---- ingest rules -------------------------------------------------------------------------------------------------------------
def test_judge_accepts_the_laptop_post():
    rec, why = pibposts.judge(_tweet())
    assert why == "" and rec["verdict"] == "FALSE" and rec["date"] == "2026-04-27" and "National Student Laptop Scheme 2026" in rec["claim"]


@pytest.mark.parametrize("patch,needle", [
    ({"author": {"screen_name": "someone_else"}}, "author"),
    ({"text": "Free laptops for students? A message claims the Government is accepting applications for free laptops. This claim is FAKE."}, "#pibfactcheck"),
    ({"text": "Free laptops? A message claims free laptops under a scheme for all students.\n\n#PIBFactCheck: we are looking into this."}, "debunk marker"),
    ({"replying_to": "123456789012345678"}, "reply"),
    ({"quote": {"author": {"screen_name": "random"}}}, "quotes someone"),
    ({"text": "#PIBFactCheck: This message is true and genuine, the Government has announced free laptops for all students in the scheme."}, "debunk marker"),
    ({"created_at": "", "created_timestamp": None}, "date"),
])
def test_judge_rejects(patch, needle):
    rec, why = pibposts.judge(_tweet(**patch))
    assert rec is None and needle in why.lower()


# ---- matching: the strict rules are unchanged, and the point is that nothing false slips through -------------------------------
@pytest.mark.parametrize("text", [
    "Government is accepting applications for free laptops under the National Student Laptop Scheme 2026",
    "The Government is accepting applications for free laptops under the 'National Student Laptop Scheme 2026'.",
])
def test_the_laptop_scheme_matches_pib_fact_check_wording(text):
    hits = _hits(text)
    assert [h["review_url"] for h in hits] == [f"https://x.com/PIBFactCheck/status/{LAPTOP_ID}"]
    assert hits[0]["checker"] == match.PIB_X_NAME == "PIB Fact Check (on X)" and hits[0]["source"] == "pib_x_post"


@pytest.mark.parametrize("text", [
    "Government is accepting applications for free laptops under the National Student Laptop Scheme 2025",     # different year
    "Government is NOT accepting applications for free laptops under the National Student Laptop Scheme 2026",  # negated
    "Government is accepting applications for free tablets under the National Student Laptop Scheme 2026",     # different item
    "Government is accepting applications for free laptops under the PM Students Laptop Scheme 2026",           # different scheme name
    "Delhi Government is accepting applications for free laptops under the National Student Laptop Scheme 2026",  # different body
])
def test_laptop_near_misses_do_not_match(text):
    assert not [h for h in _hits(text) if h["review_url"].endswith(LAPTOP_ID)]


def _mutations(claim):
    out = {}
    nums = re.findall(r"\d[\d,.]*", claim)
    if nums:
        out["number_changed"] = claim.replace(nums[0], str(int(re.sub(r"\D", "", nums[0]) or 0) + 7), 1)
    if re.search(r"\b(is|are|has|have|will|can)\b", claim):
        out["negated"] = re.sub(r"\b(is|are|has|have|will|can)\b", r"\1 not", claim, count=1)
    else:
        out["negated"] = claim + " This is not true."
    return {k: v for k, v in out.items() if v != claim}


def test_every_record_matches_its_own_claim_or_is_a_known_strictness_miss():
    misses = [r["post_id"] for r in RECS if not any(h["review_url"].endswith(r["post_id"]) for h in _hits(r["claim"]))]
    assert len(misses) <= 3, misses           # a couple of long claims fall through to the live layer; that is safe, never a wrong verdict


def test_changing_a_number_or_negating_a_claim_never_matches_its_own_record():
    bad = []
    for r in RECS:
        for kind, m in _mutations(r["claim"]).items():
            if any(h["review_url"].endswith(r["post_id"]) for h in _hits(m)):
                bad.append((kind, r["post_id"], m[:100]))
    assert not bad, bad


# ---- what people see ---------------------------------------------------------------------------------------------------------------
def test_the_match_is_attributed_to_pib_fact_check_on_x_with_the_post_link_and_date():
    text = "Government is accepting applications for free laptops under the National Student Laptop Scheme 2026"
    cand = _hits(text)[0]
    v = match.verdict_from_match(Claim(text, "scheme"), cand, "", "2026-11-13T12:00:00+00:00")
    assert v.layer == "match" and v.verdict == "FALSE"
    card = match.render_match_card([v], "FALSE", "en")
    assert "PIB Fact Check (on X)" in card and f"https://x.com/PIBFactCheck/status/{LAPTOP_ID}" in card and "27 Apr 2026" in card
    assert "pib.gov.in/PressRelease" not in card


def test_a_press_release_match_is_unchanged():
    assert match.PIB_NAME == "PIB Fact Check" and match.PIB_NAME in match.PIB_NAMES and match.PIB_X_NAME in match.PIB_NAMES
