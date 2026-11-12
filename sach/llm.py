"""Optional LLM judge (Anthropic). Only used when ANTHROPIC_API_KEY is set."""
from __future__ import annotations
import json, os

class ClaudeJudge:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("SACH_MODEL", "claude-sonnet-5-5")

    def _ask(self, system, user):
        r = self.client.messages.create(model=self.model, max_tokens=300, system=system,
                                        messages=[{"role": "user", "content": user}])
        return r.content[0].text.strip()

    def stance(self, claim, title, text):
        sys = ("You judge whether a source page contradicts, confirms, or partly supports a claim. "
               "Answer with exactly one word: contradicts, confirms, mixed, none. "
               "Use 'contradicts' ONLY if the page directly refutes this specific claim. "
               "Use 'confirms' ONLY if the page directly states the claim is true. "
               "Use 'mixed' if the core fact is real but numbers, dates or framing differ. "
               "If unsure, answer none.")
        return self._ask(sys, f"CLAIM: {claim}\n\nPAGE TITLE: {title}\nPAGE TEXT: {text[:6000]}").lower().split()[0].strip(".")

def get_llm():
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeJudge()
        except Exception:
            return None
    return None
