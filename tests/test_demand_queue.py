import pytest
from test_scale import FakeStore
from sach import demandq, limits, popularity
CLAIM = "The government will give Rs 5000 to every woman under a new scheme."

@pytest.fixture(autouse=True)
def _c(monkeypatch):
    monkeypatch.delenv("SACH_DEMAND_QUEUE", raising=False); monkeypatch.delenv("SACH_QUEUE_MIN_ASKS", raising=False)
    monkeypatch.setenv("SACH_MAX_LIVE_PER_MIN", "50"); monkeypatch.setenv("SACH_MAX_LIVE_PER_DAY", "500")
    limits.reset_memory()

class ListStore(FakeStore):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.lists = {}
    def push(self, name, value, cap=500): self.lists.setdefault(name, []).append(value)
    def items(self, name): return list(self.lists.get(name, []))

def _fs():
    return ListStore()

def test_a_claim_is_queued_only_after_min_asks_and_keeps_only_the_claim_sentence():
    st = _fs()
    for _ in range(4):
        demandq.note("Good morning 🌹 forwarded many times\n" + CLAIM, st)
    assert demandq.pending(st) == []
    demandq.note("Good morning 🌹 forwarded many times\n" + CLAIM, st)
    rows = demandq.pending(st)
    assert len(rows) == 1 and rows[0]["claims"] and "Good morning" not in " ".join(rows[0]["claims"])

def test_switch_off_and_store_failure_never_raise():
    st = _fs()
    demandq.note(CLAIM, ListStore(broken=True))
    import os; os.environ["SACH_DEMAND_QUEUE"] = "0"
    try:
        for _ in range(6): demandq.note(CLAIM, st)
    finally:
        del os.environ["SACH_DEMAND_QUEUE"]
    assert demandq.pending(st) == []

def test_work_checks_most_asked_first_marks_done_and_dry_run_spends_nothing():
    st = _fs()
    for _ in range(5): demandq.note(CLAIM, st)
    assert demandq.work(lambda t: {}, st=st)[0]["action"] == "would_check"     # dry run
    seen = []
    out = demandq.work(lambda t: seen.append(t) or {"verdict": "UNVERIFIED"}, st=st, dry_run=False)
    assert out[0]["action"] == "checked" and seen and demandq.pending(st) == []

def test_work_stops_at_the_reserve_and_when_busy(monkeypatch):
    st = _fs()
    for _ in range(5): demandq.note(CLAIM, st)
    monkeypatch.setattr(limits, "usage", lambda s=None, now=None: {"day_used": 300})
    assert demandq.work(lambda t: {}, st=st, dry_run=False)[0]["action"] == "stopped_reserve"
    assert len(demandq.pending(st)) == 1                                       # still waiting

def test_record_unchecked_feeds_the_queue():
    st = _fs()
    for _ in range(5): popularity.record_unchecked(CLAIM, "day", st=st)
    assert demandq.size(st) == 1


def test_stored_claim_has_no_phone_number_or_handle():
    st = _fs()
    c = "Call 98765 43210 or pay scam@upi to get the Rs 5000 scheme benefit now."
    for _ in range(5): demandq.note(c, st)
    stored = " ".join(demandq.pending(st)[0]["claims"])
    assert "98765" not in stored and "scam@upi" not in stored


def test_size_uses_counters_and_a_cached_unverified_answer_does_not_finish_a_claim(monkeypatch):
    from sach import cache
    st = _fs()
    for _ in range(5): demandq.note(CLAIM, st)
    assert demandq.size(st) == 1
    monkeypatch.setattr(cache, "lookup_by_claims", lambda *a, **k: {"verdict": "UNVERIFIED", "claims": []})
    monkeypatch.setattr(cache, "lookup", lambda *a, **k: {"verdict": "UNVERIFIED", "claims": []})
    monkeypatch.setattr(limits, "admit", lambda *a, **k: limits.Admission("free"))
    out = demandq.work(lambda t: {}, st=st, dry_run=False)
    assert out[0]["action"] == "skipped_cached_unverified" and demandq.size(st) == 1


def test_a_result_that_was_not_stored_stays_queued():
    st = _fs()
    for _ in range(5): demandq.note(CLAIM, st)
    out = demandq.work(lambda t: {"verdict": "UNVERIFIED", "degraded": True}, st=st, dry_run=False)
    assert out[0]["action"] == "not_stored_kept_queued" and demandq.size(st) == 1
