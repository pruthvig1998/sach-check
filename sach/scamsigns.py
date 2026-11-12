"""Warning signs: deterministic scam-pattern hints for a pasted forward.

Who calls this: sach/web.py (do_POST adds `warning_signs` to the response) and sach/site.py (result_block renders the box).
It is ADVICE, not a verdict. It never feeds the pipeline, the verdict logic, the cache or the ledger: the signs are computed
from the current request text every time. Pure regex rules, no network, no AI, linear time (every gap is bounded).
"""
from __future__ import annotations
import html
import re
from .fetch import is_official, is_factchecker, host_of

MAX_INPUT = 20000
MAX_SHOWN = 5
MAX_EVIDENCE = 80
_F = re.I | re.U


def _c(p: str) -> re.Pattern:
    return re.compile(p, _F)


# ---- secrets (OTP, PIN, ...) --------------------------------------------------------------------------------------------
_SECRET_EN = (r"(?:otp|one[- ]time[- ]password|(?:upi|atm|net ?banking|card|secret)[ -]?pin|pin(?![ -]?code)|cvv|cvc|password|passcode|"
              r"card number|(?:your|ur) (?:aadhaa?r|aadhar|pan)(?: card)? (?:number|no\.?|details)|(?:your|ur) bank (?:account )?(?:details|number)|"
              r"(?:your|ur) account (?:number|details)|(?:your )?screen)")
_SECRET_HI = r"(?:ओटीपी|पिन|सीवीवी|पासवर्ड|आधार नंबर|पैन नंबर|कार्ड नंबर|खाता नंबर|बैंक डिटेल)"
_SECRET_TE = r"(?:ఓటీపీ|పిన్|సీవీవీ|పాస్.?వర్డ్|ఆధార్ నంబర్|కార్డ్ నంబర్|ఖాతా నంబర్)"
_VERB_EN = r"(?:share|send|tell|give|enter|provide|submit|confirm|verify|type|read out|bhejo|bhejiye|bhejein|batao|batayein|bata do|dijiye|btao|cheppandi|pampandi|ivvandi|enter cheyandi|share karo|share karein)"
_VERB_HI = r"(?:बताएं|बताएँ|बताओ|बताइए|बताइये|भेजें|भेजो|भेजिए|शेयर|दें|दो|डालें|दर्ज|एंटर)"
_VERB_TE = r"(?:చెప్పండి|పంపండి|పంపించండి|షేర్|ఇవ్వండి|ఎంటర్|నమోదు)"
_SECRET = [
    _c(rf"\b{_VERB_EN}\b[^.\n]{{0,40}}?\b{_SECRET_EN}\b"),
    _c(rf"\b{_SECRET_EN}\b[^.\n]{{0,25}}?\b{_VERB_EN}\b"),
    _c(rf"{_SECRET_HI}[^।.\n]{{0,25}}{_VERB_HI}"),
    _c(rf"{_VERB_HI}[^।.\n]{{0,25}}{_SECRET_HI}"),
    _c(rf"{_SECRET_TE}[^.\n]{{0,25}}{_VERB_TE}"),
    _c(rf"{_VERB_TE}[^.\n]{{0,25}}{_SECRET_TE}"),
    _c(r"\b(?:anydesk|teamviewer|quick ?support|rustdesk|alpemix)\b"),
    _c(r"\bshare (?:your )?screen\b"),
]
# a genuine bank warning ("never share your OTP") must not be flagged
_NEG = _c(r"(?:\bnever\b|\bdo not\b|\bdon'?t\b|\bdont\b|\bnot to\b|\bnot ask\b|\bnever ask\b|\bavoid\b|\bwarn(?:ing|s)?\b|\bbeware\b|\bkabhi\b|\bmat\s+(?:batao|do|bhejo|share|dena)|\bnahi+n?\s+(?:batana|dena|bhejna|share|batayein)|कभी|मत\b|न\s*(?:बताएं|बताएँ|बताना|दें|करें|शेयर|भेजें)|नहीं|చెప్పకండి|ఇవ్వకండి|పంపకండి|వద్దు|ఎప్పుడూ|ఎవరికీ|పొరపాటున)")

# ---- UPI traps ---------------------------------------------------------------------------------------------------------
_AMT = r"(?:rs\.?|₹|inr|rupees?|रुपये?|रु\.?|రూ\.?)\s*\d[\d,]{0,5}"
_UPI = [
    _c(rf"\b(?:send|pay|transfer|deposit|bhejo|bhejiye|bhej do)\s+(?:just\s+|only\s+)?{_AMT}[^.\n]{{0,50}}?\b(?:to|and|for|taaki|ke liye|paane|pane|milega|milenge)\b[^.\n]{{0,15}}?\b(?:receive|get|claim|activate|unlock|verify|release|cashback|reward|prize|paise|paisa|money|amount)\b"),
    _c(rf"{_AMT}\s*(?:भेजें|भेजो|भेजिए|जमा करें)[^।.\n]{{0,50}}(?:पाने|प्राप्त|मिलेगा|मिलेंगे)"),
    _c(rf"{_AMT}\s*(?:పంపండి|పంపించండి|కట్టండి)[^.\n]{{0,50}}(?:పొందడానికి|పొందాలంటే|వస్తాయి|రావడానికి)"),
    _c(rf"{_AMT}\s*(?:pampandi|pampinchandi|bhejo|bhejiye|send)\b[^.\n]{{0,50}}?\b(?:receive|get|paane|pane|milega|vastayi|raavadaniki|cashback|paise|paisa)\b"),
    _c(r"\benter (?:your )?(?:upi )?pin (?:to|and) (?:receive|get|claim)"),
    _c(r"\b(?:approve|accept|authorise|authorize|confirm)\s+(?:the |this |that )?(?:upi )?(?:collect|payment) request\b"),
    _c(r"\bcollect request\b[^.\n]{0,30}\b(?:approve|accept|click|confirm)\b"),
    _c(r"\b(?:pay|send|transfer)\b[^.\n]{0,30}\b(?:processing|registration|activation|verification|delivery|release|clearance|claim) (?:fees?|charges?)\b"),
    _c(r"यूपीआई पिन (?:डालें|दर्ज|एंटर)"), _c(r"कलेक्ट रिक्वेस्ट[^।.\n]{0,20}(?:स्वीकार|अप्रूव|एक्सेप्ट)"),
    _c(r"యూపీఐ పిన్[^.\n]{0,20}(?:ఎంటర్|నమోదు)"),
]

# ---- prizes ------------------------------------------------------------------------------------------------------------
_PRIZE = [
    _c(r"\b(?:lottery|lucky draw|jackpot)\b"),
    _c(r"\byou(?:'ve| have| are| r)?\s+(?:just\s+)?(?:won|been selected|selected|the winner)\b"),
    _c(r"\bcongratulations\b[^.\n]{0,40}?\b(?:won|winner|selected|prize)\b"),
    _c(r"\bfree\s+(?:gift|gifts|gold|laptop|recharge|data|smartphone|mobile phone|phone|iphone|bike|tv)\b"),
    _c(r"\bcashback\b"),
    _c(rf"{_AMT}[^.\n]{{0,50}}?\b(?:will be credited|credited to your|will come to your)\b[^.\n]{{0,50}}?\b(?:register|click|link|apply|verify)\b"),
    _c(rf"\b(?:register|click|apply|verify)\b[^.\n]{{0,60}}?{_AMT}[^.\n]{{0,40}}?\b(?:credited|will be (?:sent|given|deposited)|in your (?:bank )?account)\b"),
    _c(r"\baap(?:ne)?\b[^.\n]{0,25}?\bjeet(?:a|e|i)\b"), _c(r"\bmuft (?:recharge|gift|mobile|laptop|sona)\b"),
    _c(r"\bmeeru\b[^.\n]{0,25}?\bgel(?:i|ee)chaaru\b"), _c(r"\blottery (?:tagilindi|vachindi|gelichaaru)\b"),
    _c(r"लॉटरी|इनाम जीत|आपने [^।.\n]{0,20}जीता|आप विजेता|मुफ्त (?:रिचार्ज|मोबाइल|लैपटॉप|गिफ्ट|सोना|स्मार्टफोन)|कैशबैक"),
    _c(r"లాటరీ|మీరు గెలిచారు|ఉచిత (?:రీ?ఛార్జ్|రీ?చార్జ్|ల్యాప్.?టాప్|మొబైల్|బహుమతి|గిఫ్ట్)|క్యాష్.?బ్యాక్"),
]

# ---- click / register --------------------------------------------------------------------------------------------------
_CLICK = [
    _c(r"\bclick\b[^.\n]{0,40}?\b(?:register|registration|claim|apply|verify|update|activate|avail|win|download)\b"),
    _c(r"\b(?:register|apply|claim|verify|update kyc|avail)\b[^.\n]{0,25}?\b(?:using|through|via|on|with)\s+(?:the |this )?(?:below |following )?link\b"),
    _c(r"\blimited (?:seats|slots|offer|period|time)\b"), _c(r"\b(?:register|apply|claim)\b[^.\n]{0,12}\b(?:before|by)\s+(?:midnight|tonight|today)\b"),
    _c(r"\b(?:link|here)\s*(?:pe|par|pai|lo|on)?\s*click\b"), _c(r"\bclick\s*(?:karo|kare[iy]n?|kijiye|kijiye|chesi|cheyandi|cheyyandi|chey(?:yandi)?)\b"),
    _c(r"(?:लिंक|यहाँ|यहां)\s*(?:पर)?\s*क्लिक\s*(?:करें|करो|करके|कीजिए)"), _c(r"क्लिक करके\s*(?:रजिस्टर|आवेदन|क्लेम|अप्लाई)"), _c(r"सीमित सीटें"),
    _c(r"లింక్\s*(?:పై|మీద|ని)?\s*క్లిక్ చేయండి"), _c(r"క్లిక్ చేసి"), _c(r"పరిమిత సీట్లు"),
]

# ---- urgency / threats -------------------------------------------------------------------------------------------------
_URG = [
    _c(r"\blast date\b[^.\n]{0,12}\b(?:today|tomorrow|tonight|aaj|e roje|ee roje|ee rojey)\b"), _c(r"\b(?:aaj|ee roje|e roje)\b[^.\n]{0,12}\blast date\b"),
    _c(r"\b(?:your|ur|aapka|aapki)\s+(?:\w+\s+){0,2}(?:bank account|account|sim(?: card)?|mobile number|upi|electricity|gas connection|pan(?: card)?|aadhaar|card)\b[^.\n]{0,30}?\b(?:will be|is going to be|gets?|has been)\s+(?:blocked|suspended|disconnected|deactivated|closed|cancelled|frozen)\b"),
    _c(r"\b(?:account|sim|card|kyc|number)\b[^.\n]{0,25}?\b(?:block|band|bandh|disconnect|suspend|expire)\s*(?:ho\s*(?:jayega|jayegi|jaega|jayenge)|avutundi|avuthundi|avtundi|avuthadi|ayipotundi)\b"),
    _c(r"\bkyc\b[^.\n]{0,40}?\b(?:expire[sd]?|expiry|pending|suspend|blocked|immediately|today|urgent)\b"),
    _c(r"\b(?:urgent|urgently|immediate|immediately)\b[^.\n]{0,30}?\b(?:action|update|verify|click|call|reply|pay)\b"),
    _c(r"\b(?:legal action (?:will be|against)|arrest warrant|digital arrest|you will be arrested|you may be arrested|court notice|police case against you)\b"),
    _c(r"आखिरी तारीख आज|अंतिम तिथि आज|अंतिम तारीख आज|खाता (?:बंद|ब्लॉक)\s*हो|सिम (?:बंद|ब्लॉक)\s*हो|केवाईसी[^।.\n]{0,30}(?:एक्सपायर|बंद|अपडेट)|आपको गिरफ्तार|गिरफ्तारी वारंट|कानूनी कार्रवाई"),
    _c(r"చివరి తేదీ (?:ఈరోజు|ఈ రోజు|నేడు)|ఖాతా (?:బ్లాక్|నిలిపివేయ|మూసివేయ)|సిమ్ (?:బ్లాక్|డిస్కనెక్ట్)|కేవైసీ[^.\n]{0,30}(?:గడువు|ముగుస్తుంది|అప్‌?డేట్)|అరెస్ట్ చేస్తారు|చట్టపరమైన చర్య"),
]

# ---- forward chains ----------------------------------------------------------------------------------------------------
_CHAIN = [
    _c(r"\b(?:forward|share|send|pass)\b[^.\n]{0,25}?\b(?:\d{1,3}|ten|five|fifteen|twenty)\s+(?:people|persons|friends|contacts|groups|whatsapp groups|members|logon|mandiki)\b"),
    _c(r"\b(?:forward|share|send|pass|bhejo|bhejein)\b[^.\n]{0,25}?\b(?:all|every|sab|sabhi)\s+(?:your\s+|the\s+)?(?:contacts|groups|friends|whatsapp|group)\b"),
    _c(r"\b(?:if you (?:do not|don'?t|dont) (?:share|forward)|(?:otherwise|else)[^.\n]{0,30}(?:bad luck|misfortune|curse))\b"),
    _c(r"\bbad luck\b[^.\n]{0,40}\b(?:share|forward)\b|\b(?:share|forward)\b[^.\n]{0,40}\bbad luck\b"),
    _c(r"\b(?:sabko|sab ko|sabhi ko|\d{1,3} logon ko)\s*(?:forward|share|bhejo)\b"), _c(r"\b(?:sab|all) groups? (?:me|mein|lo)\s*(?:forward|share|bhejo)\b"),
    _c(r"\b(?:andariki|\d{1,3} mandiki)\s*(?:forward|share)\b"),
    _c(r"(?:सबको|सभी को|सभी ग्रुप्?स?\s*में|\d{1,3}\s*(?:लोगों|ग्रुप्?स?)\w*\s*(?:को|में))\s*(?:फॉरवर्ड|फारवर्ड|शेयर|भेजें|भेजो)"),
    _c(r"అందరికీ\s*(?:షేర్|ఫార్వార్డ్|ఫార్వర్డ్)|\d{1,3}\s*(?:గ్రూపులకు|మందికి)\s*(?:షేర్|ఫార్వార్డ్|ఫార్వర్డ్|పంపండి)"),
]

# ---- links -------------------------------------------------------------------------------------------------------------
_SHORT = _c(r"(?<![\w.@-])(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|cutt\.ly|rb\.gy|is\.gd|ow\.ly|shorturl\.at|tiny\.cc|bitly\.com|t\.ly|v\.gd|buff\.ly|rebrand\.ly|s\.id)/[A-Za-z0-9_-]+")
_APK = [_c(r"(?:https?://)?[^\s<>\"']{0,150}?\.apk\b"), _c(r"\b(?:download|install)\s+(?:the\s+|this\s+|our\s+)?(?:\w+\s+){0,2}apk\b")]
_TLDS = ("in", "com", "org", "net", "xyz", "top", "click", "site", "shop", "online", "info", "co", "biz", "link", "club", "app", "vip", "cc", "tk", "ml", "ga",
         "cf", "gq", "icu", "store", "work", "fun", "buzz", "gov", "bank", "io", "me", "us", "pw", "ws", "cfd", "sbs", "live", "life", "website", "today", "digital")
_URL = _c(r"https?://[^\s<>\"'।]{1,300}|(?<![\w@./-])www\.[^\s<>\"'।]{1,300}|(?<![\w@./-])(?:[a-z0-9][a-z0-9-]{0,62}\.){1,6}(?:" + "|".join(_TLDS) + r")(?![\w-])(?:[/:][^\s<>\"'।]{0,200})?")
_STRONG = _c(r"(?<![a-z])(?:gov|pib|rbi|sbi|uidai|pm-|pm\.|pmkisan|yojana|kisan|mygov|hdfc|icici|npci|epfo|aadhaar|aadhar|incometax|income-tax|irctc|ayushman|ujjwala|jandhan)")
_WEAK = _c(r"(?<![a-z])(?:india|bharat|bank|scheme|sahayata|subsidy|ration|loan|kyc|refund|tax|pension)")
_ODD_TLD = {"xyz", "top", "click", "site", "shop", "online", "icu", "buzz", "fun", "vip", "cfd", "sbs", "tk", "ml", "ga", "cf", "gq", "pw", "work", "link", "website"}
_IP = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_MONEY_GOV = _c(r"\brs\.?\s*\d|\b(?:rupees?|lakh|crore|yojana|scheme|government|govt|sarkar|sarkaru|bank|kyc|subsidy|pension|refund|claim|prize|ration|aadhaar|aadhar|pm)\b|₹|रुपये|योजना|सरकार|बैंक|రూపాయ|పథకం|ప్రభుత్వ|బ్యాంక్")
_IMPERS = [
    _c(r"\b(?:this is|message|notice|circular|announcement|alert)\s+(?:is\s+)?(?:from|by|issued by)\s+(?:the\s+)?(?:pib|ministry|rbi|reserve bank|government|govt|sbi|state bank|uidai|income tax|npci|trai|epfo|your bank|bank)\b"),
    _c(r"\bofficial\s+(?:government\s+|govt\s+)?(?:message|notice|announcement|circular|notification)\b"), _c(r"\b(?:issued|announced) by (?:the )?(?:govt|government|ministry|pib|rbi)\b"),
    _c(r"\bdear (?:customer|user|account holder|sir/madam)\b"), _c(r"\bsarkari (?:message|notice|suchna)\b"),
    _c(r"सरकारी (?:संदेश|सूचना)|आधिकारिक (?:संदेश|सूचना)|भारत सरकार की (?:ओर|तरफ)"), _c(r"అధికారిక (?:సందేశం|ప్రకటన)|ప్రభుత్వ (?:సందేశం|ప్రకటన)"),
]

# order: high first, then rule order
_ORDER = ("asks_secret", "upi_trap", "claim_prize", "apk_download", "lookalike_domain", "click_register", "urgency_threat", "forward_chain",
          "shortened_link", "impersonation")
_SEV = {"asks_secret": "high", "upi_trap": "high", "claim_prize": "high", "apk_download": "high", "lookalike_domain": "high",
        "click_register": "medium", "urgency_threat": "medium", "forward_chain": "medium", "shortened_link": "medium", "impersonation": "medium"}

# NOT NATIVE-REVIEWED (hi, te): short natural strings, to be checked by a native speaker.
TEXT = {
    "en": {
        "asks_secret": ("Asks for a secret code or private details", "Banks and the government never ask for your OTP, PIN, password or screen access."),
        "upi_trap": ("Asks you to pay or approve a payment to receive money", "You never need to pay, or enter a UPI PIN, to receive money."),
        "claim_prize": ("Promises a prize or free gift", "Real schemes do not reach you through a lucky win or a forwarded link."),
        "click_register": ("Pushes you to click a link to register or claim", "Real schemes say to apply on the official website or at a government office."),
        "urgency_threat": ("Creates panic or a deadline", "Scammers rush you so that you do not stop to check."),
        "forward_chain": ("Asks you to forward it to many people", "Real government notices do not need chain forwarding."),
        "shortened_link": ("Hides the real web address", "A short link hides where it goes, so you cannot see the real site."),
        "apk_download": ("Asks you to install an app file (.apk)", "An app from a link, not the Play Store, can steal your messages and money."),
        "lookalike_domain": ("The link looks official but is not", "This address is not an official government or bank site."),
        "impersonation": ("Says it is official but links to an unofficial site", "Check who sent it and the web address before you trust it."),
    },
    "hi": {  # NOT NATIVE-REVIEWED
        "asks_secret": ("गुप्त कोड या निजी जानकारी माँगता है", "बैंक और सरकार कभी आपका OTP, PIN, पासवर्ड या स्क्रीन नहीं माँगते।"),
        "upi_trap": ("पैसे पाने के लिए पैसे भेजने को कहता है", "पैसे पाने के लिए कभी पैसे भेजने या UPI PIN डालने की ज़रूरत नहीं होती।"),
        "claim_prize": ("इनाम या मुफ़्त तोहफ़े का वादा करता है", "असली योजनाएँ लॉटरी या फ़ॉरवर्ड किए लिंक से नहीं आतीं।"),
        "click_register": ("रजिस्टर या क्लेम के लिए लिंक दबाने को कहता है", "असली योजना में सरकारी वेबसाइट या दफ़्तर में आवेदन करना होता है।"),
        "urgency_threat": ("डर या जल्दी का माहौल बनाता है", "ठग जल्दबाज़ी कराते हैं ताकि आप जाँच न करें।"),
        "forward_chain": ("बहुत लोगों को भेजने को कहता है", "असली सरकारी सूचना को आगे भेजने की ज़रूरत नहीं होती।"),
        "shortened_link": ("असली वेबसाइट का पता छिपाता है", "छोटा लिंक छिपा देता है कि वह कहाँ ले जाएगा।"),
        "apk_download": ("ऐप फ़ाइल (.apk) डालने को कहता है", "प्ले स्टोर के बाहर के ऐप आपके मैसेज और पैसे चुरा सकते हैं।"),
        "lookalike_domain": ("लिंक सरकारी जैसा दिखता है, पर है नहीं", "यह पता किसी सरकारी या बैंक की असली साइट का नहीं है।"),
        "impersonation": ("खुद को सरकारी बताता है, पर लिंक असली नहीं", "भरोसा करने से पहले भेजने वाले और वेबसाइट का पता जाँचें।"),
    },
    "te": {  # NOT NATIVE-REVIEWED
        "asks_secret": ("రహస్య కోడ్ లేదా వ్యక్తిగత వివరాలు అడుగుతోంది", "బ్యాంకులు, ప్రభుత్వం మీ OTP, PIN, పాస్‌వర్డ్ లేదా స్క్రీన్ ఎప్పుడూ అడగవు."),
        "upi_trap": ("డబ్బు రావాలంటే డబ్బు పంపమని అడుగుతోంది", "డబ్బు అందుకోవడానికి మీరు డబ్బు కట్టాల్సిన లేదా UPI PIN ఇవ్వాల్సిన అవసరం లేదు."),
        "claim_prize": ("బహుమతి లేదా ఉచిత కానుక ఆశ చూపుతోంది", "నిజమైన పథకాలు లాటరీ లేదా ఫార్వార్డ్ లింక్ ద్వారా రావు."),
        "click_register": ("రిజిస్టర్ కోసం లింక్ క్లిక్ చేయమంటోంది", "నిజమైన పథకానికి అధికారిక వెబ్‌సైట్ లేదా ప్రభుత్వ కార్యాలయంలో దరఖాస్తు చేయాలి."),
        "urgency_threat": ("భయం లేదా తొందర కలిగిస్తోంది", "మోసగాళ్లు తొందర పెడతారు, మీరు సరిచూడకుండా ఉండటానికి."),
        "forward_chain": ("చాలా మందికి పంపమని అడుగుతోంది", "నిజమైన ప్రభుత్వ ప్రకటనను అందరికీ ఫార్వార్డ్ చేయాల్సిన అవసరం లేదు."),
        "shortened_link": ("అసలు వెబ్ అడ్రస్ దాచిపెడుతోంది", "చిన్న లింక్ ఎక్కడికి వెళ్తుందో దాచిపెడుతుంది."),
        "apk_download": ("యాప్ ఫైల్ (.apk) ఇన్‌స్టాల్ చేయమంటోంది", "ప్లే స్టోర్ బయట యాప్‌లు మీ మెసేజ్‌లు, డబ్బు దొంగిలించగలవు."),
        "lookalike_domain": ("లింక్ అధికారికంగా కనిపిస్తుంది, కానీ కాదు", "ఈ అడ్రస్ ప్రభుత్వ లేదా బ్యాంక్ అసలు సైట్ కాదు."),
        "impersonation": ("అధికారికం అంటోంది, కానీ లింక్ అసలుది కాదు", "నమ్మే ముందు పంపినవారిని, వెబ్ అడ్రస్‌ను చూడండి."),
    },
}
UI = {
    "en": {"title": "Warning signs in this message",
           "intro": "These are patterns common in scams. They are not a verdict on the facts, and they never change the verdict above.",
           "advice": "Do not share OTPs or PINs. Do not click links you did not expect. Check on the official website by typing its address yourself.",
           "more": "and {n} more", "count1": "1 warning sign", "countn": "{n} warning signs", "all": "Show all {n} signs"},
    "hi": {"title": "इस संदेश में चेतावनी के संकेत",  # NOT NATIVE-REVIEWED
           "intro": "ये ठगी में आम पैटर्न हैं। ये तथ्यों पर फ़ैसला नहीं हैं, और ऊपर के नतीजे को नहीं बदलते।",
           "advice": "OTP या PIN किसी को न बताएँ। अनजान लिंक न दबाएँ। सरकारी वेबसाइट का पता खुद टाइप करके जाँचें।",
           "more": "और {n} संकेत", "count1": "1 चेतावनी संकेत", "countn": "{n} चेतावनी संकेत", "all": "सभी {n} संकेत देखें"},
    "te": {"title": "ఈ సందేశంలో హెచ్చరిక సంకేతాలు",  # NOT NATIVE-REVIEWED
           "intro": "ఇవి మోసాల్లో సాధారణంగా కనిపించే పద్ధతులు. ఇవి వాస్తవాలపై తీర్పు కాదు, పై ఫలితాన్ని మార్చవు.",
           "advice": "OTP లేదా PIN ఎవరికీ చెప్పకండి. ఊహించని లింక్‌లను క్లిక్ చేయకండి. అధికారిక వెబ్‌సైట్ అడ్రస్‌ను మీరే టైప్ చేసి చూడండి.",
           "more": "ఇంకా {n}", "count1": "1 హెచ్చరిక సంకేతం", "countn": "{n} హెచ్చరిక సంకేతాలు", "all": "మొత్తం {n} సంకేతాలు చూడండి"},
}
# A few words per sign for the one-line summary. NOT NATIVE-REVIEWED (hi, te).
SHORT = {
    "en": {"asks_secret": "asks for OTP or PIN", "upi_trap": "asks you to pay first", "claim_prize": "promises a prize",
           "click_register": "pushes a link", "urgency_threat": "panic or deadline", "forward_chain": "chain forward",
           "shortened_link": "hidden link", "apk_download": "app file (.apk)", "lookalike_domain": "suspicious link",
           "impersonation": "fake official"},
    "hi": {"asks_secret": "OTP या पिन माँगता है", "upi_trap": "पहले पैसे माँगता है", "claim_prize": "इनाम का लालच",
           "click_register": "लिंक दबाने को कहता है", "urgency_threat": "डर या जल्दबाज़ी", "forward_chain": "आगे भेजने को कहता है",
           "shortened_link": "छिपा हुआ लिंक", "apk_download": "ऐप फ़ाइल (.apk)", "lookalike_domain": "संदिग्ध लिंक",
           "impersonation": "सरकारी होने का दिखावा"},
    "te": {"asks_secret": "OTP లేదా పిన్ అడుగుతోంది", "upi_trap": "ముందు డబ్బు అడుగుతోంది", "claim_prize": "బహుమతి ఆశ",
           "click_register": "లింక్ క్లిక్ చేయమంటోంది", "urgency_threat": "భయం లేదా తొందర", "forward_chain": "ఫార్వార్డ్ చేయమంటోంది",
           "shortened_link": "దాచిన లింక్", "apk_download": "యాప్ ఫైల్ (.apk)", "lookalike_domain": "అనుమానాస్పద లింక్",
           "impersonation": "అధికారికం అని నటన"},
}
VISIBLE = 2        # signs shown open; the rest sit inside a <details>

CSS = """
.signs{margin:16px 0 4px;padding:10px 14px 12px;border:2px solid var(--mis);border-left-width:8px;border-radius:3px;background:color-mix(in srgb,var(--mis) 9%,var(--card))}
.signs h3{font-family:var(--serif);margin:0;font-size:19px;line-height:1.25}
.signs .sg-sum{margin:2px 0 4px;font-size:15px;font-weight:600;overflow-wrap:anywhere}
.signs .sg-intro,.signs .sg-adv{font-size:14px;line-height:1.45;margin:6px 0 0;color:var(--mute)}
.signs ul{list-style:none;margin:0;padding:0}.signs li{padding:8px 0;border-top:1px solid color-mix(in srgb,var(--ink) 20%,transparent);overflow-wrap:anywhere}
.signs li b{display:block;font-size:16px;line-height:1.35}.signs .sg-hi{font-family:var(--mono);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--mis);margin-right:6px}
.signs .sg-why{display:block;font-size:14.5px;line-height:1.45}.signs q{display:block;margin-top:3px;font-family:var(--mono);font-size:12.5px;color:var(--mute)}
.signs details.sg-all{border:0;padding:0;margin:0}.signs details.sg-all summary{display:flex;align-items:center;min-height:44px;font-size:15px;font-weight:600;border-top:1px solid color-mix(in srgb,var(--ink) 20%,transparent)}
.signs .sg-adv{margin:8px 0 0;color:var(--ink);font-weight:600}
@media(max-width:560px){.signs{margin:12px 0 2px;padding:8px 12px 10px;border-left-width:6px}.signs h3{font-size:16.5px}.signs .sg-sum{font-size:14px;line-height:1.35}.signs li{padding:5px 0}
.signs li b{font-size:14.5px;line-height:1.3}.signs .sg-why{font-size:13.5px;line-height:1.35}.signs q{font-size:12px;margin-top:2px}.signs .sg-intro,.signs .sg-adv{font-size:12.5px;line-height:1.4;margin-top:5px}}
"""


def _snip(s: str) -> str:
    return s.strip()[:MAX_EVIDENCE]


def _find(text: str, pats, guard_neg: bool = False):
    """First verbatim match of any pattern (optionally skipping matches that sit in a 'never share' sentence)."""
    best = None
    for p in pats:
        for m in p.finditer(text):
            if guard_neg and _NEG.search(text[max(0, m.start() - 40): m.end() + 15]):
                continue
            ev = m.group(0)
            if "\n" in ev:
                ev = ev.split("\n")[0]
            if ev.strip() and (best is None or m.start() < best[0]):
                best = (m.start(), ev)
            break
    return best[1].strip()[:MAX_EVIDENCE] if best else None


def _links(text: str):
    seen, out = set(), []
    for m in _URL.finditer(text):
        u = m.group(0).rstrip(".,;:!?)]}'\"।")
        if u and u not in seen:
            seen.add(u); out.append(u)
        if len(out) >= 40:
            break
    return out


def _netloc(u: str) -> str:
    rest = re.sub(r"^[a-z][a-z0-9+.-]*://", "", u, flags=re.I)
    return re.split(r"[/?#]", rest, maxsplit=1)[0]


def _link_signs(text: str, found: dict) -> None:
    links = _links(text)
    hosts = []
    money = bool(_MONEY_GOV.search(text))
    for u in links:
        full = u if "://" in u else "https://" + u
        h = host_of(full)
        netloc = _netloc(u).lower()
        trick = False
        if not h:                                              # backslash / odd netloc: browsers may read it differently
            if ("\\" in u or "@" in u or "%" in netloc) and _STRONG.search(netloc):
                trick = True
            else:
                continue
        if "@" in netloc and not trick:                          # https://pib.gov.in@evil.com/ : the part before @ is decoration
            user = netloc.rsplit("@", 1)[0]
            if _STRONG.search(user) and not is_official(full.replace(user + "@", "", 1)):
                trick = True
        if trick:
            found.setdefault("lookalike_domain", _snip(u))
            hosts.append(("", u)); continue
        official = is_official(full)
        hosts.append((h, u))
        if official or is_factchecker(full):
            continue
        tld = h.rsplit(".", 1)[-1]
        strong = bool(_STRONG.search(h))
        weak = bool(_WEAK.search(h)) and (tld in _ODD_TLD or h.count("-") >= 2)
        odd = (tld in _ODD_TLD or bool(_IP.match(h))) and money
        if strong or weak or odd:
            found.setdefault("lookalike_domain", _snip(h))
    # impersonation: claims to be official while every link is non-official
    if hosts and all(not (h and (is_official("https://" + h) or is_factchecker("https://" + h))) for h, _ in hosts):
        ev = _find(text, _IMPERS)
        if ev:
            found.setdefault("impersonation", ev)


def analyze(text) -> list:
    """Return the warning signs for `text`: [{id, severity, title, why, evidence}], high severity first. Pure and deterministic."""
    if not isinstance(text, str) or not text.strip():
        return []
    text = text[:MAX_INPUT]
    found: dict = {}
    for sid, pats, neg in (("asks_secret", _SECRET, True), ("upi_trap", _UPI, False), ("claim_prize", _PRIZE, False), ("click_register", _CLICK, False),
                           ("urgency_threat", _URG, False), ("forward_chain", _CHAIN, False)):
        ev = _find(text, pats, guard_neg=neg)
        if ev:
            found[sid] = ev
    m = _SHORT.search(text)
    if m:
        found["shortened_link"] = m.group(0)[:MAX_EVIDENCE]
    ev = _find(text, _APK)
    if ev:
        found["apk_download"] = ev
    _link_signs(text, found)
    out = []
    for sid in _ORDER:
        if sid in found:
            t, w = TEXT["en"][sid]
            out.append({"id": sid, "severity": _SEV[sid], "title": t, "why": w, "evidence": found[sid]})
    out.sort(key=lambda s: 0 if s["severity"] == "high" else 1)      # stable: keeps rule order inside each severity
    return out


def _item(s: dict, tx: dict) -> str:
    sid = s.get("id")
    title, why = tx.get(sid) or TEXT["en"].get(sid) or (s.get("title", ""), s.get("why", ""))
    ev = f"<q>{html.escape(str(s.get('evidence', '')))}</q>" if s.get("evidence") else ""
    return f'<li><b>{html.escape(str(title))}</b><span class="sg-why">{html.escape(str(why))}</span>{ev}</li>'


def _summary(ordered: list, lang: str) -> str:
    """'3 warning signs: asks for OTP or PIN, suspicious link, chain forward' (at most MAX_SHOWN labels, then 'and N more')."""
    ui, short = UI[lang], SHORT[lang]
    n = len(ordered)
    head = ui["count1"] if n == 1 else ui["countn"].format(n=n)
    labels = []
    for s in ordered[:MAX_SHOWN]:
        sid = s.get("id")
        labels.append(short.get(sid) or SHORT["en"].get(sid) or str(s.get("title", "")))
    tail = ui["more"].format(n=n - MAX_SHOWN) if n > MAX_SHOWN else ""
    return f"{head}: " + ", ".join(labels) + (f" {tail}" if tail else "")


def signs_html(signs, lang: str = "en") -> str:
    """The advisory box, compact: title, a one-line summary, the first two signs open and the rest inside a native <details>.
    Empty string when there is nothing to show. Everything user-controlled is escaped."""
    if not signs:
        return ""
    lang = lang if lang in UI else "en"      # only en, hi and te are translated; every other language shows the English box (NOT translated yet)
    ordered = sorted((s for s in signs if isinstance(s, dict)), key=lambda s: 0 if s.get("severity") == "high" else 1)
    if not ordered:
        return ""
    ui, tx = UI[lang], TEXT[lang]
    first = "".join(_item(s, tx) for s in ordered[:VISIBLE])
    rest = ""
    if len(ordered) > VISIBLE:
        rest = (f'<details class="sg-all"><summary>{html.escape(ui["all"].format(n=len(ordered)))}</summary>'
                f'<ul>{"".join(_item(s, tx) for s in ordered[VISIBLE:])}</ul></details>')
    return (f'<section class="signs" id="signs" lang="{lang}" aria-labelledby="signs-h"><h3 id="signs-h">{html.escape(ui["title"])}</h3>'
            f'<p class="sg-sum">{html.escape(_summary(ordered, lang))}</p><ul>{first}</ul>{rest}'
            f'<p class="sg-intro">{html.escape(ui["intro"])}</p><p class="sg-adv">{html.escape(ui["advice"])}</p></section>')
