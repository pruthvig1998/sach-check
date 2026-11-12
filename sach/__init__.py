"""Sach: cited verdicts for viral forwards."""
import os as _os, pathlib as _p

def _load_env():
    f = _p.Path(__file__).resolve().parents[1] / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                _os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()
