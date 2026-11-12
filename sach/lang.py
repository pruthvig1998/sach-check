"""Language detection and the one place that lists every language Sach speaks.

Who imports this: sach/pipeline.py (detect_language), sach/site.py (REPLY_LANGS, selector, card lang/dir), sach/voice.py (BCP47),
sach/telegram_bot.py (/lang), sach/impact.py, sach/ledger.py (language counters) and sach/stance.py (native digits).

Detection is offline and deterministic: by dominant script first, then a small word-list disambiguation for the scripts that more than
one language shares (Devanagari: Hindi / Marathi / Konkani / Nepali; Bengali script: Bengali / Assamese). See docs/languages.md.
"""
import re
import unicodedata

# ---- the language table (one place; everything else imports it) ------------------------------------------------------------
# Order: English, then Indian languages by number of first-language speakers (Census 2011), then the romanised Telugu option.
SUPPORTED = ("en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as", "kok", "ne", "mni", "tl")
NAMES = {"en": "English", "hi": "Hindi", "bn": "Bengali", "mr": "Marathi", "te": "Telugu", "ta": "Tamil", "gu": "Gujarati",
         "ur": "Urdu", "kn": "Kannada", "or": "Odia", "ml": "Malayalam", "pa": "Punjabi", "as": "Assamese", "kok": "Konkani",
         "ne": "Nepali", "mni": "Manipuri (Meitei)", "tl": "Tinglish"}
NATIVE = {"en": "English", "hi": "हिन्दी", "bn": "বাংলা", "mr": "मराठी", "te": "తెలుగు", "ta": "தமிழ்", "gu": "ગુજરાતી",
          "ur": "اردو", "kn": "ಕನ್ನಡ", "or": "ଓଡ଼ିଆ", "ml": "മലയാളം", "pa": "ਪੰਜਾਬੀ", "as": "অসমীয়া", "kok": "कोंकणी",
          "ne": "नेपाली", "mni": "ꯃꯩꯇꯩꯂꯣꯟ", "tl": "Tinglish"}      # NOT NATIVE-REVIEWED (the names of the languages in their own scripts)
# Browser speech language tags (recognition and read-aloud). Tinglish is Telugu in Latin letters, so a person dictating it speaks
# Telugu: te-IN. Nepali uses ne-NP (the tag browsers know). Konkani and Manipuri have no common browser voice: the tag is still
# passed, and the page says plainly when no voice is installed.
BCP47 = {"en": "en-IN", "hi": "hi-IN", "bn": "bn-IN", "mr": "mr-IN", "te": "te-IN", "ta": "ta-IN", "gu": "gu-IN", "ur": "ur-IN",
         "kn": "kn-IN", "or": "or-IN", "ml": "ml-IN", "pa": "pa-IN", "as": "as-IN", "kok": "kok-IN", "ne": "ne-NP",
         "mni": "mni-IN", "tl": "te-IN"}
RTL = {"ur"}
# Languages whose own words are written in an Indian script or Perso-Arabic (everything except English and Tinglish).
INDIAN_LANGS = tuple(c for c in SUPPORTED if c not in ("en", "tl"))


def lang_name(code: str) -> str:
    return NAMES.get(code, NAMES["en"])


def is_rtl(code: str) -> bool:
    return code in RTL


def html_lang(code: str) -> str:
    """The value for an HTML lang attribute. Tinglish is Telugu in Latin letters, which BCP 47 writes te-Latn."""
    return "te-Latn" if code == "tl" else (code if code in NAMES else "en")


# ---- native digits -> ASCII ------------------------------------------------------------------------------------------------
# Start of the 0-9 run of each script's digits. Used by stance.tokens()/numbers() so 2000 == ২০০০ == २००० == ٢٠٠٠.
_DIGIT_BASES = (0x0660, 0x06F0, 0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66, 0xABF0)
DIGITS = {b + i: ord("0") + i for b in _DIGIT_BASES for i in range(10)}
DIGITS.update({0x066B: ord("."), 0x066C: ord(",")})       # Arabic decimal and thousands separators


def to_ascii_digits(text: str) -> str:
    return (text or "").translate(DIGITS)


# ---- script detection ------------------------------------------------------------------------------------------------------
# Order matters only for ties (Telugu first keeps the old "te >= hi" tie rule).
_SCRIPTS = (
    ("te", 0x0C00, 0x0C7F),
    ("deva", 0x0900, 0x097F),
    ("bn", 0x0980, 0x09FF),
    ("pa", 0x0A00, 0x0A7F),
    ("gu", 0x0A80, 0x0AFF),
    ("or", 0x0B00, 0x0B7F),
    ("ta", 0x0B80, 0x0BFF),
    ("kn", 0x0C80, 0x0CFF),
    ("ml", 0x0D00, 0x0D7F),
    ("mni", 0xABC0, 0xABFF),
    ("ur", 0x0600, 0x06FF),
    ("ur", 0x0750, 0x077F),
    ("ur", 0xFB50, 0xFDFF),
    ("ur", 0xFE70, 0xFEFF),
)
_SCRIPT_ORDER = ("te", "deva", "bn", "pa", "gu", "or", "ta", "kn", "ml", "mni", "ur")
MIN_SCRIPT_LETTERS = 5          # more than this many letters in one Indian script: the script decides (as before)


def script_counts(text: str) -> dict:
    """Letters (and the vowel signs that belong to them) per script. Digits, punctuation, URLs' ASCII, spaces and emoji are ignored."""
    out = {}
    for ch in text:
        o = ord(ch)
        if o < 0x0600:
            continue
        for name, lo, hi in _SCRIPTS:
            if lo <= o <= hi:
                if unicodedata.category(ch)[0] in "LM":     # not digits (Nd), not danda or Arabic punctuation (Po)
                    out[name] = out.get(name, 0) + 1
                break
    return out


# ---- Devanagari: Hindi / Marathi / Konkani / Nepali ------------------------------------------------------------------------
def _dn(s: str) -> str:
    """Normalise Devanagari for matching: drop zero-width joiners and nukta, write chandrabindu as anusvara."""
    return re.sub("[​-‍़]", "", s).replace("ँ", "ं")


def _words(s: str) -> frozenset:
    return frozenset(_dn(w) for w in s.split())


# Very common function words. A word shared by two languages is left out of the shorter list, so a hit means something.
# NOT NATIVE-REVIEWED: assembled by an AI model from common usage; the unit tests pin the behaviour, a native speaker should extend them.
_HI = _words("है हैं नहीं और के की में से को का पर यह वह था थी थे रहा रही रहे गया गई गए किया हुआ लिए भी कि सभी कर करें हम आप दे देगी सकता सकते")
_MR = _words("आहे आहेत नाही नाहीत आणि मध्ये साठी करण्यात असे पण झाले झाला झाली म्हणून मिळणार पाठवा नका फक्त तुम्ही काय सर्वांना केला केली केले मिळतील मिळेल")
_KOK = _words("आसा आसात आनी हांव तुमी जाल्यार खातीर कितें म्हजें म्हजो म्हजी म्हज्या तुजें आमी जालें जालो जाली सरकारान आशिल्लो आशिल्ली आशिल्ले मेरेन")
_NE = _words("छ छन् छु छैन छैनन् होइन हुन् गर्न गर्ने गरेको भएको रहेको भनेको भने लागि पनि सबै हामी तपाईं तपाईंले सरकारले र लाई हुन्छ भयो")
# Suffixes that only that language uses on ordinary words (a Marathi noun ends -च्या; a Nepali plural ends -हरू).
_MR_END = tuple(_dn(x) for x in ("च्या", "णार", "पासून"))
_MR_IN = (_dn("ण्यात"),)
_NE_IN = (_dn("हरू"), _dn("हरु"))
_KOK_END = (_dn("पाक"),)          # Konkani infinitive of purpose: दवरपाक, करपाक
MIN_MARKERS = 2                  # a regional language needs at least this many marker hits ...
# ... and must beat Hindi by a clear margin: hits >= 2 * hindi_hits + 1 (and beat the other regional languages).


def _marker_scores(text: str) -> dict:
    toks = [_dn(t) for t in re.findall(r"[ऀ-ॣ०-ॿ​-‍]+", text)]
    s = {"hi": 0, "mr": 0, "kok": 0, "ne": 0}
    for t in toks:
        if t in _HI:
            s["hi"] += 1
        if t in _MR or t.endswith(_MR_END) and len(t) > 4 or any(x in t for x in _MR_IN):
            s["mr"] += 1
        if t in _KOK or t.endswith(_KOK_END) and len(t) > 4:
            s["kok"] += 1
        if t in _NE or any(x in t for x in _NE_IN):
            s["ne"] += 1
    return s


def _devanagari_language(text: str) -> str:
    s = _marker_scores(text)
    best = max(("mr", "kok", "ne"), key=lambda k: s[k])
    others = sorted((s[k] for k in ("mr", "kok", "ne") if k != best), reverse=True)
    if s[best] >= MIN_MARKERS and s[best] >= 2 * s["hi"] + 1 and s[best] > others[0]:
        return best
    return "hi"                  # unsure: Hindi (a wrong guess only changes the reply language, and the person can switch)


# ---- Bengali script: Bengali / Assamese ------------------------------------------------------------------------------------
_AS_LETTERS = re.compile("[ৰৱ]")           # ৰ and ৱ exist only in the Assamese use of the script
# Assamese function words that do not contain those letters (most Assamese text does contain them; this catches the rest).
# NOT NATIVE-REVIEWED
_AS_WORDS = frozenset("নহয় হৈছে হৈছিল সকলো কিয় লগত কৈছে বাবে".split())
_BN_WORDS = frozenset("নয় হয়েছে জন্য সবাই কেন সঙ্গে বলেছে".split())     # Bengali counterparts, so a Bengali text with one shared word stays Bengali


def _bengali_language(text: str) -> str:
    if _AS_LETTERS.search(text):
        return "as"
    toks = re.findall(r"[ঀ-৯]+", text)
    a = sum(t in _AS_WORDS for t in toks)
    b = sum(t in _BN_WORDS for t in toks)
    return "as" if a >= 2 and a > b else "bn"


# ---- Latin script (unchanged behaviour) ------------------------------------------------------------------------------------
_HINGLISH = set("hai hain nahi nahin kya ye yeh sabko sabhi milega milenge paisa rupaye rupay sarkar yojana "
                "kal aaj ko ka ki ke mein se par jaldi bhejo forward karo aap hum tum bahut sirf free muft".split())

# Tinglish = Telugu written in Latin script. Only distinctive words, so ordinary English never trips it.
_TINGLISH = set("""andariki andaru prabhutvam prabhutwam sarkaru sarkar-u istundi istunnaru ichestundi ichestunnaru ivvanunnaru ivvanundi ledu kaadu
kadu cheyandi cheyyandi chesukondi cheskondi pampandi pampinchandi tondaraga tvaraga mahilalaku mahilalaki rythulaku raithulaku rythulaki vidyarthulaku
rupayalu rupayalu pensionu vachesindi vachindi vastundi vastayi cheppandi unnayi undi ayyindi avutundi avvadu kosam nunchi gurinchi ippudu repu
ee-roju eppudu ayithe kani kaani kooda antha anni inka mundu taggistundi taggincharu penchaaru penchindi nijam abaddham vaartha chusara
chudandi cheppina cheppindi annaru antunnaru ante""".split())


def _latin_language(text: str) -> str:
    words = re.findall(r"[a-z]+", text.lower())
    hl = sum(w in _HINGLISH for w in words)
    tl = sum(w in _TINGLISH for w in words)
    if words and tl >= max(2, 0.10 * len(words)) and tl > hl:
        return "tl"          # Tinglish: reply in Tinglish
    if words and hl >= max(3, 0.12 * len(words)):
        return "hi"          # Hinglish: reply in Hindi
    return "en"


def detect_language(text: str) -> str:
    """Return one of SUPPORTED. The Indian script with the most letters wins (when it has more than MIN_SCRIPT_LETTERS); Devanagari and
    Bengali-script text is then split by marker words; otherwise Latin text is English, Tinglish or Hinglish (which maps to 'hi')."""
    text = text or ""
    counts = script_counts(text)
    if counts:
        top = max(_SCRIPT_ORDER, key=lambda k: counts.get(k, 0))      # max() keeps the first of equals: the tie order above
        if counts[top] > MIN_SCRIPT_LETTERS:
            if top == "deva":
                return _devanagari_language(text)
            if top == "bn":
                return _bengali_language(text)
            return top
    return _latin_language(text)
