"""Verdict-card strings. Fixed, short, human-written templates - never machine-translated at runtime.
NOTE: Telugu/Hindi strings need native-speaker sign-off before the demo (see README)."""
LABEL = {
 "en": {"TRUE": "TRUE", "FALSE": "FALSE", "MISLEADING": "MISLEADING", "UNVERIFIED": "UNVERIFIED"},
 "hi": {"TRUE": "सच", "FALSE": "झूठ", "MISLEADING": "भ्रामक", "UNVERIFIED": "पुष्टि नहीं हुई"},
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
 "te": {"FALSE": "{src} ప్రకారం ఈ వార్త అబద్ధం.",
        "TRUE": "{src} దీనిని ధృవీకరించింది.",
        "MISLEADING": "ఇందులో కొంత నిజం ఉంది ({src}), కానీ సంఖ్యలు, తేదీలు లేదా చెప్పిన తీరు వక్రీకరించబడింది.",
        "UNVERIFIED": "దీనిని ధృవీకరించే లేదా ఖండించే అధికారిక ఆధారం మాకు దొరకలేదు. దీన్ని నిజంగా భావించవద్దు."},
}
SOURCE_LABEL = {"en": "Source", "hi": "स्रोत", "te": "ఆధారం"}
FC_NOTE = {"en": "Fact-checker (not official)", "hi": "फैक्ट-चेकर (सरकारी नहीं)", "te": "ఫ్యాక్ట్-చెకర్ (అధికారికం కాదు)"}
EMOJI = {"TRUE": "✅", "FALSE": "❌", "MISLEADING": "⚠️", "UNVERIFIED": "❔"}
