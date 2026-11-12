import re
_HINGLISH = set("hai hain nahi nahin kya ye yeh sabko sabhi milega milenge paisa rupaye rupay sarkar yojana "
                "kal aaj ko ka ki ke mein se par jaldi bhejo forward karo aap hum tum bahut sirf free muft".split())

def detect_language(text: str) -> str:
    """Return 'te', 'hi' or 'en'. Romanised Hindi (Hinglish) maps to 'hi'."""
    te = len(re.findall(r"[ఀ-౿]", text))
    hi = len(re.findall(r"[ऀ-ॿ]", text))
    if te > 5 and te >= hi:
        return "te"
    if hi > 5:
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    if words and sum(w in _HINGLISH for w in words) >= max(3, 0.12 * len(words)):
        return "hi"
    return "en"
