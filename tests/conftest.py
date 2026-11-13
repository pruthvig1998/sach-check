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
    from sach import limits
    limits.reset_memory()
