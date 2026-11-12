"""Offline tests for the evaluation set (data/eval_set.json) and scripts/run_eval.py. No network, no LLM calls."""
import importlib.util, json, os, pathlib, re, sys, unicodedata
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sach.fetch import is_official  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_eval", ROOT / "scripts" / "run_eval.py")
run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_eval)

ROWS = json.load(open(ROOT / "data" / "eval_set.json", encoding="utf-8"))
FIELDS = ("claim", "label", "source", "lang", "seeded", "verified_on", "note")
OLD_LANGS = ("en", "hi", "te", "hinglish", "tinglish")
NEW_LANGS = ("bn", "as", "mni", "mr", "kok", "ne", "ta", "gu", "pa", "or", "kn", "ml", "ur")


def _validation_errors():
    """run_eval.validate_rows, ignoring only 'bad lang' complaints about the 13 new codes. scripts/run_eval.py's LANGS tuple has to
    learn those codes (it is outside this work package); every other problem still fails the test."""
    return [e for e in run_eval.validate_rows(ROWS) if not any(e.endswith(f"bad lang {c!r}") for c in NEW_LANGS)]


def _seed_prids():
    ids = {str(x["prid"]) for x in json.load(open(ROOT / "data" / "seed_debunks.json", encoding="utf-8"))}
    ids |= {str(json.loads(l)["prid"]) for l in open(ROOT / "data" / "pib_index.jsonl", encoding="utf-8") if l.strip()}
    return ids


# ---------- the data ----------
def test_size_and_schema():
    assert 75 <= len(ROWS) <= 90
    assert _validation_errors() == []
    for r in ROWS:
        for f in FIELDS:
            assert f in r, (f, r["claim"])
        assert r["label"] in ("TRUE", "FALSE", "UNVERIFIED")
        assert r["lang"] in OLD_LANGS + NEW_LANGS
        assert isinstance(r["seeded"], bool)
        assert r["note"].strip()
        if r["verified_on"] is None:
            assert r.get("verified_on_note"), r["claim"]
        else:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["verified_on"])


def test_no_duplicate_claims():
    keys = [" ".join(r["claim"].lower().split()) for r in ROWS]
    assert len(keys) == len(set(keys))


def test_languages_present_and_script_matches():
    hi = [r for r in ROWS if r["lang"] == "hi"]
    te = [r for r in ROWS if r["lang"] == "te"]
    assert len(hi) >= 5 and len(te) >= 5
    assert all(re.search(r"[ऀ-ॿ]", r["claim"]) for r in hi)
    assert all(re.search(r"[ఀ-౿]", r["claim"]) for r in te)
    for r in hi + te:   # AI-written rows must say so
        assert "not yet reviewed by a native speaker" in r["note"]
    assert any(r["label"] == "UNVERIFIED" for r in hi) and any(r["label"] == "UNVERIFIED" for r in te)


def test_true_false_sources_are_official_https():
    for r in ROWS:
        if r["label"] in ("TRUE", "FALSE"):
            assert r["source"].startswith("https://"), r["source"]
            assert " " not in r["source"], r["source"]
            assert is_official(r["source"]), r["source"]
            assert r["verified_on"] or r.get("verified_on_note")
        else:
            assert r["source"].startswith("control:"), r["source"]


def test_seeded_flags_match_seed_files():
    ids = _seed_prids()
    for r in ROWS:
        m = re.search(r"PRID=(\d+)", r["source"])
        assert r["seeded"] == bool(m and m.group(1) in ids), r["source"]


def test_label_mix_roughly_balanced():
    n = lambda l: sum(r["label"] == l for r in ROWS)
    assert n("FALSE") >= 15 and n("TRUE") >= 15 and 3 <= n("UNVERIFIED") <= 12


# ---------- the 13 new languages ----------
SCRIPT_RANGES = {
    "bn": [(0x0980, 0x09FF)], "as": [(0x0980, 0x09FF)], "mni": [(0xABC0, 0xABFF), (0xAAE0, 0xAAFF)],
    "mr": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)], "kok": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)], "ne": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)],
    "ta": [(0x0B80, 0x0BFF)], "gu": [(0x0A80, 0x0AFF)], "pa": [(0x0A00, 0x0A7F)], "or": [(0x0B00, 0x0B7F)],
    "kn": [(0x0C80, 0x0CFF)], "ml": [(0x0D00, 0x0D7F)],
    "ur": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
}
NEW_ROWS = [r for r in ROWS if r["lang"] in NEW_LANGS]
TRANSLATED = [r for r in NEW_ROWS if r.get("translated_from")]
BY_CLAIM = {r["claim"]: r for r in ROWS}


def _in(ch, ranges):
    return any(a <= ord(ch) <= b for a, b in ranges)


def _numbers(text):
    """Numbers in a claim with native digits (Bengali, Devanagari, Gujarati, Odia, Meitei Mayek, Arabic-Indic ...) converted to ASCII."""
    t = "".join(str(unicodedata.decimal(c)) if unicodedata.category(c) == "Nd" else c for c in text)
    return sorted(re.findall(r"\d+(?:[.,]\d+)*", t))


def test_new_languages_have_at_least_two_rows_one_false_one_true():
    for lang in NEW_LANGS:
        rows = [r for r in ROWS if r["lang"] == lang]
        assert len(rows) >= 2, lang
        assert {"FALSE", "TRUE"} <= {r["label"] for r in rows}, lang


def test_new_language_totals():
    assert len(NEW_ROWS) == 29 and len(TRANSLATED) == 26
    assert sum(r["label"] == "UNVERIFIED" for r in NEW_ROWS) == 3
    assert len({r["lang"] for r in NEW_ROWS if r["label"] == "UNVERIFIED"}) == 3          # controls spread over three languages
    assert len({r["translated_from"] for r in TRANSLATED}) >= 8                           # not one fact repeated 13 times


@pytest.mark.parametrize("row", NEW_ROWS, ids=lambda r: f"{r['lang']}-{r['label']}")
def test_new_language_row_script_matches_language(row):
    ranges = SCRIPT_RANGES[row["lang"]]
    marked = [c for c in row["claim"] if ord(c) > 127 and unicodedata.category(c)[0] in "LM" and c not in "️‌‍"]  # emoji selector / joiners are script-neutral
    assert len(marked) >= 15, row["claim"]                                                  # really written in that script
    stray = [c for c in marked if not _in(c, ranges)]
    assert not stray, (row["lang"], stray, row["claim"])                                    # no letters from another script
    if row["lang"] == "as":
        assert re.search("[ৰৱ]", row["claim"]), row["claim"]                               # Assamese-specific letters
    if row["lang"] == "bn":
        assert not re.search("[ৰৱ]", row["claim"]), row["claim"]                           # those letters are not Bengali
    assert "not yet reviewed by a native speaker" in row["note"]


@pytest.mark.parametrize("row", TRANSLATED, ids=lambda r: f"{r['lang']}-{r['label']}")
def test_translated_row_keeps_the_verified_facts_of_its_source(row):
    src = BY_CLAIM.get(row["translated_from"])
    assert src is not None and src["lang"] in OLD_LANGS, row["translated_from"]
    for f in ("label", "source", "seeded", "verified_on"):
        assert row[f] == src[f], (f, row["claim"])
    assert src["label"] in ("TRUE", "FALSE") and src["verified_on"], "only rows whose official page was fetched and read may be translated"
    assert row["verified_on_note"].startswith("same fact as the ") and src["claim"][:60] in row["verified_on_note"]
    assert row["verified_on_note"].endswith("translated by an AI model, not native-reviewed")
    assert row["note"] == "Translation of an already-verified row. Written by an AI model; not yet reviewed by a native speaker."
    # every number, date and amount survives translation unchanged (native digits are converted first)
    assert _numbers(row["claim"]) == _numbers(src["claim"]), (row["claim"], _numbers(row["claim"]), _numbers(src["claim"]))


def test_number_extraction_handles_native_digits():
    assert _numbers("২০২৬-২৭ ₹৫৩,৪২৮ ꯲꯰꯲꯶ ۲۰۲۶ ૧,૫૦૦ ୩.୧୫") == sorted(["2026", "27", "53,428", "2026", "2026", "1,500", "3.15"])


@pytest.mark.parametrize("row", [r for r in NEW_ROWS if r["label"] == "UNVERIFIED"], ids=lambda r: r["lang"])
def test_new_language_controls_are_marked_invented(row):
    assert row["source"].startswith("control:") and row["verified_on"] is None and row.get("verified_on_note")
    assert "Invented control" in row["note"] and "avoid resembling any real scheme" in row["note"]
    assert "translated_from" not in row


@pytest.mark.parametrize("lang", NEW_LANGS)
def test_detect_language_on_new_language_rows(lang):
    # Detection is built separately; this runs only once sach.lang lists the code in SUPPORTED (it skips until the branches are merged).
    import sach.lang as sl
    if lang not in getattr(sl, "SUPPORTED", ()):
        pytest.skip(f"sach.lang does not support {lang!r} yet")
    for r in (r for r in ROWS if r["lang"] == lang):
        assert sl.detect_language(r["claim"]) == lang, r["claim"]


# ---------- script: pure functions ----------
def _res(lang, label, got):
    return {"claim": f"{lang}-{label}-{got}", "lang": lang, "label": label, "got": got, "seeded": False, "source": "x"}


def test_by_lang_aggregation():
    res = [_res("hi", "FALSE", "FALSE"),          # correct
           _res("hi", "TRUE", "UNVERIFIED"),      # abstained
           _res("hi", "UNVERIFIED", "FALSE"),     # overclaimed FALSE
           _res("hi", "FALSE", "TRUE"),           # overclaimed TRUE
           _res("te", "TRUE", "TRUE"),
           _res("te", "TRUE", "MISLEADING")]      # wrong, neither abstained nor an overclaim
    b = run_eval.by_lang(res)
    assert b["hi"] == {"n": 4, "correct": 1, "abstained": 1, "overclaimed_false": 1, "overclaimed_true": 1, "wrong_other": 0}
    assert b["te"] == {"n": 2, "correct": 1, "abstained": 0, "overclaimed_false": 0, "overclaimed_true": 0, "wrong_other": 1}
    s = run_eval.summarize(res)
    assert (s["n"], s["correct"], s["overclaimed_false"], s["overclaimed_true"], s["abstained"], s["abstained_wrong"]) == (6, 2, 1, 1, 1, 3)


# ---------- script: runs with fakes ----------
class FakeLLM:
    def __init__(self, fail_on=()):
        self.failures = 0
        self.fail_on = set(fail_on)

    def describe(self):
        return [("fake", "ready")]


SMALL = [
    {"claim": "claim one", "label": "FALSE", "source": "https://pib.gov.in/PressReleasePage.aspx?PRID=1", "lang": "en", "seeded": False, "verified_on": "2026-01-01", "note": "n"},
    {"claim": "दावा दो", "label": "TRUE", "source": "https://pib.gov.in/PressReleasePage.aspx?PRID=2", "lang": "hi", "seeded": False, "verified_on": "2026-01-01", "note": "n"},
    {"claim": "claim three", "label": "UNVERIFIED", "source": "control: invented claim, no source expected", "lang": "en", "seeded": False, "verified_on": None, "verified_on_note": "x", "note": "n"},
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir(); (tmp_path / "data").mkdir()
    es = tmp_path / "data" / "eval_set.json"
    es.write_text(json.dumps(SMALL, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(run_eval, "ROOT", tmp_path)
    monkeypatch.setattr(run_eval, "EVAL_SET", es)
    monkeypatch.setattr(run_eval, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(run_eval, "SUMMARY", tmp_path / "data" / "eval_summary.json")
    monkeypatch.setattr(run_eval, "CHECKPOINT", tmp_path / "cache" / "eval_progress.json")
    monkeypatch.setattr(run_eval, "git_info", lambda: ("abc1234", False))
    monkeypatch.setattr(run_eval, "default_retrievers", lambda: [object()])
    calls = []

    def fake_check(text, ret, llm, log=False):
        calls.append(text)
        if llm is not None and text in getattr(llm, "fail_on", ()):
            llm.failures += 1
        verdict = {"claim one": "FALSE", "दावा दो": "TRUE", "claim three": "UNVERIFIED"}[text]
        return {"verdict": verdict, "claims": [{"reason_code": "r", "citations": [{"url": "https://pib.gov.in/x"}]}]}
    monkeypatch.setattr(run_eval, "check_forward", fake_check)
    monkeypatch.setattr(run_eval, "get_llm", lambda: FakeLLM())
    return tmp_path, calls, monkeypatch


def test_dry_run_makes_no_calls(env, capsys, monkeypatch):
    tmp, calls, mp = env
    mp.setattr(run_eval, "get_llm", lambda: pytest.fail("dry run must not build the LLM"))
    assert run_eval.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "'hi': 1" in out and calls == []
    assert not (tmp / "docs" / "evaluation.md").exists() and not (tmp / "cache").exists()


def test_dry_run_on_real_set(capsys, monkeypatch):
    monkeypatch.setattr(run_eval, "LANGS", tuple(dict.fromkeys(tuple(run_eval.LANGS) + NEW_LANGS)))   # no-op once run_eval knows the codes
    assert run_eval.main(["--dry-run"]) == 0
    assert "by language" in capsys.readouterr().out


def test_full_clean_run_writes_headline_and_archives_old(env):
    tmp, calls, mp = env
    (tmp / "docs" / "evaluation.md").write_text("# Evaluation\nold run\n", encoding="utf-8")
    assert run_eval.main([]) == 0
    doc = (tmp / "docs" / "evaluation.md").read_text(encoding="utf-8")
    assert "Measured on commit `abc1234`" in doc and "## By language" in doc and "Previous runs" in doc
    assert "evaluation-v1-superseded.md" in doc
    old = (tmp / "docs" / "evaluation-history" / "evaluation-v1-superseded.md").read_text(encoding="utf-8")
    assert old.startswith("> **Superseded**") and "abc1234" in old.split("\n")[0] and "old run" in old
    s = json.loads((tmp / "data" / "eval_summary.json").read_text())
    assert (s["n"], s["correct"], s["overclaimed_false"], s["abstained"], s["abstained_wrong"]) == (3, 3, 0, 0, 0)
    assert s["commit"] == "abc1234" and s["dirty"] is False and "date" in s and "by_lang" in s and s["overclaimed_true"] == 0


def test_degraded_run_does_not_write_headline(env):
    tmp, calls, mp = env
    mp.setattr(run_eval, "get_llm", lambda: FakeLLM(fail_on={"claim one"}))
    assert run_eval.main([]) == 0
    assert not (tmp / "docs" / "evaluation.md").exists()
    assert not (tmp / "data" / "eval_summary.json").exists()
    assert "degraded" in (tmp / "docs" / "evaluation-fallback-run.md").read_text(encoding="utf-8")


def test_no_llm_is_degraded(env):
    tmp, calls, mp = env
    mp.setattr(run_eval, "get_llm", lambda: None)
    run_eval.main([])
    assert (tmp / "docs" / "evaluation-fallback-run.md").exists()
    assert not (tmp / "data" / "eval_summary.json").exists()


@pytest.mark.parametrize("args", [["--only-lang", "hi"], ["--limit", "2"]])
def test_partial_run_does_not_write_headline(env, args):
    tmp, calls, mp = env
    (tmp / "docs" / "evaluation.md").write_text("# Evaluation\nkeep me\n", encoding="utf-8")
    assert run_eval.main(args) == 0
    assert (tmp / "docs" / "evaluation.md").read_text(encoding="utf-8") == "# Evaluation\nkeep me\n"
    assert not (tmp / "data" / "eval_summary.json").exists()
    assert not (tmp / "docs" / "evaluation-history").exists()
    assert "partial run" in (tmp / "docs" / "evaluation-partial-run.md").read_text(encoding="utf-8")
    assert len(calls) == (1 if args[0] == "--only-lang" else 2)


def test_resume_skips_finished_and_keeps_failure_count(env):
    tmp, calls, mp = env
    # first session: quota dies on claim three after two claims are done
    mp.setattr(run_eval, "get_llm", lambda: FakeLLM(fail_on={"claim one"}))
    run_eval.main(["--limit", "2"])
    ck = json.loads((tmp / "cache" / "eval_progress.json").read_text())
    assert set(ck["results"]) == {"claim one", "दावा दो"} and ck["llm_failures"] == 1
    calls.clear()
    # next day, healthy LLM: only the unfinished claim runs, but the earlier failure still makes the run degraded
    mp.setattr(run_eval, "get_llm", lambda: FakeLLM())
    run_eval.main(["--resume"])
    assert calls == ["claim three"]
    ck = json.loads((tmp / "cache" / "eval_progress.json").read_text())
    assert ck["llm_failures"] == 1
    assert not (tmp / "docs" / "evaluation.md").exists() and not (tmp / "data" / "eval_summary.json").exists()
    assert (tmp / "docs" / "evaluation-fallback-run.md").exists()


def test_resume_ignored_when_commit_or_set_changes_and_fresh_start_without_flag(env):
    tmp, calls, mp = env
    run_eval.main([])
    assert len(calls) == 3
    calls.clear()
    run_eval.main([])                      # no --resume: starts fresh
    assert len(calls) == 3
    calls.clear()
    run_eval.main(["--resume"])            # same commit, same set: nothing left to do
    assert calls == []
    mp.setattr(run_eval, "git_info", lambda: ("def5678", False))
    run_eval.main(["--resume"])            # different commit: the checkpoint is not reused
    assert len(calls) == 3
