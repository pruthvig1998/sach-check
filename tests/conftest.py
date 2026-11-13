import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SACH_LEDGER", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("SACH_CACHE_DIR", str(tmp_path / "cache"))
    # Admission control (sach/limits.py) is covered by tests/test_scale.py; other tests run many live checks in a minute, so switch the global budget off.
    monkeypatch.setenv("SACH_MAX_LIVE_PER_MIN", "0")
    monkeypatch.setenv("SACH_MAX_LIVE_PER_DAY", "0")
    # A developer's real .env (loaded by `import sach`) must never reach the network from the test suite: tests inject fakes where they need one.
    for k in ("GOOGLE_TRANSLATE_API_KEY", "GOOGLE_FACTCHECK_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    # The link checker's optional hostname lookups (RDAP, Safe Browsing, short-link expansion) never run in tests unless a test injects a fake opener.
    monkeypatch.setenv("SACH_LINKCHECK_NO_NETWORK", "1")
    monkeypatch.delenv("GOOGLE_SAFEBROWSING_API_KEY", raising=False)
    from sach import limits
    limits.reset_memory()
