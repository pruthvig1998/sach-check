import re
_HINGLISH = set("hai hain nahi nahin kya ye yeh sabko sabhi milega milenge paisa rupaye rupay sarkar yojana "
                "kal aaj ko ka ki ke mein se par jaldi bhejo forward karo aap hum tum bahut sirf free muft".split())

# Tinglish = Telugu written in Latin script. Only distinctive words, so ordinary English never trips it.
_TINGLISH = set("""andariki andaru prabhutvam prabhutwam sarkaru sarkar-u istundi istunnaru ichestundi ichestunnaru ivvanunnaru ivvanundi ledu kaadu
kadu cheyandi cheyyandi chesukondi cheskondi pampandi pampinchandi tondaraga tvaraga mahilalaku mahilalaki rythulaku raithulaku rythulaki vidyarthulaku
rupayalu rupayalu pensionu vachesindi vachindi vastundi vastayi cheppandi unnayi undi ayyindi avutundi avvadu kosam nunchi gurinchi ippudu repu
ee-roju eppudu ayithe kani kaani kooda antha anni inka mundu taggistundi taggincharu penchaaru penchindi nijam abaddham vaartha chusara
chudandi cheppina cheppindi annaru antunnaru ante""".split())

def detect_language(text: str) -> str:
    """Return 'te', 'hi', 'tl' (Tinglish) or 'en'. Romanised Hindi (Hinglish) maps to 'hi'."""
    te = len(re.findall(r"[ఀ-౿]", text))
    hi = len(re.findall(r"[ऀ-ॿ]", text))
    if te > 5 and te >= hi:
        return "te"
    if hi > 5:
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    hl = sum(w in _HINGLISH for w in words)
    tl = sum(w in _TINGLISH for w in words)
    if words and tl >= max(2, 0.10 * len(words)) and tl > hl:
        return "tl"          # Tinglish: reply in Tinglish
    if words and hl >= max(3, 0.12 * len(words)):
        return "hi"
    return "en"
