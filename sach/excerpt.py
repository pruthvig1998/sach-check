"""Token diet: send the judge the part of a page that matters, not the whole page.

The judge prompt used to carry up to 6,000 characters of page text per source. Free-tier AI quotas are counted in tokens, so
this is the biggest multiplier we have. `excerpt()` keeps the sentences that best overlap the claim, every sentence that
contains one of the claim's numbers, every sentence with denial/debunk wording, and (for a PIB release) the first sentence,
in the page's original order, capped at about 1,200 characters.

Safety: this only changes what the model SEES. stance.validate_stance() still checks the model's quote against the FULL page
(and runs the prompt-injection check on the full page), so a quote taken from the excerpt validates, and nothing that is not
on the page can. Every excerpt sentence is a substring of the page text.
Pure function, stdlib only, no I/O."""
from __future__ import annotations
import os, re
from .stance import tokens, numbers, _DENIAL

EXCERPT_CHARS = int(os.environ.get("SACH_EXCERPT_CHARS", "1200"))     # 0 turns the diet off (old behaviour: first 6,000 chars)
LEGACY_CHARS = 6000
SENTENCE_MAX = 500                                                      # one huge run-on sentence may not eat the whole budget
_SPLIT = re.compile(r"(?<=[.!?।॥])\s+|\s{2,}")                # . ! ? and the Devanagari danda, or a wide gap


def _clip(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s.rfind(" ", 0, n)
    return s[: cut if cut > n // 2 else n].rstrip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text or "") if s and s.strip()]


def excerpt(claim: str, title: str, text: str, tier: str = "", cap: int | None = None) -> str:
    """The most relevant part of `text` for `claim`, at most about `cap` characters. Short pages are returned unchanged."""
    cap = EXCERPT_CHARS if cap is None else cap
    text = text or ""
    if cap <= 0:
        return text[:LEGACY_CHARS]
    if len(text) <= cap:
        return text
    sents = [_clip(s, SENTENCE_MAX) for s in split_sentences(text)]
    if not sents:
        return text[:cap]
    ctoks, cnums = tokens(claim), numbers(claim)
    must, score = set(), []
    for i, s in enumerate(sents):
        st = tokens(s)
        score.append(len(ctoks & st) / len(ctoks) if ctoks else 0.0)
        if (cnums and cnums & numbers(s)) or _DENIAL.search(s):
            must.add(i)
    if tier in ("pib_debunk", "official"):       # PIB releases arrive as either tier: their first sentence is the lede
        must.add(0)
    picked, used = [], 0

    def take(i):
        nonlocal used
        add = len(sents[i]) + (1 if picked else 0)
        if i in picked or used + add > cap:
            return
        picked.append(i); used += add

    # required sentences first (first PIB sentence, then numbers/denials best-scoring first), then fill by overlap score
    for i in sorted(must, key=lambda i: (i != 0, -score[i], i)):
        take(i)
    for i in sorted((i for i in range(len(sents)) if i not in must and score[i] > 0), key=lambda i: (-score[i], i)):
        take(i)
    if not picked:
        return text[:cap]
    return " ".join(sents[i] for i in sorted(picked))
