"""scripts/run_eval.py: no exception message text is stored or printed (lone-surrogate safety, the UNVERIFIED label line, --workers help).

Decision (D1): an exception contributes only its class name ('error') and the canonical 'error_category'. The message text is
never kept, so no redaction code exists and nothing redacted can leak. These tests try secret-shaped messages through every
output the evaluation writes."""
import importlib.util, json, pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_eval():
    spec = importlib.util.spec_from_file_location("run_eval_redaction_under_test", ROOT / "scripts" / "run_eval.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Llm:
    failures = 0


META = {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}
KEY = {"schema_version": 1, "mode": "live", "commit": "c", "eval_hash": "h", "code_hash": "x", "config_hash": "y"}


# ---------------------------------------------------------------- no exception message text is stored or printed (D1)
SECRETS = ["Zk4Pq8Lw2Xv9Tm1Rb7", "Qm7Vb3Nx9Lk2Pw8Rt5Zd", "Hj6Wc1Ys4Gt8Fn2Ke9Ma"]      # 19-20 character, secret-shaped
TEMPLATES = [
    "https://deployer:{s}@ci.example.internal/path failed",          # credentials in a URL
    "token {s} expired",                                              # a token after a key word
    "401 invalid key {s}",                                            # an API key in plain text
    "password={s} rejected",                                          # a key=value secret
    "Forwarded text: {s} was shared with us in a chat",               # forwarded user text
    "contact asha.{s}@example.com about the failure",                 # an email address
    "call +91 98765 {s} to retry",                                    # a phone number
    "file /home/{s}/work/checkout/run.py is missing",                 # a path with a user name
    "jwt eyJhbGciOiJIUzI1NiJ9.{s}.sig rejected",                      # a JWT-like value
    "Authorization: Bearer {s} refused",                              # a bearer token
]
CASES = [(template.format(s=secret), secret, RuntimeError if j % 2 else TimeoutError)
         for j, (template, secret) in enumerate((t, s) for t in TEMPLATES for s in SECRETS)]     # 10 templates x 3 secrets = 30


def test_there_are_thirty_secret_shaped_cases():
    assert len(CASES) == 30 and len({message for message, _, _ in CASES}) == 30


@pytest.mark.parametrize("workers,offline", [(1, False), (3, False), (1, True)])
def test_no_exception_message_text_reaches_the_checkpoint_report_summary_artifact_or_console(monkeypatch, tmp_path, workers, offline):
    ev = _run_eval()
    checkpoint_path = tmp_path / "eval_progress.json"
    monkeypatch.setattr(ev, "CHECKPOINT", checkpoint_path)
    raised = {}

    def check(text, ret, llm, log=False):
        message, secret, exc = raised[text]
        raise exc(message)
    monkeypatch.setattr(ev, "check_forward", check)
    rows = [{"claim": f"claim {i}", "label": "TRUE", "lang": "en", "seeded": False} for i in range(len(CASES))]
    for row, (message, secret, exc) in zip(rows, CASES):
        raised[row["claim"]] = (message, secret, exc)
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    console = []
    out = ev.run(rows, [], _Llm(), ck, out=console.append, workers=workers, offline=offline)

    shipped = [json.dumps(ck, ensure_ascii=False), "\n".join(console)]
    if checkpoint_path.exists():
        shipped.append(checkpoint_path.read_text(encoding="utf-8"))
    shipped.append(ev.build_report(out, META, False, "", 0, docs=tmp_path))
    shipped.append(json.dumps(ev.summary_payload(out, META, "h", [], 0), ensure_ascii=False))
    shipped.append(json.dumps(ev.build_artifact(out, KEY, {}, False, "", False, len(rows)), ensure_ascii=False))
    text = "\n".join(shipped)
    assert "error_msg" not in text
    for message, secret, _ in CASES:
        assert secret not in text, secret
        assert message not in text, message
    # the class name is what is kept and shown
    assert "RuntimeError" in text and "TimeoutError" in text
    for result in ck["results"].values():
        assert set(result) >= {"error", "error_category"} and result["error"] in ("RuntimeError", "TimeoutError")
        assert result["got"] is None and result["status"] == "error"


def test_error_rows_have_no_message_field_and_keep_the_class_name_only():
    ev = _run_eval()
    row = ev._error_row("check_exception", error="ValueError")
    assert "error_msg" not in row and row["error"] == "ValueError" and row["error_category"] == "check_exception"
    assert row["status"] == "error" and row["got"] is None


def test_the_redaction_code_and_the_message_field_are_gone_from_the_code_and_the_method_doc():
    src = (ROOT / "scripts" / "run_eval.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "evaluation-method.md").read_text(encoding="utf-8")
    for name in ("error_msg", "safe_error_message", "redact_secrets"):
        assert name not in src and name not in doc, name
    assert "no exception message is stored or printed" in doc.lower()


# ---------------------------------------------------------------- lone surrogates never break the run or the report
def test_a_lone_surrogate_in_an_exception_does_not_break_the_run_or_the_report(monkeypatch, tmp_path):
    ev = _run_eval()
    monkeypatch.setattr(ev, "CHECKPOINT", tmp_path / "ck.json")

    def check(text, ret, llm, log=False):
        if text == "boom":
            raise Exception("bad \ud800 text")
        return {"verdict": "FALSE", "claims": [], "layer": "live"}
    monkeypatch.setattr(ev, "check_forward", check)
    rows = [{"claim": "boom", "label": "TRUE", "lang": "en", "seeded": False},
            {"claim": "fine", "label": "FALSE", "lang": "en", "seeded": False}]
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    out = ev.run(rows, [], _Llm(), ck, out=lambda *_: None)
    assert len(out) == 2 and ck["results"]["boom"]["status"] == "error" and ck["results"]["boom"]["got"] is None
    assert ck["results"]["boom"]["error"] == "Exception"
    saved = json.loads((tmp_path / "ck.json").read_text(encoding="utf-8"))      # the checkpoint was written
    assert saved["results"]["boom"]["error"] == "Exception" and "error_msg" not in saved["results"]["boom"]

    rep = ev.build_report(out, META, False, "", 0, docs=tmp_path)
    (tmp_path / "report.md").write_text(rep, encoding="utf-8")                 # the report writer survives too
    json.dumps(ev.summary_payload(out, META, "h", [], 0), ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------- the UNVERIFIED label line
def _row(got, label):
    return {"claim": f"{label} {got}", "label": label, "got": got, "lang": "en", "layer": "live", "seeded": False, "reasons": [], "cites": []}


def test_unverified_label_line_counts_controls_answered_as_expected_and_drops_the_correct_wording():
    ev = _run_eval()
    res = [_row("UNVERIFIED", "UNVERIFIED")] * 9 + [_row("TRUE", "UNVERIFIED")] * 2 + [_row("TRUE", "TRUE")]
    rep = ev.build_report(res, META, False, "", 0, docs=None)
    assert "- Label UNVERIFIED (controls): 9/11 answered UNVERIFIED as expected" in rep
    assert "Label UNVERIFIED: 9/11 correct" not in rep and "9 abstained as UNVERIFIED" not in rep


def test_unverified_label_line_is_computed_not_hard_coded():
    ev = _run_eval()
    res = [_row("UNVERIFIED", "UNVERIFIED")] * 3 + [_row("FALSE", "UNVERIFIED")] * 1
    rep = ev.build_report(res, META, False, "", 0, docs=None)
    assert "- Label UNVERIFIED (controls): 3/4 answered UNVERIFIED as expected" in rep


# ---------------------------------------------------------------- --workers help text
def test_workers_help_does_not_claim_an_unmeasured_speed_up():
    src = (ROOT / "scripts" / "run_eval.py").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if '"--workers"' in l)
    assert "4-5x" not in line and "faster; stays inside provider limits at 3" in line
