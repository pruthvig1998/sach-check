"""Check every configured AI judge: does each key/model answer, and does it pass a tiny quality probe?
Usage: python scripts/check_llm.py     (reads .env)
Vertex AI (GOOGLE_SA_JSON set) is probed like the others; its calls are billed and count toward SACH_VERTEX_MAX_PER_DAY."""
import os, pathlib, sys, time
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root)); os.chdir(root)
import sach  # noqa: loads .env
from sach.llm import build_judges, _Judge, parse_reply
from sach.stance import validate_stance

DEBUNK_T = "No reduction in retirement age of Central Government employees, PIB Fact Check busts fake news"
DEBUNK_X = "A media report said the retirement age would be reduced to 50 years. This is fake; no such proposal exists."
PROBES = [("retirement age to 50", DEBUNK_T, DEBUNK_X, "Central Government will reduce the retirement age of employees to 50 years.", "contradicts"),
          ("unrelated page (must be none)", "Cabinet approves NBS rates for fertilizers", "The Union Cabinet approved nutrient based subsidy rates for Rabi 2026-27.",
           "The Cabinet has approved declaring the 14th of every month as National Mango Day.", "none")]

judges = build_judges()
if not judges:
    sys.exit("No AI keys found. Set GEMINI_API_KEY (free: aistudio.google.com/apikey), (or GOOGLE_SA_JSON for Vertex AI), and optionally GROQ_API_KEY / OPENROUTER_API_KEY / MISTRAL_API_KEY in .env")
bad = 0
for j in judges:
    print(f"\n== {j.name}  ({', '.join(getattr(j, 'models', []) or ['single model'])})")
    if not isinstance(j, _Judge):
        print("   (not probed: single-model judge)"); continue
    for m in j.models:
        t = time.time()
        try:
            out = j._raw(m, "Reply with the single word OK.", "ping", 10).strip()
            print(f"   {m:48} OK   {time.time()-t:4.1f}s  -> {out[:20]!r}")
        except Exception as e:
            code = getattr(e, "code", type(e).__name__); bad += 1
            print(f"   {m:48} FAIL {code}  {(e.read().decode()[:90].replace(chr(10), ' ') if hasattr(e, 'read') else str(e)[:90])}")
            continue
        for name, title, text, claim, want in PROBES:
            try:
                st, q = parse_reply(j._raw(m, __import__('sach.llm', fromlist=['PROMPT']).PROMPT,
                                           __import__('sach.llm', fromlist=['_user'])._user(claim, title, text), 200))
                got = validate_stance(st, q, claim, title, text)
            except Exception as e:
                got = f"error {type(e).__name__}"
            print(f"      probe {name:32} {'PASS' if got == want else 'FAIL'} (got {got}, want {want})")
            bad += got != want
print("\nAll judges healthy." if not bad else f"\n{bad} problem(s). A model that FAILs is skipped automatically at runtime; fix names with SACH_<PROVIDER>_MODELS in .env.")
