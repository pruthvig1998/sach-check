"""Optional LLM stance judges. Gemini (free tier, no card) is preferred; Anthropic is optional.
Any failure raises, and stance.judge() falls back to the conservative heuristic."""
from __future__ import annotations
import json, os, time, urllib.request
from .stance import validate_stance, heuristic_stance

PROMPT = ("You judge ONE source page against ONE claim from a viral forward. Reply on ONE line as:  LABEL | quote\n"
          "where LABEL is exactly one of the words below and quote is a sentence COPIED VERBATIM from the page (max 30 words) that justifies it. For NEITHER write no quote.\n"
          "CONTRADICTS - the page directly refutes this specific claim.\n"
          "CONFIRMS - the page directly states this specific claim is true.\n"
          "PARTIAL - the core fact is real but the claim's numbers, dates or framing differ from the page.\n"
          "NEITHER - anything else: unrelated, only loosely related, or unsure.\n"
          "A page that merely mentions fake news in general, or a DIFFERENT claim, scheme or number, is NEITHER. A page describing a real scheme does not contradict a claim about something else. When unsure, NEITHER.")
_MAP = {"CONTRADICTS": "contradicts", "CONFIRMS": "confirms", "PARTIAL": "mixed", "NEITHER": "none"}

def parse_label(raw: str) -> str:
    w = (raw or "").strip().upper().replace("*", "").split()
    return _MAP.get(w[0].strip(".,:;") if w else "", "none")

def parse_reply(raw: str):
    """'CONTRADICTS | quote...' -> (stance, quote)."""
    label, _, quote = (raw or "").partition("|")
    return parse_label(label), quote.strip()

def _user(claim, title, text):
    return f"CLAIM: {claim}\n\nPAGE TITLE: {title}\nPAGE TEXT: {text[:6000]}"

DEFAULT_GEMINI_MODELS = "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.8-flash,gemini-flash-latest"

TRANSLATE_PROMPT = ("Translate the user's claim into plain English. The claim may be in Telugu, Hindi, or Telugu/Hindi written in English letters (Tinglish/Hinglish). Be faithful and literal: keep every number, amount, date, name and "
                    "scheme name exactly. Do not add, explain or soften anything. Output only the English sentence.")

class GeminiJudge:
    """Tries each model in turn; a model that is retired (404), overloaded (503), rate-limited (429) or slow is skipped."""
    def __init__(self, key=None, model=None, timeout=45):
        self.key = key or os.environ["GEMINI_API_KEY"]
        self.models = [m.strip() for m in (model or os.environ.get("SACH_GEMINI_MODEL", DEFAULT_GEMINI_MODELS)).split(",") if m.strip()]
        self.timeout = timeout
        self.failures = 0      # count of stance calls where every model failed (quota, outage): surfaced as a "limited mode" notice

    def _post(self, model, body):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(url, json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "x-goog-api-key": self.key})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def _label(self, model, claim, title, text):
        body = {"systemInstruction": {"parts": [{"text": PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": _user(claim, title, text)}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 200}}
        d = self._post(model, body)
        st, q = parse_reply(d["candidates"][0]["content"]["parts"][0]["text"])
        return validate_stance(st, q, claim, title, text)

    def stance(self, claim, title, text, tier=""):
        """First opinion from the first model that answers. Any decisive stance (not 'none') must be confirmed by a
        DIFFERENT model. If no second model can answer, the deterministic title/number heuristic is the second opinion
        (so a clear PIB debunk survives a flaky free tier, but a lone LLM guess does not). Disagreement -> 'none'."""
        first, used, last = None, None, None
        for m in self.models:
            try:
                first, used = self._label(m, claim, title, text), m
                break
            except Exception as e:      # 404/429/503/timeout/odd payload: try the next model
                last = e
        if first is None:
            self.failures += 1
            raise last
        if first == "none":
            return "none"
        for m in [m for m in self.models if m != used] or [used]:
            try:
                return first if self._label(m, claim, title, text) == first else "none"
            except Exception:
                continue
        return first if heuristic_stance(claim, title, text, tier) == first else "none"

    def translate(self, text):
        body = {"systemInstruction": {"parts": [{"text": TRANSLATE_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": text[:1000]}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 200}}
        last = None
        for model in self.models:
            try:
                return self._post(model, body)["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                last = e
        raise last

class ClaudeJudge:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("SACH_MODEL", "claude-sonnet-5-5")

    def stance(self, claim, title, text):
        r = self.client.messages.create(model=self.model, max_tokens=200, system=PROMPT,
                                        messages=[{"role": "user", "content": _user(claim, title, text)}])
        st, q = parse_reply(r.content[0].text)
        return validate_stance(st, q, claim, title, text)

def get_llm():
    try:
        if os.environ.get("GEMINI_API_KEY"):
            return GeminiJudge()
        if os.environ.get("ANTHROPIC_API_KEY"):
            return ClaudeJudge()
    except Exception:
        pass
    return None
