"""Words for fake / false / misleading / rumour and for "no / not" in the newly supported Indian languages.

Who calls this: sach/stance.py (extends _STRICT_DEBUNK, _DENIAL and _NEGATION) and sach/pib.py (DEBUNK_MARKERS). Nothing else holds
such lists. No data is read or written; these are compiled patterns built at import time from the tuples below.

They only extend the OFFLINE heuristics to more scripts: the checks that use them are unchanged. Every word is matched as a WHOLE word
(no letter or vowel sign directly before or after it), because Python's \\b does not see Indic vowel signs and a short word such as the
Bengali na would otherwise match inside ordinary words. Only common, unambiguous words are listed; a language with no safe word is left
empty (Manipuri). When the verdict flow runs with an AI translator these heuristics see the English translation, so these lists matter
mainly in limited mode and for regional-language pages.

NOT NATIVE-REVIEWED: assembled by an AI model, to be checked by native speakers (docs/languages.md).
"""
import re

# Characters that count as "part of a word" next to a match: ASCII/Unicode word characters, Indic letters and vowel signs
# (U+0900-0D7F without the danda U+0964-0965), Meitei Mayek, and Arabic-script marks.
_WORDCH = "\\w\u0900-\u0963\u0966-\u0d7f\uabc0-\uabff\u064b-\u065f\u0670\u06d6-\u06ed"

# fake / false / misleading / baseless / rumour (NOT NATIVE-REVIEWED)
DEBUNK = {
    "bn": ("ভুয়া", "মিথ্যা", "ভিত্তিহীন", "বিভ্রান্তিকর", "গুজব", "অসত্য"),
    "as": ("ভুৱা", "মিছা", "ভিত্তিহীন", "বিভ্ৰান্তিকৰ", "গুজৱ"),
    "mr": ("खोटे", "खोटी", "खोटा", "बनावट", "अफवा", "दिशाभूल", "निराधार", "असत्य"),
    "kok": ("खोटें", "खोटी", "खोटो", "अफवा", "निराधार"),
    "ne": ("झुटो", "झूटो", "झुटा", "नक्कली", "भ्रमपूर्ण"),
    "ta": ("போலி", "பொய்", "பொய்யான", "வதந்தி", "அடிப்படையற்ற"),
    "gu": ("નકલી", "ખોટું", "ખોટી", "ખોટો", "ખોટા", "અફવા", "ભ્રામક", "પાયાવિહોણું"),
    "pa": ("ਜਾਅਲੀ", "ਝੂਠ", "ਝੂਠਾ", "ਝੂਠੀ", "ਅਫਵਾਹ", "ਗੁੰਮਰਾਹਕੁੰਨ", "ਬੇਬੁਨਿਆਦ", "ਫਰਜ਼ੀ"),
    "or": ("ଭୁଆ", "ମିଥ୍ୟା", "ମିଛ", "ଗୁଜବ", "ଅସତ୍ୟ", "ଭିତ୍ତିହୀନ", "ଭ୍ରମାତ୍ମକ"),
    "kn": ("ನಕಲಿ", "ಸುಳ್ಳು", "ವದಂತಿ", "ಆಧಾರರಹಿತ", "ದಾರಿತಪ್ಪಿಸುವ"),
    "ml": ("വ്യാജ", "വ്യാജം", "കള്ളം", "നുണ", "അടിസ്ഥാനരഹിതം"),
    "ur": ("جعلی", "جھوٹ", "جھوٹا", "جھوٹی", "جھوٹے", "افواہ", "فرضی", "بے بنیاد", "گمراہ کن"),
    "mni": (),
}

# no / not / never (NOT NATIVE-REVIEWED). A negated claim is never judged FALSE by the heuristic, so a longer list only makes Sach more careful.
NEGATION = {
    "bn": ("না", "নয়", "নেই", "নাই", "নহে"),
    "as": ("নহয়", "নাই", "নাছিল"),
    "mr": ("नाही", "नाहीत", "नव्हे", "नसे", "नका"),
    "kok": ("ना", "नात", "न्हय"),
    "ne": ("छैन", "छैनन्", "होइन", "नभएको"),
    "ta": ("இல்லை", "அல்ல", "இல்லாத", "கிடையாது"),
    "gu": ("નથી", "નહીં", "નહિ"),
    "pa": ("ਨਹੀਂ", "ਨਹੀ", "ਨਾ"),
    "or": ("ନାହିଁ", "ନୁହେଁ", "ନୁହଁ"),
    "kn": ("ಇಲ್ಲ", "ಅಲ್ಲ", "ಇಲ್ಲಾ"),
    "ml": ("ഇല്ല", "അല്ല", "ഇല്ലാ"),
    "ur": ("نہیں", "نہ"),
    "mni": ("ꯅꯠꯇꯦ", "ꯂꯩꯇꯦ"),
}


def whole_words(table: dict) -> str:
    """A regex fragment (no flags) matching any word of the table as a whole word."""
    words = sorted({w for ws in table.values() for w in ws}, key=len, reverse=True)
    if not words:
        return "(?!)"
    return "(?<![%s])(?:%s)(?![%s])" % (_WORDCH, "|".join(re.escape(w) for w in words), _WORDCH)


DEBUNK_RE = whole_words(DEBUNK)
NEGATION_RE = whole_words(NEGATION)
