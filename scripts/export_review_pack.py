"""Export every Hindi and Telugu string the site shows, next to its English source, for a native-speaker review.
Writes docs/language-review-pack.csv (open it in Google Sheets or Excel). Run: python scripts/export_review_pack.py
Strings come straight from the code tables, so the pack cannot drift from what users see."""
import csv, importlib, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULES = ["i18n", "match", "voice", "scamsigns", "models", "linkcheck", "honesty", "share", "report", "card", "telegram_bot"]
LANGS = ("en", "hi", "te")

def flat(v):
    if isinstance(v, (tuple, list)):
        return " | ".join(str(x) for x in v)
    return str(v)

def rows_for(modname, name, table):
    out = []
    if not isinstance(table, dict) or not table:
        return out
    if all(isinstance(v, (str, tuple, list)) for v in table.values()) and any(l in table for l in LANGS) and not any(isinstance(v, dict) for v in table.values()):
        if "en" in table and ("hi" in table or "te" in table):
            out.append((f"{modname}.{name}", "", flat(table["en"]), flat(table.get("hi", "")), flat(table.get("te", ""))))
        return out
    if any(l in table for l in LANGS) and all(isinstance(table.get(l), dict) for l in LANGS if l in table):
        keys = list((table.get("en") or {}).keys())
        for k in keys:
            en = (table.get("en") or {}).get(k)
            if en is None:
                continue
            out.append((f"{modname}.{name}", str(k), flat(en), flat((table.get("hi") or {}).get(k, "")), flat((table.get("te") or {}).get(k, ""))))
    return out

def main():
    rows, seen = [], set()
    for m in MODULES:
        try:
            mod = importlib.import_module(f"sach.{m}")
        except Exception as e:                      # a module that cannot import here is reported, never silently skipped
            print(f"skipped sach.{m}: {type(e).__name__}", file=sys.stderr); continue
        for name, val in vars(mod).items():
            if name.startswith("__") or not isinstance(val, dict):
                continue
            for r in rows_for(m, name, val):
                key = (r[2], r[3], r[4])
                if key in seen:
                    continue
                seen.add(key); rows.append(r)
    welcome = importlib.import_module("sach.telegram_bot").WELCOME
    rows.append(("telegram_bot.WELCOME", "full text (English, then the Hindi and Telugu lines at the end)", welcome, "", ""))
    out = ROOT / "docs" / "language-review-pack.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig so Excel opens Hindi and Telugu correctly
        w = csv.writer(f)
        w.writerow(["Where (file.table)", "Key", "English (source meaning)", "Hindi (as shown)", "Telugu (as shown)",
                    "Hindi: OK or your correction", "Telugu: OK or your correction", "Notes"])
        for r in rows:
            w.writerow([*r, "", "", ""])
    print(f"wrote {out.relative_to(ROOT)} with {len(rows)} rows")

if __name__ == "__main__":
    main()
