"""Work through claims people asked about while Sach was busy, most asked first. Dry run by default.
  python scripts/work_demand_queue.py              # list what would be checked
  python scripts/work_demand_queue.py --run -n 5   # check up to 5 (uses the live budget; stops at half the day's cap)
Needs the same environment as the site (store and provider keys). Never changes verdict rules: it calls the normal pipeline."""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sach import demandq
from sach.pipeline import check_forward
from sach.retrieve import default_retrievers
from sach.llm import get_llm

ap = argparse.ArgumentParser()
ap.add_argument("--run", action="store_true"); ap.add_argument("-n", type=int, default=5)
a = ap.parse_args()
r, llm = default_retrievers(), get_llm()
print(json.dumps(demandq.work(lambda t: check_forward(t, r, llm), max_checks=a.n, dry_run=not a.run), indent=1))
