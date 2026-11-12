"""Word normalisation in sach.stance.tokens: same-meaning wording must count as the same topic, but nothing safety-related loosens."""
import pytest
from sach import stance as S

CLAIM = "GST will be levied on UPI payments above Rs 2000"
TITLE = "Claims that Government is considering levying Goods and Services Tax (GST) on UPI transactions over ₹2,000 are completely false, misleading, and without any basis"

def test_thousands_commas_do_not_split_numbers():
    assert "2000" in S.tokens("limit of ₹2,000") and "000" not in S.tokens("limit of ₹2,000")
    assert S.tokens("1,20,579 posts") >= {"120579"}

@pytest.mark.parametrize("a,b", [("levied", "levying"), ("payments", "transactions"), ("above", "over"), ("rupees", "rs"),
                                 ("hiked", "increase"), ("banned", "prohibits")])
def test_same_meaning_words_share_a_token(a, b):
    assert S.tokens(a) == S.tokens(b)

def test_the_exact_pib_debunk_is_now_matched_by_both_judging_paths():
    assert S.overlap(CLAIM, TITLE) >= 0.7
    assert S.validate_stance("contradicts", TITLE, CLAIM, TITLE, TITLE + " " + TITLE) == "contradicts"
    assert S.heuristic_stance(CLAIM, TITLE, TITLE, "pib_debunk") == "contradicts"

def test_unrelated_pages_still_do_not_match():
    other = "Cabinet approves MSP for rabi crops: wheat 2610, barley 2286 for marketing season 2027-28"
    assert S.overlap(CLAIM, other) < 0.3
    assert S.validate_stance("contradicts", TITLE, "Free laptops for all students above Rs 2000", TITLE, TITLE) == "none"

def test_a_changed_number_still_blocks_confirmation():
    page = "The Government has raised the dearness allowance by 3% from 1 July 2026"
    assert S.validate_stance("confirms", page, "Dearness allowance hiked by 5% from 1 July 2026", "DA", page) == "none"

def test_a_debunk_page_still_cannot_confirm_after_normalisation():
    assert S.validate_stance("confirms", TITLE, CLAIM, TITLE, TITLE) == "none"

def test_direction_conflict_still_applies():
    assert S.validate_stance("confirms", "The Centre will reduce the retirement age to 58", "Centre has increased retirement age to 62",
                             "Retirement age", "The Centre will reduce the retirement age to 58") == "none"
