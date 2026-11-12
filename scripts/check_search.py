"""Check every web-search provider: does each configured key answer one small real query?
Prints OK / out of credits (402) / rate limited / auth error / no key per provider. Never prints a key.
Usage: python scripts/check_search.py     (reads .env)
Exit code 1 if any configured provider is not OK."""
import os, pathlib, sys, time, urllib.error
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
import sach  # noqa: loads .env
from sach.search import BraveSearch, TavilySearch

PROBE = "site:pib.gov.in PIB fact check"

def classify(err) -> str:
    """Plain label for a failure. Looks only at the error's type and HTTP code, never at its text (which could echo a URL)."""
    code = getattr(err, "code", None)
    if code in (402, 432, 433):
        return f"out of credits ({code})"
    if code == 429:
        return "rate limited (429)"
    if code in (401, 403):
        return f"auth error ({code})"
    if isinstance(err, urllib.error.HTTPError):
        return f"HTTP error ({code})"
    return f"unreachable ({type(err).__name__})"

def check(providers=None, out=print) -> int:
    """providers: list of (name, provider-or-None). None means no key. Returns the number of problems."""
    if providers is None:
        providers = [("brave", BraveSearch(os.environ["BRAVE_API_KEY"]) if os.environ.get("BRAVE_API_KEY") else None),
                     ("tavily", TavilySearch(os.environ["TAVILY_API_KEY"]) if os.environ.get("TAVILY_API_KEY") else None)]
    bad = configured = 0
    for name, p in providers:
        if p is None:
            out(f"{name:8} no key (set {name.upper()}_API_KEY in .env)")
            continue
        configured += 1
        t = time.time()
        try:
            n = len(p.search(PROBE, 3))
            out(f"{name:8} OK   {time.time() - t:4.1f}s  {n} result(s)")
        except Exception as e:
            bad += 1
            out(f"{name:8} FAIL {classify(e)}")
    if not configured:
        out("\nNo search keys: Sach runs on its built-in PIB list only (search status 'off').")
    elif bad:
        out(f"\n{bad} problem(s). A failing provider is skipped automatically at runtime (402/401/403: for 6 hours; 429: for its Retry-After).")
    else:
        out("\nAll configured search providers healthy.")
    return bad

if __name__ == "__main__":
    sys.exit(1 if check() else 0)
