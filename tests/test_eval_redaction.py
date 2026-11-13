"""scripts/run_eval.py: error-message redaction (defect A), lone-surrogate safety (B), the UNVERIFIED label line (C), --workers help (E)."""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_eval():
    spec = importlib.util.spec_from_file_location("run_eval_redaction_under_test", ROOT / "scripts" / "run_eval.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Llm:
    failures = 0


JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
       "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")


# ---------------------------------------------------------------- A: redaction of keys, tokens and passwords
def test_google_key_in_a_query_string_is_redacted():
    ev = _run_eval()
    e = Exception("403 Forbidden: https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"
                  "?key=AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBI3")
    msg = ev.safe_error_message(e)
    assert "AIzaSyD" not in msg and "a7eZSW0jkFMBI3" not in msg and "9tSrke72" not in msg
    assert "[redacted]" in msg


def test_anthropic_key_with_dashes_and_underscores_is_redacted():
    ev = _run_eval()
    key = "sk-ant-api03-Qx7_Lm2Vb9-Zr4Tn8Wk3Pd6Hj1Gf5Ds0Ap_Yt2Mu8Xc4Ri7Eo9Ng3Bl6Ka1Sh-Wv5Ju0Qe2Lo8Ta4Zb"
    msg = ev.safe_error_message(Exception("401 invalid key " + key))
    assert "Qx7_Lm2" not in msg and "Ta4Zb" not in msg and "sk-ant" not in msg and "[redacted]" in msg


def test_jwt_including_its_signature_is_redacted():
    ev = _run_eval()
    msg = ev.safe_error_message(Exception(f"jwt rejected: {JWT} expired"))
    assert "dozjgNryP4J3jVmNHl0w5N" not in msg and "eyJhbGci" not in msg and "[redacted]" in msg
    assert "expired" in msg


def test_aws_style_secret_with_slashes_is_redacted():
    ev = _run_eval()
    msg = ev.safe_error_message(Exception("secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"))
    assert "wJalrXUtnFEMI" not in msg and "EXAMPLEKEY" not in msg and "[redacted]" in msg


def test_password_assignment_is_redacted():
    ev = _run_eval()
    msg = ev.safe_error_message(Exception("login failed password=hunter2supersecret"))
    assert "hunter2supersecret" not in msg and "password=[redacted]" in msg


def test_api_key_query_parameter_is_redacted_and_the_host_path_kept():
    ev = _run_eval()
    msg = ev.safe_error_message(Exception("GET https://api.example.com/v1/x?api_key=abc123 failed"))
    assert "abc123" not in msg and "api.example.com/v1/x" in msg and "api_key=[redacted]" in msg


def test_authorization_header_and_bearer_tokens_are_redacted():
    ev = _run_eval()
    assert "abc" not in ev.safe_error_message(Exception("Authorization: Bearer abc")).split()[-1]
    assert ev.safe_error_message(Exception("Authorization: Bearer abc")).endswith("[redacted]")
    msg = ev.safe_error_message(Exception(f"Bearer {JWT}"))
    assert "eyJhbGci" not in msg and "[redacted]" in msg


def test_token_colon_and_api_key_header_are_redacted():
    ev = _run_eval()
    assert "abcd1234" not in ev.safe_error_message(Exception("token: abcd1234"))
    msg = ev.safe_error_message(Exception("header x-goog-api-key: AIzaSyD9tSrke72PouQMnMX"))
    assert "AIzaSyD9" not in msg and "[redacted]" in msg


def test_key_value_secrets_are_redacted_case_insensitively_and_at_any_length():
    ev = _run_eval()
    for text, secret in [("PASSWORD=ab", "ab"), ("Access_Token=xy9", "xy9"), ("Passwd=zz", "zz"),
                         ("pwd=q", "q"), ("SECRET=short1", "short1"), ("auth=tiny", "tiny")]:
        msg = ev.safe_error_message(Exception(text))
        assert f"={secret}" not in msg and "[redacted]" in msg, (text, msg)


def test_ordinary_text_and_urls_are_not_over_redacted():
    ev = _run_eval()
    assert ev.safe_error_message(Exception("https://pib.gov.in/PressReleasePage.aspx?PRID=2110356")) == \
        "https://pib.gov.in/PressReleasePage.aspx?PRID=2110356"
    assert ev.safe_error_message(Exception("ConnectionResetError")) == "ConnectionResetError"
    assert ev.safe_error_message(Exception("TimeoutError")) == "TimeoutError"
    assert "ConnectionResetError" in ev.safe_error_message(Exception("ConnectionResetError: peer closed"))


def test_redaction_runs_before_truncation_so_no_secret_survives_the_cut():
    ev = _run_eval()
    secret = "password=" + "Hunter2" * 5          # fully inside the first 160 characters
    msg = ev.safe_error_message(Exception(("x " * 70) + secret))
    assert "Hunter2" not in msg and len(msg) <= 160
    msg2 = ev.safe_error_message(Exception("pre " + "a" * 150 + " key=SECRETVALUE123"))
    assert "SECRETVALUE123" not in msg2 and len(msg2) <= 160


def test_keys_are_redacted_in_the_checkpoint_and_the_failed_table(monkeypatch):
    ev = _run_eval()
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)

    def check(text, ret, llm, log=False):
        raise RuntimeError("403: https://generativelanguage.googleapis.com/v1beta/x:generateContent?key=AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBI3")
    monkeypatch.setattr(ev, "check_forward", check)
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    out = ev.run([{"claim": "c", "label": "TRUE", "lang": "en", "seeded": False}], [], _Llm(), ck, out=lambda *_: None)
    text = "\n".join(ev.failed_table(out))
    assert "AIzaSyD" not in text and "a7eZSW0jkFMBI3" not in text and "9tSrke72" not in text
    assert "AIzaSyD" not in ck["results"]["c"]["error_msg"]


# ---------------------------------------------------------------- B: lone surrogates never break the run or the report
def test_a_lone_surrogate_in_an_error_is_utf8_encodable_and_the_run_survives(monkeypatch, tmp_path):
    ev = _run_eval()
    msg = ev.safe_error_message(Exception("bad \ud800 text"))
    msg.encode("utf-8")                                  # must not raise
    assert "bad" in msg and "text" in msg

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
    assert len(out) == 2 and ck["results"]["boom"]["got"] == "ERROR"
    saved = json.loads((tmp_path / "ck.json").read_text(encoding="utf-8"))      # the checkpoint was written
    assert saved["results"]["boom"]["error_msg"].encode("utf-8")

    rep = ev.build_report(out, {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}, False, "", 0, docs=tmp_path)
    (tmp_path / "report.md").write_text(rep, encoding="utf-8")                 # the report writer survives too
    json.dumps(ev.summary_payload(out, {"commit": "c", "dirty": False, "date": "d", "mode": "m", "retrievers": [], "judges": []}, "h", [], 0),
               ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------- A2: quoted, JSON and repr key forms; symbol tokens after a key
def test_quoted_json_and_repr_key_forms_are_redacted():
    ev = _run_eval()
    cases = [
        ('{"password": "correcthorsebatterystaple"}', "correcthorsebatterystaple"),
        ("{'api_key': 'Abcdefghijklmnopqrstuvwx'}", "Abcdefghijklmnopqrstuvwx"),
        ('token "Zx9Lm2Qp7Rt4Vb8Nc1Wd5Yh6Jk3Gf0Ms"', "Zx9Lm2Qp7Rt4Vb8Nc1Wd5Yh6Jk3Gf0Ms"),
        ("secret='plainsecretvalue'", "plainsecretvalue"),
        ("headers={'Authorization': 'Basic dXNlcjpwYXNz'}", "dXNlcjpwYXNz"),
    ]
    for text, secret in cases:
        msg = ev.safe_error_message(Exception(text))
        assert secret not in msg and "[redacted]" in msg, (text, msg)


def test_a_symbol_token_of_20_to_27_characters_directly_after_a_key_name_is_redacted():
    ev = _run_eval()
    upper = ev.safe_error_message(Exception("token ABCDEFGHIJKLMNOPQRST-UVWX rejected"))
    lower = ev.safe_error_message(Exception("api_key abcdefghijklmnopqr-stuvwx rejected"))
    assert "ABCDEFGHIJKLMNOPQRST" not in upper and "[redacted]" in upper and "rejected" in upper
    assert "abcdefghijklmnopqr" not in lower and "[redacted]" in lower and "rejected" in lower


# ---------------------------------------------------------------- A3: the committed report and summary carry no exception text
LEAK_SECRETS = [
    "AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBI3",
    "sk-ant-api03-Qx7_Lm2Vb9-Zr4Tn8Wk3Pd6Hj1Gf5Ds0Ap_Yt2Mu8Xc4Ri7Eo9Ng3Bl6Ka1Sh-Wv5Ju0Qe2Lo8Ta4Zb",
    JWT,
    "correcthorsebatterystaple",
    "Zq8LmN2pRt5vWx9yBc3dFg7hJk1nPq4s",
    "9fK2mQ7xLp4Rt8Vn3Zc6Wb1Ys5Gd0Hj",
]


def test_committed_report_and_summary_contain_no_exception_text(monkeypatch, tmp_path):
    ev = _run_eval()
    monkeypatch.setattr(ev, "save_checkpoint", lambda c: None)
    msg = (f'AIza key {LEAK_SECRETS[0]} and sk {LEAK_SECRETS[1]} jwt {LEAK_SECRETS[2]} '
           f'body {{"password": "{LEAK_SECRETS[3]}"}} key={LEAK_SECRETS[4]} Bearer {LEAK_SECRETS[5]}')

    def check(text, ret, llm, log=False):
        raise TimeoutError(msg)
    monkeypatch.setattr(ev, "check_forward", check)
    rows = [{"claim": "c", "label": "TRUE", "lang": "en", "seeded": False}]
    ck = {"key": {}, "results": {}, "llm_failures": 0, "search_failures": 0, "no_llm": False}
    out = ev.run(rows, [], _Llm(), ck, out=lambda *_: None)
    meta = {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}
    report = ev.build_report(out, meta, False, "", 0, docs=tmp_path)
    summary = json.dumps(ev.summary_payload(out, meta, "h", [], 0), ensure_ascii=False)
    shipped = report + "\n" + summary
    assert "TimeoutError" in report and "| Error |" in report and "Error message" not in report
    for secret in LEAK_SECRETS:
        for i in range(len(secret) - 11):
            window = secret[i:i + 12]
            assert window not in shipped, window
    assert "[redacted]" not in shipped and "rejected" not in shipped


# ---------------------------------------------------------------- C: the UNVERIFIED label line
def _row(got, label):
    return {"claim": f"{label} {got}", "label": label, "got": got, "lang": "en", "layer": "live", "seeded": False, "reasons": [], "cites": []}


def test_unverified_label_line_counts_controls_answered_as_expected_and_drops_the_correct_wording():
    ev = _run_eval()
    meta = {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}
    res = [_row("UNVERIFIED", "UNVERIFIED")] * 9 + [_row("TRUE", "UNVERIFIED")] * 2 + [_row("TRUE", "TRUE")]
    rep = ev.build_report(res, meta, False, "", 0, docs=None)
    assert "- Label UNVERIFIED (controls): 9/11 answered UNVERIFIED as expected" in rep
    assert "Label UNVERIFIED: 9/11 correct" not in rep and "9 abstained as UNVERIFIED" not in rep


def test_unverified_label_line_is_computed_not_hard_coded():
    ev = _run_eval()
    meta = {"commit": "c", "dirty": False, "date": "2026-11-13", "mode": "m", "retrievers": [], "judges": []}
    res = [_row("UNVERIFIED", "UNVERIFIED")] * 3 + [_row("FALSE", "UNVERIFIED")] * 1
    rep = ev.build_report(res, meta, False, "", 0, docs=None)
    assert "- Label UNVERIFIED (controls): 3/4 answered UNVERIFIED as expected" in rep


# ---------------------------------------------------------------- E: --workers help text
def test_workers_help_does_not_claim_an_unmeasured_speed_up():
    src = (ROOT / "scripts" / "run_eval.py").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if '"--workers"' in l)
    assert "4-5x" not in line and "faster; stays inside provider limits at 3" in line
