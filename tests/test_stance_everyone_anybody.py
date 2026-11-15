"""Directive 6 addendum: a PIB debunk must be able to refute a claim phrased with "everyone" when the denial says "anybody".

Before the fix, validate_stance() accepted the judge's CONTRADICTS (a correct verbatim quote) and then _contradiction_scope_ok() rejected it,
because the claim's "everyone" was a required critical word and the PIB sentence says "to anybody". The featured claim therefore ended UNVERIFIED
although the debunk was retrieved first and the judges said CONTRADICTS. The repo's FakeLLM returns "contradicts" without running validate_stance,
so it could never see this; the judge below applies the same validation the real providers go through.

The page text is the real PIB release (PRID 1618314) saved as a fixture. Nothing here special-cases that page, that claim or any Try chip: the fix is a
class-level equivalence (everyone ~ anybody) inside the CONTRADICTS scope check only."""
import pathlib

import pytest
from test_cache_trace import CountingRetriever
from sach.excerpt import excerpt
from sach.models import Evidence, TIER_PIB
from sach.pipeline import check_forward
from sach.stance import validate_stance as v

_RAW = (pathlib.Path(__file__).parent / "fixtures" / "pib_1618314_page.txt").read_text(encoding="utf-8")
TITLE, TEXT = _RAW.split("\n", 1)
URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1618314&reg=48&lang=2"
CLAIM = "Government is giving Rs 1000 to everyone under Corona Sahayata Yojana."
FORWARD = CLAIM + " Click the link to register. Please forward to all groups!"
TS = "2026-11-15T00:00:00+00:00"
# What two different judge providers actually answered for this page and claim (raw replies, quotes copied verbatim from the page).
QUOTES = [
    "Government of India is not giving Rs 1000 to anybody under the so called Corona Sahayata Yojana scheme.",
    "Fact Check Unit of Press Information Bureau has today clarified in a tweet that Government of India is not giving Rs 1000 to anybody "
    "under the so called Corona Sahayata Yojana scheme.",
]


class ValidatingJudge:
    """Behaves like the real providers: a model label and quote, then the same validate_stance gate. failures stays 0 (not degraded)."""
    failures = 0
    name = "fakejudge"

    def __init__(self, quote):
        self.quote = quote

    def reset_provider(self):
        pass

    def last_provider(self):
        return self.name

    def stance(self, claim, title, text, tier=None):
        return v("contradicts", self.quote, claim, title, text)


def _synthetic(denial: str, title: str = "Fake news on WhatsApp claims Government giving Rs 1000 under Corona Sahayata Yojana") -> tuple[str, str]:
    return title, f"Ministry of Information & Broadcasting {title} Posted On: 25 APR 2020 Fact Check Unit has today clarified. {denial}"


# ---- (a) the featured claim against the real page content -> contradicts -> FALSE with the PIB citation

@pytest.mark.parametrize("quote", QUOTES)
def test_real_pib_debunk_refutes_the_everyone_claim(quote):
    assert quote in TEXT, "the quote must be verbatim from the real page"
    assert v("contradicts", quote, CLAIM, TITLE, TEXT) == "contradicts"


@pytest.mark.parametrize("quote", QUOTES)
def test_featured_forward_ends_false_with_the_pib_citation(quote):
    ev = Evidence("PIB (Press Information Bureau)", URL, TIER_PIB, TS, TITLE, TEXT)
    out = check_forward(FORWARD, [CountingRetriever([ev])], ValidatingJudge(quote), log=False, use_cache=False)
    assert out["verdict"] == "FALSE"
    cites = [c["url"] for cl in out["claims"] for c in cl["citations"]]
    assert any("PRID=1618314" in u for u in cites)


def test_the_trace_names_the_judge_provider_per_source():
    ev = Evidence("PIB (Press Information Bureau)", URL, TIER_PIB, TS, TITLE, TEXT)
    out = check_forward(FORWARD, [CountingRetriever([ev])], ValidatingJudge(QUOTES[0]), log=False, use_cache=False)
    src = out["claims"][0]["trace"]["sources"][0]
    assert src["judged"]["outcome"] == "answered" and src["judged"]["provider"] == "fakejudge"


def test_a_judge_without_provider_methods_still_works_and_adds_no_provider_field():
    class Plain:
        failures = 0
        def stance(self, claim, title, text, tier=None):
            return v("contradicts", QUOTES[0], claim, title, text)
    ev = Evidence("PIB (Press Information Bureau)", URL, TIER_PIB, TS, TITLE, TEXT)
    out = check_forward(FORWARD, [CountingRetriever([ev])], Plain(), log=False, use_cache=False)
    assert out["verdict"] == "FALSE" and "provider" not in out["claims"][0]["trace"]["sources"][0]["judged"]


# ---- (b) guardrails: the fix restores decisiveness inside the safety record, it does not move the FALSE bar

def test_a_debunk_page_retrieved_for_a_different_claim_stays_neither():
    other = "Government is giving Rs 5000 to every woman under Mahila Samman Yojana."
    assert v("contradicts", QUOTES[0], other, TITLE, TEXT) == "none"


def test_a_denial_of_a_different_amount_still_cannot_refute():
    claim = "Government is giving Rs 5000 to everyone under Corona Sahayata Yojana."
    assert v("contradicts", QUOTES[0], claim, TITLE, TEXT) == "none"


@pytest.mark.parametrize("denial", [
    "Government of India is not giving Rs 1000 to anyone above 60 years under the so called Corona Sahayata Yojana scheme.",
    "Government of India is not giving Rs 1000 to any woman under the so called Corona Sahayata Yojana scheme.",
    "Government of India is not giving Rs 1000 to anybody in Delhi under the so called Corona Sahayata Yojana scheme.",
])
def test_a_denial_that_is_narrower_than_everyone_still_abstains(denial):
    title, text = _synthetic(denial)
    assert v("contradicts", denial, CLAIM, title, text) == "none"


def test_a_hedged_or_negated_denial_still_abstains():
    for denial in ("Government of India may not be giving Rs 1000 to anybody under the so called Corona Sahayata Yojana scheme.",
                   "It is not false that Government of India is giving Rs 1000 to anybody under the so called Corona Sahayata Yojana scheme."):
        title, text = _synthetic(denial)
        assert v("contradicts", denial, CLAIM, title, text) == "none"


def test_a_confirmation_is_never_relaxed_by_the_everyone_anybody_rule():
    quote = "Government of India is giving Rs 1000 to anybody who applies under the Corona Sahayata Yojana scheme."
    title, text = "Corona Sahayata Yojana payments", f"Corona Sahayata Yojana payments. {quote}"
    assert v("confirms", quote, CLAIM, title, text) == "none"


def test_unverified_controls_stay_unverified():
    assert v("none", QUOTES[0], CLAIM, TITLE, TEXT) == "none"
    ev = Evidence("PIB (Press Information Bureau)", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
                  "Cabinet approves new scheme for coal gasification", "The Union Cabinet approved a scheme for coal gasification projects.")
    out = check_forward(FORWARD, [CountingRetriever([ev])], ValidatingJudge(QUOTES[0]), log=False, use_cache=False)
    assert out["verdict"] == "UNVERIFIED"


# ---- (c) the judge must see a denial that sits beyond the old character budget (excerpt, not the trace's 260-character display clip)

def test_the_excerpt_keeps_a_denial_that_sits_beyond_the_old_cut():
    filler = " ".join(f"Sentence number {i} describes an unrelated routine administrative detail of the ministry." for i in range(60))
    denial = "Government of India is not giving Rs 1000 to anybody under the so called Corona Sahayata Yojana scheme."
    page = f"{filler} {denial}"
    assert page.index(denial) > 2500                      # well past any fixed prefix budget
    ex = excerpt(CLAIM, TITLE, page, TIER_PIB)
    assert denial in ex and len(ex) <= 1300


# ---- the Hindi chip: its claim is translated to "Corona Assistance Scheme", PIB writes "Corona Sahayata Yojana" (same words, transliterated)

HINDI_CLAIM = "The government is giving Rs 1000 to everyone under the Corona Assistance Scheme."


def test_a_translated_hindi_claim_is_refuted_by_the_transliterated_pib_title():
    assert v("contradicts", QUOTES[0], HINDI_CLAIM, TITLE, TEXT) == "contradicts"


def test_the_sahayata_assistance_equivalence_does_not_let_a_different_scheme_be_refuted():
    other = "The government is giving Rs 1000 to everyone under the Ayushman Assistance Scheme."
    assert v("contradicts", QUOTES[0], other, TITLE, TEXT) == "none"
    other2 = "The government is giving Rs 1000 to everyone under the Kisan Assistance Scheme."
    assert v("contradicts", QUOTES[0], other2, TITLE, TEXT) == "none"
