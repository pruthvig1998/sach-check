"""Verdict-card strings. Fixed, short, human-written templates - never machine-translated at runtime.
NOTE: Telugu/Hindi strings need native-speaker sign-off before the demo (see README)."""
LABEL = {
 "en": {"TRUE": "TRUE", "FALSE": "FALSE", "MISLEADING": "MISLEADING", "UNVERIFIED": "UNVERIFIED"},
 "hi": {"TRUE": "सच", "FALSE": "झूठ", "MISLEADING": "भ्रामक", "UNVERIFIED": "पुष्टि नहीं हुई"},
 "tl": {"TRUE": "NIJAM", "FALSE": "ABADDHAM", "MISLEADING": "THAPPUDARI PATTINCHEDI", "UNVERIFIED": "CONFIRM KAALEDU"},
 "te": {"TRUE": "నిజం", "FALSE": "అబద్ధం", "MISLEADING": "తప్పుదారి పట్టించేది", "UNVERIFIED": "ధృవీకరణ కాలేదు"},
}
WHY = {
 "en": {"FALSE": "{src} says this claim is false.",
        "TRUE": "{src} confirms this.",
        "MISLEADING": "Part of it is real ({src}), but the numbers, dates or framing in the forward are distorted.",
        "UNVERIFIED": "We found no official source that confirms or denies this. Do not treat it as fact."},
 "hi": {"FALSE": "{src} के अनुसार यह दावा झूठ है।",
        "TRUE": "{src} ने इसकी पुष्टि की है।",
        "MISLEADING": "इसका कुछ हिस्सा सही है ({src}), पर संख्या, तारीख या बात का ढंग गलत पेश किया गया है।",
        "UNVERIFIED": "हमें इसकी पुष्टि या खंडन करने वाला कोई सरकारी स्रोत नहीं मिला। इसे सच न मानें।"},
 "tl": {"FALSE": "{src} prakaaram ee vaartha abaddham.",
        "TRUE": "{src} idi nijam ani confirm chesindi.",
        "MISLEADING": "Konta nijam undi ({src}), kaani numbers, dates leda cheppina vidhaanam tappuga undi.",
        "UNVERIFIED": "Deenini confirm cheyadaniki leda khandinchadaniki official source dorakaledu. Deenini nijam anukovaddu."},
 "te": {"FALSE": "{src} ప్రకారం ఈ వార్త అబద్ధం.",
        "TRUE": "{src} దీనిని ధృవీకరించింది.",
        "MISLEADING": "ఇందులో కొంత నిజం ఉంది ({src}), కానీ సంఖ్యలు, తేదీలు లేదా చెప్పిన తీరు వక్రీకరించబడింది.",
        "UNVERIFIED": "దీనిని ధృవీకరించే లేదా ఖండించే అధికారిక ఆధారం మాకు దొరకలేదు. దీన్ని నిజంగా భావించవద్దు."},
}
SOURCE_LABEL = {"tl": "Aadhaaram", "en": "Source", "hi": "स्रोत", "te": "ఆధారం"}
FC_NOTE = {"tl": "Fact-checker (official kaadu)", "en": "Fact-checker (not official)", "hi": "फैक्ट-चेकर (सरकारी नहीं)", "te": "ఫ్యాక్ట్-చెకర్ (అధికారికం కాదు)"}
EMOJI = {"TRUE": "✅", "FALSE": "❌", "MISLEADING": "⚠️", "UNVERIFIED": "❔"}

NOCLAIM = {
 "tl": "Ee message lo check cheyyadaniki factual statement kanapadaledu. Check cheyalsina statement ni paste cheyandi.",
 "en": "We couldn't find a checkable factual claim in this message. Try pasting the specific claim you want checked.",
 "hi": "इस संदेश में जाँचने लायक कोई तथ्य-दावा नहीं मिला। जिस दावे की जाँच करनी है, कृपया वही चिपकाएँ।",
 "te": "ఈ సందేశంలో తనిఖీ చేయదగిన వాస్తవ ప్రకటన కనిపించలేదు. తనిఖీ చేయాల్సిన నిర్దిష్ట ప్రకటనను అతికించండి.",
}
NOCLAIM_LABEL = {"tl": "CHECK CHEYYALSINDI LEDU", "en": "NO CLAIM FOUND", "hi": "कोई दावा नहीं मिला", "te": "ప్రకటన కనిపించలేదు"}
