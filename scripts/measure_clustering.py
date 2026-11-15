"""Measure near-duplicate claim clustering BEFORE any use. No model, no network. Reads data/eval_set.json (79 labelled claims).

Rule under test (guarded token similarity): two claims may share one checked answer only if
  1. their NUMBERS are identical (a changed amount or date never merges),
  2. their NEGATION words are identical (a 'not' never merges with its opposite),
  3. word-level Jaccard similarity >= T.
Two numbers come out:
  false merges   pairs of DIFFERENT claims that would merge (must be 0; a wrong merge serves one claim's verdict for another)
  recall         synthetic near-duplicates (greeting added, one filler word dropped, a typo, trailing share-request) that merge back to the original
Run: python scripts/measure_clustering.py"""
import json, os, re, sys, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sach.cache import normalise

NEG = {"not", "no", "never", "nahi", "nahin", "नहीं", "नही", "లేదు", "కాదు", "without", "cannot", "won't", "isn't", "n't"}

def toks(t):
    return re.findall(r"\w+", normalise(t), flags=re.UNICODE)

def numbers(t):
    return sorted(re.findall(r"\d[\d,\.]*", normalise(t).replace(",", "")))

def negs(t):
    return sorted(set(toks(t)) & NEG)

def sim(a, b):
    A, B = set(toks(a)), set(toks(b))
    return len(A & B) / len(A | B) if A | B else 0.0

def same_cluster(a, b, T):
    return numbers(a) == numbers(b) and negs(a) == negs(b) and sim(a, b) >= T

def variants(c):
    w = c.split()
    out = ["Good morning all. " + c, c + " Share with all your groups.", "Forwarded many times: " + c]
    if len(w) > 6:
        out.append(" ".join(w[:3] + w[4:]))                 # one word dropped
        out.append(" ".join(w[:2] + [w[2][:-1] + w[2][-1:] * 2] + w[3:]))   # a doubled-letter typo
    return out

def main():
    items = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "eval_set.json")))
    claims = [(i["claim"], i["label"]) for i in items]
    print("claims:", len(claims))
    for T in (0.6, 0.7, 0.8, 0.9):
        fm = [(a, b) for (a, la), (b, lb) in itertools.combinations(claims, 2) if same_cluster(a, b, T)]
        tot = hit = 0
        for c, _ in claims:
            for v in variants(c):
                tot += 1
                hit += same_cluster(c, v, T)
        print("T=%.1f  false merges: %d   recall on synthetic near-duplicates: %d/%d (%.0f%%)" % (T, len(fm), hit, tot, 100 * hit / tot))
        for a, b in fm[:3]:
            print("   FALSE MERGE:", a[:70], "|", b[:70])
    # the hard cases: one fact changed
    hard = [("Government will give Rs 5000 to every woman.", "Government will give Rs 50000 to every woman."),
            ("The government will ban 500 rupee notes.", "The government will not ban 500 rupee notes."),
            ("Exam on 12 March.", "Exam on 13 March.")]
    for a, b in hard:
        print("hard case merged (must be False):", same_cluster(a, b, 0.6), "|", a, "|", b)

if __name__ == "__main__":
    main()
