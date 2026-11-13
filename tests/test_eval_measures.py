"""scripts/run_eval.py: separate measures, latency, every failed case listed, ERROR handling, old checkpoints, eval_summary.json."""
import importlib.util, json, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_eval():
    spec = importlib.util.spec_from_file_location("run_eval_measures_under_test", ROOT / "scripts" / "run_eval.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Llm:
    failures = 0


def _row(got, label, lang="en", layer="live", ms=None, **extra):
    r = {"claim": f"{label} {got} {lang} {layer} {ms}", "label": label, "got": got, "lang": lang, "layer": layer,
         "seeded": False, "reasons": ["r_" + got], "cites": []}
    if ms is not None:
        r["ms"] = ms
    r.update(extra)
    return r


# ---------------------------------------------------------------- percentiles and latency
def test_nearest_rank_percentiles_on_known_arrays():
    ev = _run_eval()
    ten = list(range(1, 11))
    assert ev.percentile(ten, 50) == 5 and ev.percentile(ten, 90) == 9 and ev.percentile(ten, 95) == 10
    assert ev.percentile(ten, 100) == 10 and ev.percentile(ten, 1) == 1
    hundred = list(range(1, 101))
    assert ev.percentile(hundred, 50) == 50 and ev.percentile(hundred, 90) == 90 and ev.percentile(hundred, 95) == 95
    assert ev.percentile([], 50) is None
    assert ev.percentile([7], 95) == 7


def test_latency_stats_are_in_seconds_and_include_mean_and_max():
    ev = _run_eval()
    res = [_row("FALSE", "FALSE", ms=float(k * 1000)) for k in (10, 1, 9, 2, 8, 3, 7, 4, 6, 5)]     # unsorted on purpose
    lat = ev.latency(res)
    s = lat["all"]
    assert s["n"] == 10 and s["p50_s"] == 5.0 and s["p90_s"] == 9.0 and s["p95_s"] == 10.0
    assert s["max_s"] == 10.0 and s["mean_s"] == 5.5 and lat["untimed"] == 0


def test_latency_counts_claims_without_timing_and_splits_by_layer():
    ev = _run_eval()
    res = [_row("FALSE", "FALSE", layer="match", ms=200.0), _row("FALSE", "FALSE", layer="live", ms=800.0),
           _row("TRUE", "TRUE", layer="live", ms=1200.0), _row("TRUE", "TRUE", layer="live")]     # last one: an old checkpoint row
    lat = ev.latency(res)
    assert lat["untimed"] == 1 and lat["all"]["n"] == 3
    assert lat["by_layer"]["match"]["p50_s"] == 0.2 and lat["by_layer"]["live"]["n"] == 2
    assert lat["by_layer"]["live"]["max_s"] == 1.2


# ---------------------------------------------------------------- measures
def test_measures_use_their_own_denominators_and_errors_are_failures():
    ev = _run_eval()
    res = [_row("FALSE", "FALSE"),                 # correct
           _row("UNVERIFIED", "TRUE"),             # abstained on a decisive label
           _row("UNVERIFIED", "UNVERIFIED"),       # correct abstention, not decisive
           _row("FALSE", "TRUE"),                  # overclaim FALSE
           _row("TRUE", "FALSE"),                  # overclaim TRUE
           _row("MISLEADING", "FALSE"),            # wrong but not an overclaim
           _row("ERROR", "FALSE", degraded=False, error="RuntimeError")]
    m = ev.measures(res, failed=2)
    assert m["accuracy"] == {"correct": 2, "n": 7}
    assert m["abstention"] == {"abstained_on_decisive": 1, "decisive_n": 6}
    assert m["overclaim"] == {"false": 1, "true": 1, "n": 7}
    assert m["wrong_not_overclaim"] == {"count": 1, "n": 7}         # the ERROR is not counted here, it is a failure
    assert m["failures"]["errors"] == 1 and m["failures"]["llm_source_failures"] == 2
    assert m["failures"]["claims_with_any_failure"] == 1


def test_an_error_is_never_correct_or_abstained():
    ev = _run_eval()
    res = [_row("ERROR", "UNVERIFIED", error="ValueError"), _row("ERROR", "TRUE", error="ValueError")]
    m = ev.measures(res)
    assert m["accuracy"]["correct"] == 0 and m["abstention"]["abstained_on_decisive"] == 0
    assert m["failures"]["errors"] == 2 and m["wrong_not_overclaim"]["count"] == 0


def test_measures_section_and_report_sections_are_present(tmp_path):
    ev = _run_eval()
    res = [_row("FALSE", "FALSE", ms=900.0), _row("UNVERIFIED", "TRUE", ms=1500.0, degraded=True),
           _row("MISLEADING", "FALSE", ms=700.0, search_status="down"), _row("ERROR", "FALSE", ms=50.0, error="RuntimeError")]
    meta = {"commit": "x", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}
    rep = ev.build_report(res, meta, True, "", 0, docs=tmp_path)
    for section in ("## Measures, separately", "## Latency (wall time per claim, seconds)", "## Failed, abstained and wrong cases",
                    "## What this run did not measure", "## Every claim", "## Limitations", "## Which layer answered"):
        assert section in rep
    assert "accuracy counts abstentions" in rep.lower().replace("`", "")
    assert "Exact-match accuracy: **1/4**" in rep and "Overclaimed FALSE (the unforgivable failure): 0" in rep     # old headline lines kept
    assert "Abstention rate" in rep and "| 0 | 4 decisive-label claims | 0.0% |" in rep      # the degraded UNVERIFIED is not a real abstention
    assert "Claims without timing: **0**" in rep
    assert "Judge problem" in rep and "Search failure" in rep and "ERROR (checking the claim raised" in rep


def test_failed_table_lists_exactly_the_non_exact_matches(tmp_path):
    ev = _run_eval()
    res = [_row("FALSE", "FALSE", ms=1.0), _row("UNVERIFIED", "TRUE", ms=2.0), _row("TRUE", "FALSE", ms=3.0),
           _row("FALSE", "TRUE", ms=4.0), _row("MISLEADING", "FALSE", ms=5.0), _row("TRUE", "TRUE", ms=6.0),
           _row("ERROR", "TRUE", ms=7.0, error="KeyError")]
    for r in res:
        r["claim"] = f"claim {r['label']} {r['got']}"
    section = ev.failed_table(res)
    text = "\n".join(section)
    for r in res:
        assert (f"| {r['claim']} |" in text) == (r["got"] != r["label"])          # exact matches absent, every other case present
    assert "Every claim whose result is not an exact match: 5 of 7" in text
    assert "| 7.0 |" in text and "| 3.0 |" in text                             # ms column present
    assert ev.failed_table([_row("FALSE", "FALSE")])[-1].startswith("| none")


# ---------------------------------------------------------------- run(): timing, ERROR, old checkpoints
def test_run_records_ms_and_flags_and_handles_a_raising_claim(monkeypatch):
    ev = _run_eval()
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)

    def check(text, ret, llm, log=False):
        if text.endswith("2"):
            raise ValueError("bad claim")
        time.sleep(0.02)
        return {"verdict": "UNVERIFIED", "claims": [], "layer": "live", "degraded": text.endswith("1"),
                "search_status": "partial" if text.endswith("3") else "ok"}
    monkeypatch.setattr(ev, "check_forward", check)
    rows = [{"claim": f"claim {i}", "label": "TRUE", "lang": "en", "seeded": False} for i in range(4)]
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    out = ev.run(rows, [], _Llm(), ck, out=lambda *_: None, workers=2)
    assert len(out) == 4                                                    # the run finished
    err = ck["results"]["claim 2"]
    assert err["status"] == "error" and err["got"] is None and err["error"] == "ValueError" and err["layer"] == "error"
    assert ck["results"]["claim 1"]["degraded"] is True and ck["results"]["claim 3"]["search_status"] == "partial"
    assert ck["results"]["claim 0"]["error"] is None and ck["results"]["claim 0"]["ms"] >= 15
    assert all(ck["results"][c]["ms"] >= 0 for c in ck["results"])
    assert ck["degraded_claims"] == 1 and ck["search_failures"] == 1


def test_timing_is_per_claim_under_threads(monkeypatch):
    ev = _run_eval()
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)
    monkeypatch.setattr(ev, "check_forward", lambda text, ret, llm, log=False: (time.sleep(0.05) or
                        {"verdict": "UNVERIFIED", "claims": [], "layer": "live"}))
    rows = [{"claim": f"c{i}", "label": "TRUE", "lang": "en", "seeded": False} for i in range(8)]
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    t0 = time.monotonic()
    ev.run(rows, [], _Llm(), ck, out=lambda *_: None, workers=4)
    wall = time.monotonic() - t0
    ms = [ck["results"][f"c{i}"]["ms"] for i in range(8)]
    assert all(45 <= x < 2000 for x in ms)                  # each claim timed on its own, not the whole batch
    assert wall < 8 * 0.05                                   # really ran concurrently
    assert ev.latency(list(ck["results"].values()))["all"]["n"] == 8


def test_old_checkpoints_without_ms_still_load_and_report(monkeypatch, tmp_path):
    ev = _run_eval()
    cp = tmp_path / "eval_progress.json"
    cp.write_text(json.dumps({"key": {"commit": "c"}, "results": {"old": {"got": "FALSE", "reasons": [], "cites": [], "layer": "live"}},
                              "llm_failures": 0, "search_failures": 0, "no_llm": False}), encoding="utf-8")
    monkeypatch.setattr(ev, "CHECKPOINT", cp)
    ck = ev.load_checkpoint({"commit": "c"})
    assert ck["results"]["old"]["got"] == "FALSE"
    res = [{**r, **ck["results"][r["claim"]]} for r in [{"claim": "old", "label": "FALSE", "lang": "en", "seeded": False}]]
    meta = {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}
    rep = ev.build_report(res, meta, False, "", 0, docs=tmp_path)
    assert "Claims without timing: **1**" in rep


def test_a_run_with_a_timed_out_claim_is_not_clean(monkeypatch, tmp_path):
    ev = _run_eval()
    monkeypatch.setattr(ev, "DOCS", tmp_path)
    monkeypatch.setattr(ev, "ROOT", tmp_path)
    monkeypatch.setattr(ev, "CHECKPOINT", tmp_path / "cache" / "p.json")
    monkeypatch.setattr(ev, "SUMMARY", tmp_path / "s.json")
    monkeypatch.setattr(ev, "load_rows", lambda path=None: [{"claim": "a", "label": "FALSE", "source": "", "lang": "en", "seeded": False,
                                                           "verified_on": "", "note": ""}])
    monkeypatch.setattr(ev, "default_retrievers", lambda: [])
    monkeypatch.setattr(ev, "get_llm", lambda: _Llm())
    monkeypatch.setattr(ev, "git_info", lambda: ("abc", False))
    monkeypatch.setattr(ev, "check_forward", lambda text, ret, llm, log=False: (_ for _ in ()).throw(RuntimeError("x")))
    assert ev.main([]) == 0
    assert not (tmp_path / "s.json").exists() and (tmp_path / "evaluation-fallback-run.md").exists()
    assert "checking raised an error on 1 claims" in (tmp_path / "evaluation-fallback-run.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- data/eval_summary.json
OLD_KEYS = ("n", "correct", "overclaimed_false", "overclaimed_true", "abstained", "abstained_wrong", "commit", "dirty", "date",
            "by_lang", "eval_set_hash", "retrievers", "judges")


def test_eval_summary_keeps_old_keys_and_gains_measures(monkeypatch, tmp_path):
    ev = _run_eval()
    monkeypatch.setattr(ev, "DOCS", tmp_path)
    monkeypatch.setattr(ev, "ROOT", tmp_path)
    monkeypatch.setattr(ev, "CHECKPOINT", tmp_path / "cache" / "p.json")
    monkeypatch.setattr(ev, "SUMMARY", tmp_path / "s.json")
    monkeypatch.setattr(ev, "load_rows", lambda path=None: [
        {"claim": "a", "label": "FALSE", "source": "", "lang": "en", "seeded": False, "verified_on": "", "note": ""},
        {"claim": "b", "label": "TRUE", "source": "", "lang": "hi", "seeded": False, "verified_on": "", "note": ""}])
    monkeypatch.setattr(ev, "default_retrievers", lambda: [])
    monkeypatch.setattr(ev, "get_llm", lambda: _Llm())
    monkeypatch.setattr(ev, "git_info", lambda: ("abc", False))
    answers = {"a": "FALSE", "b": "UNVERIFIED"}
    monkeypatch.setattr(ev, "check_forward", lambda text, ret, llm, log=False: {"verdict": answers[text], "claims": [], "layer": "live",
                                                                                "search_status": "ok", "degraded": False})
    assert ev.main([]) == 0
    s = json.load(open(tmp_path / "s.json", encoding="utf-8"))
    for k in OLD_KEYS:
        assert k in s
    assert s["n"] == 2 and s["correct"] == 1 and s["abstained"] == 1 and s["by_lang"]["hi"]["abstained"] == 1
    m = s["measures"]
    assert m["accuracy"] == {"correct": 1, "n": 2} and m["abstention"] == {"abstained_on_decisive": 1, "decisive_n": 2}
    assert m["failures"]["errors"] == 0 and m["latency"]["all"]["n"] == 2
    rep = (tmp_path / "evaluation.md").read_text(encoding="utf-8")
    assert "## Measures, separately" in rep


def test_dry_run_still_works_and_writes_nothing(monkeypatch, tmp_path, capsys):
    ev = _run_eval()
    monkeypatch.setattr(ev, "DOCS", tmp_path)
    monkeypatch.setattr(ev, "SUMMARY", tmp_path / "s.json")
    monkeypatch.setattr(ev, "load_rows", lambda path=None: [{"claim": "a", "label": "FALSE", "source": "", "lang": "en", "seeded": False,
                                                           "verified_on": "", "note": ""}])
    monkeypatch.setattr(ev, "check_forward", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network in a dry run")))
    assert ev.main(["--dry-run"]) == 0
    assert "DRY RUN" in capsys.readouterr().out and not (tmp_path / "s.json").exists()


def test_per_claim_record_is_written_under_the_checkpoint_lock():
    """Source check: the timing and result are stored inside the same lock that guards the checkpoint save."""
    src = (ROOT / "scripts" / "run_eval.py").read_text(encoding="utf-8")
    body = src.split("def one(i, r):", 1)[1].split("todo = []", 1)[0]
    assert "with lock:" in body and body.index("with lock:") < body.index("save_checkpoint(ckpt)")
    assert "time.monotonic()" in body


# ---------------------------------------------------------------- headline, measures table and JSON agree (defect 1)
def _scenario():
    """10 claims: 2 exact, 1 wrong-not-overclaim, 2 FALSE overclaims, 2 TRUE overclaims, 2 abstentions on decisive labels, 1 ERROR."""
    spec = [("FALSE", "FALSE"), ("TRUE", "TRUE"),                       # exact
            ("FALSE", "MISLEADING"),                                    # wrong, not an overclaim
            ("TRUE", "FALSE"), ("TRUE", "FALSE"),                       # overclaim FALSE
            ("FALSE", "TRUE"), ("FALSE", "TRUE"),                       # overclaim TRUE
            ("TRUE", "UNVERIFIED"), ("FALSE", "UNVERIFIED"),            # abstained on decisive labels
            ("TRUE", "ERROR")]                                          # the check raised
    return [{"claim": f"s{i} {label} {got}", "label": label, "got": got, "lang": "en", "layer": "live", "seeded": False,
             "reasons": [], "cites": [], "ms": 100.0, "degraded": False, "search_status": "ok", "error": None}
            for i, (label, got) in enumerate(spec)]


def _meta():
    return {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}


def test_scenario_headline_table_and_json_agree_exactly(tmp_path):
    ev = _run_eval()
    res = _scenario()
    s = ev.summarize(res)
    m = ev.measures(res, 0)
    rep = ev.build_report(res, _meta(), True, "", 0, docs=tmp_path)
    headline = next(l for l in rep.splitlines() if l.startswith("- Wrong verdicts other than overclaims"))
    table = next(l for l in rep.splitlines() if l.startswith("| Wrong but not an overclaim"))
    table_count = int(table.split("|")[2].strip())
    payload = ev.summary_payload(res, _meta(), "hash", [], 0)
    # counted by hand: 2 correct, 2 FALSE overclaims, 2 TRUE overclaims, 1 wrong-not-overclaim, 2 abstentions, 1 ERROR
    assert (s["n"], s["correct"], s["overclaimed_false"], s["overclaimed_true"], s["abstained"]) == (10, 2, 2, 2, 2)
    assert int(headline.rsplit(": ", 1)[1]) == 1 == table_count == m["wrong_not_overclaim"]["count"]
    assert payload["measures"]["wrong_not_overclaim"]["count"] == 1 == payload["measures"]["wrong_not_overclaim"]["n"] - 9
    assert payload["abstained_wrong"] == 5          # old key, old meaning: 2 + 2 overclaims + 1 wrong verdict; the ERROR is not in it
    assert payload["measures"]["failures"]["errors"] == 1 and payload["measures"]["accuracy"] == {"correct": 2, "n": 10}
    assert "Exact-match accuracy: **2/10**" in rep


def test_an_error_is_not_counted_as_a_wrong_verdict_anywhere():
    ev = _run_eval()
    res = [_row("ERROR", "TRUE", error="ValueError")]
    assert ev.outcome(res[0]) == "error"
    assert ev.summarize(res)["abstained_wrong"] == 0 and ev.summarize(res)["n"] == 1
    assert ev.by_lang(res)["en"] == {"n": 1, "correct": 0, "abstained": 0, "overclaimed_false": 0, "overclaimed_true": 0, "wrong_other": 0}
    assert ev.measures(res)["wrong_not_overclaim"]["count"] == 0


# ---------------------------------------------------------------- exception text: only the class name is kept (D1)
def test_run_keeps_only_the_exception_class_in_the_checkpoint_and_the_failed_table(monkeypatch):
    ev = _run_eval()
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)
    secret = "Q" * 40

    def check(text, ret, llm, log=False):
        raise RuntimeError(f"token {secret} rejected " + "x" * 300)
    monkeypatch.setattr(ev, "check_forward", check)
    rows = [{"claim": "boom", "label": "TRUE", "lang": "en", "seeded": False}]
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    out = ev.run(rows, [], _Llm(), ck, out=lambda *_: None)
    got = ck["results"]["boom"]
    assert got["error"] == "RuntimeError" and got["status"] == "error" and got["got"] is None
    assert "error_msg" not in got and secret not in json.dumps(got)
    text = "\n".join(ev.failed_table(out))
    # the committed table carries no message text: only the exception class name in the Error column
    assert "Error message" not in text and "rejected" not in text and secret not in text and "[redacted]" not in text
    assert "| Error |" in text and "RuntimeError" in text


# ---------------------------------------------------------------- Why column (defect 4)
def test_why_column_gives_every_reason_and_failed_table_shows_it():
    ev = _run_eval()
    cases = {
        "judge problem, wrong verdict": _row("MISLEADING", "TRUE", degraded=True),
        "search failure, overclaim": _row("FALSE", "TRUE", search_status="partial"),
        "abstained": _row("UNVERIFIED", "FALSE"),
        "overclaim": _row("TRUE", "FALSE"),
        "error": _row("ERROR", "TRUE", error="KeyError"),
        "judge problem, search failure, abstained": _row("UNVERIFIED", "TRUE", degraded=True, search_status="down"),
    }
    for expected, r in cases.items():
        r["claim"] = f"why {expected}"
        assert ", ".join(ev.why_tags(r)) == expected
    text = "\n".join(ev.failed_table(list(cases.values()) + [_row("FALSE", "FALSE")]))
    assert "| Why |" in text
    for expected, r in cases.items():
        assert f"| {expected} |" in text
    why_cells = [l.split("|")[8].strip() for l in text.splitlines() if l.startswith("| why ")]
    assert len(why_cells) == len(cases) and all(c != "-" for c in why_cells)        # every listed row has a reason


# ---------------------------------------------------------------- site card label (defect 3) and docs (defects 3 and 5)
def test_report_says_what_the_site_card_abstained_counts():
    ev = _run_eval()
    res = [_row("UNVERIFIED", "UNVERIFIED"), _row("UNVERIFIED", "UNVERIFIED"), _row("UNVERIFIED", "TRUE"), _row("FALSE", "FALSE")]
    rep = ev.build_report(res, _meta(), False, "", 0, docs=None)
    assert "The site card's 'abstained' figure counts every such UNVERIFIED answer across all labels" in rep
    assert "the abstention rate in Measures counts only TRUE/FALSE-labelled claims" in rep
    assert "The 2 UNVERIFIED-labelled controls are correct" in rep


def test_method_doc_explains_the_card_number_and_the_layers():
    doc = (ROOT / "docs" / "evaluation-method.md").read_text(encoding="utf-8")
    assert "Site card \"abstained\"" in doc and "only because the set has no MISLEADING rows" in doc
    latency_line = next(l for l in doc.splitlines() if l.startswith("- **Latency**"))
    assert "`mixed`" in latency_line and "`error`" in latency_line
