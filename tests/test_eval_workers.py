"""scripts/run_eval.py --workers: checking claims concurrently gives the same results and counters as a sequential run."""
import importlib.util, pathlib, threading, time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_eval():
    spec = importlib.util.spec_from_file_location("run_eval_workers_under_test", ROOT / "scripts" / "run_eval.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Llm:
    failures = 0


def _rows(n=12):
    return [{"claim": f"claim {i}", "label": "FALSE" if i % 2 else "TRUE", "lang": "en", "seeded": False} for i in range(n)]


def _fake_check(active, peak):
    def check(text, ret, llm, log=False):
        with peak["lock"]:
            active[0] += 1
            peak["max"] = max(peak["max"], active[0])
        time.sleep(0.03)
        i = int(text.split()[-1])
        with peak["lock"]:
            active[0] -= 1
        status = "partial" if i % 5 == 0 else "ok"
        return {"verdict": "FALSE" if i % 2 else "UNVERIFIED", "claims": [{"reason_code": "r%d" % i, "citations": [{"url": "u%d" % i}]}],
                "layer": "live", "search_status": status}
    return check


def _go(monkeypatch, workers):
    ev = _run_eval()
    peak = {"max": 0, "lock": threading.Lock()}
    monkeypatch.setattr(ev, "check_forward", _fake_check([0], peak))
    saved = []
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: saved.append(len(c["results"])))
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    lines = []
    out = ev.run(_rows(), [], _Llm(), ck, out=lines.append, workers=workers)
    return out, ck, peak["max"], saved, lines


def test_parallel_run_matches_the_sequential_run(monkeypatch):
    seq, ck1, peak1, _, _ = _go(monkeypatch, 1)
    par, ck4, peak4, saved, lines = _go(monkeypatch, 4)
    assert peak1 == 1 and 1 < peak4 <= 4                      # really concurrent, never above the requested number
    assert [r["claim"] for r in par] == [r["claim"] for r in seq]       # results come back in eval-set order
    assert par == seq and ck4["results"] == ck1["results"]
    assert ck4["search_failures"] == ck1["search_failures"] == 3        # claims 0, 5, 10 lost search; counted exactly once each under threads
    assert saved and saved[-1] == 12 and sorted(saved) == list(range(1, 13))     # every claim checkpointed exactly once
    assert len(lines) == 12 and all("->" in l for l in lines)


def test_resumed_claims_are_not_rechecked_in_parallel(monkeypatch):
    ev = _run_eval()
    calls = []
    monkeypatch.setattr(ev, "check_forward", lambda text, ret, llm, log=False: calls.append(text) or
                        {"verdict": "FALSE", "claims": [], "layer": "live"})
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)
    ck = {"key": {}, "results": {"claim 0": {"got": "TRUE", "reasons": [], "cites": [], "layer": "live"}}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    out = ev.run(_rows(4), [], _Llm(), ck, out=lambda *_: None, workers=3)
    assert "claim 0" not in calls and len(calls) == 3 and out[0]["got"] == "TRUE"


def test_a_failing_worker_raises_like_a_sequential_run(monkeypatch):
    ev = _run_eval()
    monkeypatch.setattr(ev, "check_forward", lambda text, ret, llm, log=False: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    try:
        ev.run(_rows(3), [], _Llm(), ck, out=lambda *_: None, workers=2)
    except RuntimeError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("worker error was swallowed")


def test_workers_flag_exists_and_defaults_to_sequential():
    src = (ROOT / "scripts" / "run_eval.py").read_text(encoding="utf-8")
    assert '"--workers"' in src and "default=1" in src and "workers=a.workers" in src
