"""Optional LLM stance judges. Gemini (free tier, no card) is preferred; Anthropic is optional.
Any failure raises, and stance.judge() falls back to the conservative heuristic."""
from __future__ import annotations
import json, os, time, urllib.request

PROMPT = ("You judge ONE source page against ONE claim from a viral forward. Reply with exactly one word:\n"
          "CONTRADICTS - the page directly refutes this specific claim.\n"
          "CONFIRMS - the page directly states this specific claim is true.\n"
          "PARTIAL - the core fact is real but the claim's numbers, dates or framing differ from the page.\n"
          "NEITHER - anything else: unrelated, only loosely related, or unsure.\n"
          "A page that merely mentions fake news in general, or a different claim, is NEITHER. When unsure, NEITHER.")
_MAP = {"CONTRADICTS": "contradicts", "CONFIRMS": "confirms", "PARTIAL": "mixed", "NEITHER": "none"}

def parse_label(raw: str) -> str:
    w = (raw or "").strip().upper().replace("*", "").split()
    return _MAP.get(w[0].strip(".,:;") if w else "", "none")

def _user(claim, title, text):
    return f"CLAIM: {claim}\n\nPAGE TITLE: {title}\nPAGE TEXT: {text[:6000]}"

class GeminiJudge:
    def __init__(self, key=None, model=None):
        self.key = key or os.environ["GEMINI_API_KEY"]
        self.model = model or os.environ.get("SACH_GEMINI_MODEL", "gemini-2.5-flash")

    def _post(self, body):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        req = urllib.request.Request(url, json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "x-goog-api-key": self.key})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    def stance(self, claim, title, text):
        body = {"systemInstruction": {"parts": [{"text": PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": _user(claim, title, text)}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 8}}
        for attempt in (0, 1):
            try:
                d = self._post(body)
                return parse_label(d["candidates"][0]["content"]["parts"][0]["text"])
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    time.sleep(6); continue   # free-tier rate limit: one retry
                raise

class ClaudeJudge:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("SACH_MODEL", "claude-sonnet-5-5")

    def stance(self, claim, title, text):
        r = self.client.messages.create(model=self.model, max_tokens=8, system=PROMPT,
                                        messages=[{"role": "user", "content": _user(claim, title, text)}])
        return parse_label(r.content[0].text)

def get_llm():
    try:
        if os.environ.get("GEMINI_API_KEY"):
            return GeminiJudge()
        if os.environ.get("ANTHROPIC_API_KEY"):
            return ClaudeJudge()
    except Exception:
        pass
    return None
