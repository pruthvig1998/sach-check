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
    assert "Abstention rate" in rep and "| 1 | 4 decisive-label claims | 25.0% |" in rep
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
    assert err["got"] == "ERROR" and err["error"] == "ValueError" and err["layer"] == "error"
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
