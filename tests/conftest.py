import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SACH_LEDGER", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("SACH_CACHE_DIR", str(tmp_path / "cache"))
