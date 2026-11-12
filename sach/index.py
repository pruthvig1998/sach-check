"""Local index of PIB press releases (data/pib_index.jsonl), built by scripts/harvest_pib.py.
Used only to pick candidate pages; every candidate is re-fetched live before it can be cited."""
from __future__ import annotations
import json, os
from .stance import overlap, subject_coverage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(ROOT, "data", "pib_index.jsonl")
_cache: dict = {"key": None, "rows": []}

def load(path: str | None = None) -> list[dict]:
    path = path or INDEX_PATH
    if not os.path.exists(path):
        return []
    key = (path, os.path.getmtime(path))
    if _cache["key"] != key:
        rows = []
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue                       # a corrupt line never breaks retrieval
        _cache.update(key=key, rows=rows)
    return _cache["rows"]

def search(claim: str, top_n: int = 5, path: str | None = None) -> list[dict]:
    """Rank indexed releases for a claim. Needs the claim's distinctive words, not generic government vocabulary."""
    hits = []
    for r in load(path):
        text = f"{r.get('title', '')} {r.get('excerpt', '')}"
        cov, ov = subject_coverage(claim, text), overlap(claim, text)
        if cov >= 0.5 and ov >= 0.3:
            hits.append({**r, "score": round(0.6 * cov + 0.4 * ov + (0.05 if r.get("debunk") else 0), 4)})
    hits.sort(key=lambda h: -h["score"])
    return hits[:top_n]

def append(entries: list[dict], path: str | None = None) -> int:
    """Add new entries (deduplicated by PRID). Returns how many were added."""
    path = path or INDEX_PATH
    have = {str(r.get("prid")) for r in load(path)}
    new = [e for e in entries if str(e.get("prid")) not in have]
    if new:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for e in new:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(new)
