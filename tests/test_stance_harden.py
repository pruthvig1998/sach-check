"""STANCEHARDEN: the stance gate may only make Sach abstain more often, never decide more.

Each gap (A-D, F, I) is a case where validate_stance accepted a stance that the quote does not support. A failure in the
'must abstain' tests means a denial about other figures, a negated denial, an approval sentence, a negated confirmation or a
restricted confirmation can again become a decisive FALSE or TRUE-grade stance. The control tests must keep passing: a faithful
denial or confirmation with the same figures is still accepted, so the tightening does not silence real PIB notices."""
import pytest
from sach.stance import validate_stance as v

CLAIM = "Government will give Rs 5000 to every woman"
TITLE = "Claim that Government will give Rs 5000 to every woman is fake"


def _page(quote: str, title: str = TITLE) -> str:
    return f"{title}. {quote}"


# ---- A: a denial about a DIFFERENT number, year or scheme must not refute the claim

@pytest.mark.parametrize("quote", [
    "The claim that Government will give Rs 2000 to every woman is fake and misleading. No such scheme exists.",
    "The claim that Government will give Rs 50,000 to every woman is fake and misleading. No such scheme exists.",
    "The claim that Government will give Rs 500 to every woman is fake and misleading. No such scheme exists.",
    "The claim that Government will give Rs 2,000 to every woman is baseless. No such scheme exists.",
    "The claim that Government will give 2000 rupees to every woman is a hoax. No such scheme exists.",
])
def test_denial_of_a_different_amount_cannot_refute_the_claim(quote):
    # A failure means 'Rs 2000 is fake' is accepted as FALSE for a 'Rs 5000' claim.
    assert v("contradicts", quote, CLAIM, TITLE, _page(quote)) == "none"


def test_denial_of_a_different_year_cannot_refute_the_claim():
    # A failure means a 2019 denial refutes a 2024 claim.
    claim = "Government will give Rs 5000 to every woman in 2024"
    quote = "The claim that Government will give Rs 5000 to every woman in 2019 is fake and misleading. No such scheme exists."
    assert v("contradicts", quote, claim, "Claim that Government will give Rs 5000 to every woman is fake", _page(quote)) == "none"


def test_denial_of_another_named_scheme_cannot_refute_the_claim():
    # A failure means a denial of the Ayushman scheme's payout refutes the PM Kisan claim with the same amount.
    claim = "PM Kisan will pay Rs 6000 to every farmer"
    title = "Claim that PM Kisan will pay Rs 6000 to every farmer is fake"
    quote = "The Ayushman scheme will pay Rs 6000 to every farmer is fake and misleading. No such scheme exists."
    assert v("contradicts", quote, claim, title, _page(quote, title)) == "none"


def test_denial_of_the_named_scheme_still_refutes_it():
    # Control: the same amount and the same scheme name, denied, is still a contradiction.
    claim = "PM Kisan will pay Rs 6000 to every farmer"
    title = "Claim that PM Kisan will pay Rs 6000 to every farmer is fake"
    quote = "The claim that PM Kisan will pay Rs 6000 to every farmer is fake and misleading. No such scheme exists."
    assert v("contradicts", quote, claim, title, _page(quote, title)) == "contradicts"


# ---- B: a denial word that is itself negated must not count as a denial

@pytest.mark.parametrize("quote", [
    "The claim that Government will give Rs 5000 to every woman is not fake, the Cabinet approved it.",
    "The claim that Government will give Rs 5000 to every woman is not a hoax.",
    "The claim that Government will give Rs 5000 to every woman is never false.",
    "The claim that Government will give Rs 5000 to every woman is no longer misleading.",
])
def test_negated_denial_word_is_not_a_denial(quote):
    # A failure means 'is not fake' is read as 'is fake' and refutes a claim that the page itself supports.
    assert v("contradicts", quote, CLAIM, TITLE, _page(quote)) == "none"


# ---- C: a sentence that denies and approves in one breath is ambiguous

@pytest.mark.parametrize("quote", [
    "The Cabinet approved that Government will give Rs 5000 to every woman this year, no such thing.",
    "Cabinet approved the Rs 5000 scheme for every woman; this claim is fake.",
    "The Cabinet has sanctioned Government will give Rs 5000 to every woman, the message is misleading.",
    "The Cabinet announced that Government will give Rs 5000 to every woman. No such thing is fake.",
])
def test_approval_in_the_denial_sentence_abstains(quote):
    # A failure means a sentence that approves the claim and mentions a stray denial word is read as a refutation.
    assert v("contradicts", quote, CLAIM, TITLE, _page(quote)) == "none"


# ---- D: a denial about one figure with an approval of another figure

@pytest.mark.parametrize("quote", [
    "Reports of Rs 2000 for every woman are misleading; the Rs 5000 scheme is real and approved.",
    "Reports of Rs 2000 for every woman are fake. The Rs 5000 scheme is genuine.",
    "Reports of Rs 2000 for every woman are misleading; Government will give Rs 5000 to every woman, notified by the Cabinet.",
])
def test_denial_of_one_figure_with_approval_of_another_abstains(quote):
    # A failure means a denial of Rs 2000 is taken as a refutation of the Rs 5000 claim that the same sentence approves.
    assert v("contradicts", quote, CLAIM, TITLE, _page(quote)) == "none"


def test_hindi_denial_of_another_amount_cannot_refute_the_claim():
    # A failure means a Hindi denial of 2000 rupees refutes a 5000-rupee claim (the native denial words are checked too).
    quote = "सरकार हर महिला को 2000 रुपये देगी, यह दावा फर्जी है।"
    title = "Claim that Government will give Rs 5000 to every woman is fake"
    assert v("contradicts", quote, CLAIM, title, _page(quote, title)) == "none"


def test_telugu_denial_of_another_amount_cannot_refute_the_claim():
    quote = "ప్రభుత్వం ప్రతి మహిళకు 2000 రూపాయలు ఇస్తుందన్న వాదన నకిలీ."
    title = "Claim that Government will give Rs 5000 to every woman is fake"
    assert v("contradicts", quote, CLAIM, title, _page(quote, title)) == "none"


# ---- F: a confirmation that is itself negated must not confirm a positive claim

@pytest.mark.parametrize("quote", [
    "The Cabinet has not approved that Government will give Rs 5000 to every woman under the welfare scheme this year.",
    "Government will never give Rs 5000 to every woman under the welfare scheme this year.",
    "The Cabinet has approved nothing, the plan that Government will give Rs 5000 to every woman was withdrawn.",
    "The proposal that Government will give Rs 5000 to every woman was cancelled this year.",
    "The Rs 5000 payment to every woman is yet to be notified by the Cabinet.",
])
def test_negated_quote_cannot_confirm_a_positive_claim(quote):
    # A failure means a 'has not approved' or 'never give' sentence is accepted as CONFIRMS for the positive claim.
    title = "Cabinet welfare scheme for women"
    assert v("confirms", quote, CLAIM, title, _page(quote, title)) == "none"
    assert v("mixed", quote, CLAIM, title, _page(quote, title)) == "none"


def test_positive_confirmation_is_still_accepted():
    # Control: the same sentence without the negation confirms.
    quote = "The Cabinet approved that Government will give Rs 5000 to every woman this year."
    title = "Cabinet approves welfare scheme"
    assert v("confirms", quote, "Government will give Rs 5000 to every woman this year", title, _page(quote, title)) == "confirms"


def test_negated_claim_with_negated_quote_keeps_working():
    # Control: the existing negated-claim handling is untouched. A negated claim with a negated quote is not blocked by the new check.
    claim = "Government will not give Rs 5000 to every woman this year"
    quote = "The Cabinet has not approved that Government will give Rs 5000 to every woman this year."
    assert v("confirms", quote, claim, "Cabinet welfare scheme", _page(quote, "Cabinet welfare scheme")) == "confirms"


# ---- I: a confirmation whose quote restricts the claim does not confirm the broader claim

@pytest.mark.parametrize("quote", [
    "Government will give Rs 5000 to every woman who is a cricketer in the national team this year.",
    "Government will give Rs 5000 only to every woman this year.",
    "Government will give Rs 5000 to every woman this year, except women in government jobs.",
    "Government will give Rs 5000 to every woman this year, subject to income limits.",
    "Government will give Rs 5000 to every woman this year, limited to rural areas.",
    "Government will give Rs 5000 to every woman this year, excluding students.",
    "Government will give Rs 5000 to every woman this year, provided that the family is poor.",
    "Government will give Rs 5000 to every woman who are in urban slums this year.",
])
def test_restricting_phrase_absent_from_the_claim_abstains(quote):
    # A failure means a restricted sentence confirms the unrestricted claim.
    title = "Cabinet welfare scheme for women"
    assert v("confirms", quote, "Government will give Rs 5000 to every woman this year", title, _page(quote, title)) == "none"


def test_restriction_that_the_claim_also_has_is_not_blocked():
    # Control: when the claim carries the same limit, the quote may confirm it.
    claim = "Government will give Rs 5000 only to every woman this year"
    quote = "Government will give Rs 5000 only to every woman this year."
    assert v("confirms", quote, claim, "Cabinet welfare scheme for women", _page(quote, "Cabinet welfare scheme for women")) == "confirms"


# ---- Controls that MUST still be accepted (no false abstention on faithful text)

def test_plain_pib_denial_without_numbers_still_contradicts():
    claim = "Central Government will reduce the retirement age of employees."
    title = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
    quote = "The Fact Check Unit has clarified that there is no proposal to reduce the retirement age of employees. This claim is fake."
    assert v("contradicts", quote, claim, title, title + ". " + quote) == "contradicts"


def test_same_figures_denial_still_contradicts():
    title = "PIB Fact Check: Government will give Rs 5000 to every woman is fake"
    quote = "The claim that Government will give Rs 5000 to every woman is fake. No such scheme exists."
    assert v("contradicts", quote, CLAIM, title, _page(quote, title)) == "contradicts"


def test_rs_with_comma_matches_plain_digits_in_both_directions():
    # 'Rs 5,000' and '5000' are the same figure, so a comma in either text must not block a valid stance.
    title = "Cabinet welfare scheme for women"
    quote_plain = "The Cabinet approved that Government will give Rs 5000 to every woman this year."
    assert v("confirms", quote_plain, "Government will give Rs 5,000 to every woman this year", title, _page(quote_plain, title)) == "confirms"
    quote_comma = "The Cabinet approved that Government will give Rs 5,000 to every woman this year."
    assert v("confirms", quote_comma, "Government will give Rs 5000 to every woman this year", title, _page(quote_comma, title)) == "confirms"


def test_denial_with_comma_figure_matches_plain_claim():
    title = "PIB Fact Check: Government will give Rs 5000 to every woman is fake"
    quote = "The claim that Government will give Rs 5,000 to every woman is fake. No such scheme exists."
    assert v("contradicts", quote, CLAIM, title, _page(quote, title)) == "contradicts"


def test_lakh_and_crore_figures_are_compared_as_the_numbers_helper_treats_them():
    # The numbers helper removes thousands separators, so 1,00,000 == 100000 (lakh-style grouping). A figure that differs still abstains.
    claim = "Government will give Rs 1,00,000 to every farmer"
    title = "Claim that Government will give Rs 1,00,000 to every farmer is fake"
    same = "The claim that Government will give Rs 100000 to every farmer is fake. No such scheme exists."
    assert v("contradicts", same, claim, title, _page(same, title)) == "contradicts"
    other = "The claim that Government will give Rs 10,000 to every farmer is fake. No such scheme exists."
    assert v("contradicts", other, claim, title, _page(other, title)) == "none"


def test_hindi_denial_of_the_same_amount_still_contradicts():
    # Control: a native-language denial of the same figure, with the claim's subject in the title, is still accepted.
    title = "PIB Fact Check: Government will give Rs 5000 to every woman is fake"
    quote = "सरकार हर महिला को 5000 रुपये देगी, यह दावा फर्जी है।"
    assert v("contradicts", quote, CLAIM, title, _page(quote, title)) == "contradicts"
