"""Verdict-card strings. Fixed, short, AI-written templates that are not yet reviewed by native speakers - never machine-translated at runtime.
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


# ================================================================================================================================
# Indian languages added by the LANG work package.
# NOT NATIVE-REVIEWED: every string below was written by an AI model and has not been checked by a native speaker.
# Reviewers: see docs/languages.md. Each table keeps the hi/te structure and the {src} placeholder.
# ================================================================================================================================
# Manipuri (Meitei, mni) has NO entries on purpose: Meitei Mayek verdict wording cannot be authored reliably without a native speaker, and
# a wrong word on a fact-check card is worse than English. Every lookup goes through tr()/text_lang(), so a Manipuri reply is the English
# card until a reviewer adds "mni" rows to the tables below and removes it from ENGLISH_ONLY.
ENGLISH_ONLY = frozenset({"mni"})

LABEL.update({  # NOT NATIVE-REVIEWED
 "bn": {"TRUE": "সত্য", "FALSE": "মিথ্যা", "MISLEADING": "বিভ্রান্তিকর", "UNVERIFIED": "যাচাই হয়নি"},
 "as": {"TRUE": "সঁচা", "FALSE": "মিছা", "MISLEADING": "বিভ্ৰান্তিকৰ", "UNVERIFIED": "যাচাই কৰা হোৱা নাই"},
 "mr": {"TRUE": "खरा", "FALSE": "खोटा", "MISLEADING": "दिशाभूल करणारा", "UNVERIFIED": "पुष्टी झाली नाही"},  # masculine, agrees with दावा in WHY (Muse review 2026-11-13)
 "kok": {"TRUE": "खरें", "FALSE": "खोटें", "MISLEADING": "दिशाभूल करपी", "UNVERIFIED": "खात्री जाल्ली ना"},
 "ne": {"TRUE": "सत्य", "FALSE": "झुटो", "MISLEADING": "भ्रामक", "UNVERIFIED": "पुष्टि भएको छैन"},
 "ta": {"TRUE": "உண்மை", "FALSE": "பொய்", "MISLEADING": "தவறாக வழிநடத்துகிறது", "UNVERIFIED": "உறுதிசெய்யப்படவில்லை"},
 "gu": {"TRUE": "સાચું", "FALSE": "ખોટું", "MISLEADING": "ભ્રામક", "UNVERIFIED": "ખાતરી થઈ નથી"},
 "ur": {"TRUE": "سچ", "FALSE": "جھوٹ", "MISLEADING": "گمراہ کن", "UNVERIFIED": "تصدیق نہیں ہوئی"},
 "kn": {"TRUE": "ನಿಜ", "FALSE": "ಸುಳ್ಳು", "MISLEADING": "ದಾರಿತಪ್ಪಿಸುವಂಥದ್ದು", "UNVERIFIED": "ಖಚಿತವಾಗಿಲ್ಲ"},
 "or": {"TRUE": "ସତ", "FALSE": "ମିଛ", "MISLEADING": "ଭ୍ରମାତ୍ମକ", "UNVERIFIED": "ଯାଞ୍ଚ ହୋଇନାହିଁ"},
 "ml": {"TRUE": "സത്യം", "FALSE": "കള്ളം", "MISLEADING": "തെറ്റിദ്ധരിപ്പിക്കുന്നത്", "UNVERIFIED": "സ്ഥിരീകരിച്ചിട്ടില്ല"},
 "pa": {"TRUE": "ਸੱਚ", "FALSE": "ਝੂਠ", "MISLEADING": "ਗੁੰਮਰਾਹਕੁੰਨ", "UNVERIFIED": "ਪੁਸ਼ਟੀ ਨਹੀਂ ਹੋਈ"},
})
WHY.update({  # NOT NATIVE-REVIEWED
 "bn": {"FALSE": "{src}-এর তথ্য অনুযায়ী এই দাবিটি মিথ্যা।",
        "TRUE": "{src} এটি নিশ্চিত করেছে।",
        "MISLEADING": "এর কিছু অংশ সত্য ({src}), কিন্তু সংখ্যা, তারিখ বা উপস্থাপনা বিকৃত করা হয়েছে।",
        "UNVERIFIED": "এটি নিশ্চিত বা অস্বীকার করার মতো কোনও সরকারি সূত্র আমরা পাইনি। এটিকে সত্য বলে ধরে নেবেন না।"},
 "as": {"FALSE": "{src}ৰ মতে এই দাবীটো মিছা।",
        "TRUE": "{src}এ ইয়াক নিশ্চিত কৰিছে।",
        "MISLEADING": "ইয়াৰ কিছু অংশ সঁচা ({src}), কিন্তু সংখ্যা, তাৰিখ বা কথাৰ ধৰণ ভুলকৈ দাঙি ধৰা হৈছে।",
        "UNVERIFIED": "ইয়াক নিশ্চিত বা অস্বীকাৰ কৰা কোনো চৰকাৰী উৎস আমি পোৱা নাই। ইয়াক সঁচা বুলি নাভাবিব।"},
 "mr": {"FALSE": "{src} नुसार हा दावा खोटा आहे.",
        "TRUE": "{src} ने याला दुजोरा दिला आहे.",
        "MISLEADING": "यातील काही भाग खरा आहे ({src}), पण आकडे, तारखा किंवा सांगण्याची पद्धत चुकीची मांडली आहे.",
        "UNVERIFIED": "याला दुजोरा देणारा किंवा नाकारणारा कोणताही सरकारी स्रोत आम्हाला मिळाला नाही. हे खरे समजू नका."},
 "kok": {"FALSE": "{src} प्रमाणें हो दावो खोटो आसा.",
         "TRUE": "{src} न हें खरें अशें सांगलां.",
         "MISLEADING": "हांतलो थोडो भाग खरो आसा ({src}), पूण आकडे, तारीख वा सांगपाची तऱ्हा चुकीची मांडल्या.",
         "UNVERIFIED": "हाका दुजोरो दिवपी वा न्हयकारपी सरकारी स्रोत आमकां मेळ्ळो ना. हें खरें अशें धरूं नाकात."},
 "ne": {"FALSE": "{src} का अनुसार यो दाबी झुटो हो।",
        "TRUE": "{src} ले यसको पुष्टि गरेको छ।",
        "MISLEADING": "यसको केही भाग सही छ ({src}), तर सङ्ख्या, मिति वा भनाइको तरिका बिगारेर प्रस्तुत गरिएको छ।",
        "UNVERIFIED": "यसलाई पुष्टि वा खण्डन गर्ने कुनै सरकारी स्रोत हामीले फेला पारेनौं। यसलाई सत्य नमान्नुहोस्।"},
 "ta": {"FALSE": "{src} கூற்றுப்படி இந்தத் தகவல் பொய்.",
        "TRUE": "{src} இதை உறுதிசெய்துள்ளது.",
        "MISLEADING": "இதில் ஒரு பகுதி உண்மை ({src}), ஆனால் எண்கள், தேதிகள் அல்லது சொன்ன விதம் திரிக்கப்பட்டுள்ளது.",
        "UNVERIFIED": "இதை உறுதிசெய்யவோ மறுக்கவோ அதிகாரபூர்வ ஆதாரம் எதுவும் எங்களுக்குக் கிடைக்கவில்லை. இதை உண்மை என்று எடுத்துக்கொள்ள வேண்டாம்."},
 "gu": {"FALSE": "{src} મુજબ આ દાવો ખોટો છે.",
        "TRUE": "{src} એ આની પુષ્ટિ કરી છે.",
        "MISLEADING": "આનો થોડો ભાગ સાચો છે ({src}), પણ આંકડા, તારીખો કે રજૂઆતની રીત ખોટી રીતે બતાવવામાં આવી છે.",
        "UNVERIFIED": "આની પુષ્ટિ કે ખંડન કરતો કોઈ સરકારી સ્રોત અમને મળ્યો નથી. આને સાચું માનશો નહીં."},
 "ur": {"FALSE": "{src} کے مطابق یہ دعویٰ جھوٹا ہے۔",
        "TRUE": "{src} نے اس کی تصدیق کی ہے۔",
        "MISLEADING": "اس کا کچھ حصہ درست ہے ({src})، لیکن اعداد، تاریخیں یا بات کا انداز غلط پیش کیا گیا ہے۔",
        "UNVERIFIED": "ہمیں اس کی تصدیق یا تردید کرنے والا کوئی سرکاری ذریعہ نہیں ملا۔ اسے سچ نہ سمجھیں۔"},
 "kn": {"FALSE": "{src} ಪ್ರಕಾರ ಈ ಸುದ್ದಿ ಸುಳ್ಳು.",
        "TRUE": "{src} ಇದನ್ನು ದೃಢಪಡಿಸಿದೆ.",
        "MISLEADING": "ಇದರಲ್ಲಿ ಸ್ವಲ್ಪ ಭಾಗ ನಿಜ ({src}), ಆದರೆ ಸಂಖ್ಯೆಗಳು, ದಿನಾಂಕಗಳು ಅಥವಾ ಹೇಳಿದ ರೀತಿಯನ್ನು ತಿರುಚಲಾಗಿದೆ.",
        "UNVERIFIED": "ಇದನ್ನು ದೃಢಪಡಿಸುವ ಅಥವಾ ಅಲ್ಲಗಳೆಯುವ ಯಾವುದೇ ಅಧಿಕೃತ ಮೂಲ ನಮಗೆ ಸಿಗಲಿಲ್ಲ. ಇದನ್ನು ನಿಜವೆಂದು ಭಾವಿಸಬೇಡಿ."},
 "or": {"FALSE": "{src} ଅନୁସାରେ ଏହି ଦାବି ମିଛ।",
        "TRUE": "{src} ଏହାକୁ ନିଶ୍ଚିତ କରିଛି।",
        "MISLEADING": "ଏହାର କିଛି ଅଂଶ ସତ ({src}), କିନ୍ତୁ ସଂଖ୍ୟା, ତାରିଖ କିମ୍ବା କହିବା ଢଙ୍ଗ ବିକୃତ କରାଯାଇଛି।",
        "UNVERIFIED": "ଏହାକୁ ନିଶ୍ଚିତ କିମ୍ବା ଖଣ୍ଡନ କରୁଥିବା କୌଣସି ସରକାରୀ ସୂତ୍ର ଆମେ ପାଇଲୁ ନାହିଁ। ଏହାକୁ ସତ ବୋଲି ଧରନ୍ତୁ ନାହିଁ।"},
 "ml": {"FALSE": "{src} പ്രകാരം ഈ വാർത്ത തെറ്റാണ്.",
        "TRUE": "{src} ഇത് സ്ഥിരീകരിച്ചിട്ടുണ്ട്.",
        "MISLEADING": "ഇതിൽ കുറച്ച് ഭാഗം ശരിയാണ് ({src}), പക്ഷേ സംഖ്യകളോ തീയതികളോ പറഞ്ഞ രീതിയോ വളച്ചൊടിച്ചിരിക്കുന്നു.",
        "UNVERIFIED": "ഇത് സ്ഥിരീകരിക്കുന്നതോ നിഷേധിക്കുന്നതോ ആയ ഔദ്യോഗിക ഉറവിടം ഞങ്ങൾക്ക് കിട്ടിയില്ല. ഇത് സത്യമെന്ന് കരുതരുത്."},
 "pa": {"FALSE": "{src} ਅਨੁਸਾਰ ਇਹ ਦਾਅਵਾ ਝੂਠ ਹੈ।",
        "TRUE": "{src} ਨੇ ਇਸ ਦੀ ਪੁਸ਼ਟੀ ਕੀਤੀ ਹੈ।",
        "MISLEADING": "ਇਸ ਦਾ ਕੁਝ ਹਿੱਸਾ ਸਹੀ ਹੈ ({src}), ਪਰ ਅੰਕੜੇ, ਤਾਰੀਖਾਂ ਜਾਂ ਗੱਲ ਦਾ ਢੰਗ ਗਲਤ ਪੇਸ਼ ਕੀਤਾ ਗਿਆ ਹੈ।",
        "UNVERIFIED": "ਸਾਨੂੰ ਇਸ ਦੀ ਪੁਸ਼ਟੀ ਜਾਂ ਖੰਡਨ ਕਰਨ ਵਾਲਾ ਕੋਈ ਸਰਕਾਰੀ ਸਰੋਤ ਨਹੀਂ ਮਿਲਿਆ। ਇਸ ਨੂੰ ਸੱਚ ਨਾ ਮੰਨੋ।"},
})
SOURCE_LABEL.update({  # NOT NATIVE-REVIEWED
 "bn": "সূত্র", "as": "উৎস", "mr": "स्रोत", "kok": "स्रोत", "ne": "स्रोत", "ta": "ஆதாரம்", "gu": "સ્રોત", "ur": "ماخذ",
 "kn": "ಮೂಲ", "or": "ସୂତ୍ର", "ml": "ഉറവിടം", "pa": "ਸਰੋਤ"})
FC_NOTE.update({  # NOT NATIVE-REVIEWED
 "bn": "ফ্যাক্ট-চেকার (সরকারি নয়)", "as": "ফেক্ট-চেকাৰ (চৰকাৰী নহয়)", "mr": "फॅक्ट-चेकर (सरकारी नाही)",
 "kok": "फॅक्ट-चेकर (सरकारी न्हय)", "ne": "फ्याक्ट-चेकर (सरकारी होइन)", "ta": "உண்மை சரிபார்ப்பாளர் (அதிகாரபூர்வம் அல்ல)",
 "gu": "ફેક્ટ-ચેકર (સરકારી નથી)", "ur": "فیکٹ چیکر (سرکاری نہیں)", "kn": "ಫ್ಯಾಕ್ಟ್-ಚೆಕರ್ (ಅಧಿಕೃತವಲ್ಲ)",
 "or": "ଫ୍ୟାକ୍ଟ-ଚେକର (ସରକାରୀ ନୁହେଁ)", "ml": "ഫാക്ട്-ചെക്കർ (ഔദ്യോഗികമല്ല)", "pa": "ਫੈਕਟ-ਚੈਕਰ (ਸਰਕਾਰੀ ਨਹੀਂ)"})
NOCLAIM.update({  # NOT NATIVE-REVIEWED
 "bn": "এই বার্তায় যাচাই করার মতো কোনও তথ্যগত দাবি পাওয়া যায়নি। যে দাবিটি যাচাই করতে চান, শুধু সেটি পেস্ট করুন।",
 "as": "এই বাৰ্তাত যাচাই কৰিব পৰা কোনো তথ্যভিত্তিক দাবী পোৱা নগ'ল। যিটো দাবী যাচাই কৰিব বিচাৰে, সেইটো মাত্ৰ পেষ্ট কৰক।",
 "mr": "या संदेशात तपासता येईल असा कोणताही तथ्यात्मक दावा सापडला नाही. जो दावा तपासायचा आहे तो नेमका पेस्ट करा.",
 "kok": "ह्या संदेशांत तपासपा सारको खबरेचो दावो मेळ्ळो ना. जो दावो तपासपाचो आसा तो मात्र पेस्ट करात.",
 "ne": "यो सन्देशमा जाँच गर्न मिल्ने कुनै तथ्यपरक दाबी भेटिएन। जुन दाबी जाँच गर्नुपर्ने हो, त्यही मात्र टाँस्नुहोस्।",
 "ta": "இந்தச் செய்தியில் சரிபார்க்கக்கூடிய உண்மைக் கூற்று எதுவும் இல்லை. சரிபார்க்க வேண்டிய கூற்றை மட்டும் ஒட்டவும்.",
 "gu": "આ સંદેશમાં તપાસી શકાય એવો કોઈ તથ્યાત્મક દાવો મળ્યો નથી. જે દાવો તપાસવો છે તે જ પેસ્ટ કરો.",
 "ur": "اس پیغام میں جانچنے کے قابل کوئی حقیقت پر مبنی دعویٰ نہیں ملا۔ جس دعوے کی جانچ کرنی ہے صرف وہی پیسٹ کریں۔",
 "kn": "ಈ ಸಂದೇಶದಲ್ಲಿ ಪರಿಶೀಲಿಸಬಹುದಾದ ಯಾವುದೇ ವಾಸ್ತವ ಹೇಳಿಕೆ ಕಂಡುಬಂದಿಲ್ಲ. ಪರಿಶೀಲಿಸಬೇಕಾದ ಹೇಳಿಕೆಯನ್ನು ಮಾತ್ರ ಅಂಟಿಸಿ.",
 "or": "ଏହି ବାର୍ତ୍ତାରେ ଯାଞ୍ଚ କରିବା ଭଳି କୌଣସି ତଥ୍ୟଭିତ୍ତିକ ଦାବି ମିଳିଲା ନାହିଁ। ଯେଉଁ ଦାବି ଯାଞ୍ଚ କରିବାକୁ ଚାହାଁନ୍ତି କେବଳ ତାହା ପେଷ୍ଟ କରନ୍ତୁ।",
 "ml": "ഈ സന്ദേശത്തിൽ പരിശോധിക്കാവുന്ന വസ്തുതാപരമായ അവകാശവാദം ഒന്നും കണ്ടില്ല. പരിശോധിക്കേണ്ട അവകാശവാദം മാത്രം ഒട്ടിക്കുക.",
 "pa": "ਇਸ ਸੁਨੇਹੇ ਵਿੱਚ ਜਾਂਚਣ ਯੋਗ ਕੋਈ ਤੱਥਾਂ ਵਾਲਾ ਦਾਅਵਾ ਨਹੀਂ ਮਿਲਿਆ। ਜਿਸ ਦਾਅਵੇ ਦੀ ਜਾਂਚ ਕਰਨੀ ਹੈ ਸਿਰਫ਼ ਉਹੀ ਪੇਸਟ ਕਰੋ।"})
NOCLAIM_LABEL.update({  # NOT NATIVE-REVIEWED
 "bn": "কোনও দাবি পাওয়া যায়নি", "as": "কোনো দাবী পোৱা নগ'ল", "mr": "कोणताही दावा सापडला नाही", "kok": "दावो मेळ्ळो ना",
 "ne": "कुनै दाबी भेटिएन", "ta": "கூற்று எதுவும் இல்லை", "gu": "કોઈ દાવો મળ્યો નથી", "ur": "کوئی دعویٰ نہیں ملا",
 "kn": "ಯಾವುದೇ ಹೇಳಿಕೆ ಇಲ್ಲ", "or": "କୌଣସି ଦାବି ମିଳିଲା ନାହିଁ", "ml": "അവകാശവാദം ഇല്ല", "pa": "ਕੋਈ ਦਾਅਵਾ ਨਹੀਂ ਮਿਲਿਆ"})


# "What Sach checked" panel under an UNVERIFIED live result (sach/honesty.py). Counts are filled in by the caller from the trace.
UNVERIFIED_PANEL = {
 "en": {"title": "What Sach checked", "claims": "Claims checked: {n}",
        "official": "Official pages judged that neither confirmed nor denied the claim: {n}", "pib": "PIB pages judged: {n}",
        "meaning_title": "What UNVERIFIED means",
        "meaning": "Not confirmed or denied by the official sources Sach could read. It does not mean probably true, and it does not mean probably false.",
        "next_title": "What to do next",
        "next": "Do not forward it until it is checked. Ask PIB Fact Check or a fact-checker with the buttons below. If the message has a link or UPI ID, check it in the link checker (#linkcheck).",
        "scope": "PIB covers the Union Government; for a state-level matter ask that state's department."},
 # NOT NATIVE-REVIEWED
 "hi": {"title": "Sach ने क्या जाँचा", "claims": "जाँचे गए दावे: {n}",
        "official": "सरकारी पेज जिन्हें जाँचा गया और जिनमें न पुष्टि हुई न खंडन: {n}", "pib": "जाँचे गए PIB पेज: {n}",
        "meaning_title": "UNVERIFIED का मतलब",
        "meaning": "Sach जिन सरकारी स्रोतों को पढ़ पाया, उनमें इसकी न पुष्टि हुई न खंडन। इसका मतलब यह नहीं कि यह शायद सच है, और यह भी नहीं कि यह शायद झूठ है।",
        "next_title": "आगे क्या करें",
        "next": "जाँच होने तक इसे आगे न भेजें। नीचे के बटनों से PIB Fact Check या किसी फैक्ट-चेकर से पूछें। संदेश में कोई लिंक या UPI ID हो तो लिंक चेकर (#linkcheck) में जाँचें।",
        "scope": "PIB केंद्र सरकार को कवर करता है; राज्य से जुड़े मामले में उस राज्य के विभाग से पूछें।"},
 # NOT NATIVE-REVIEWED
 "te": {"title": "Sach ఏం తనిఖీ చేసింది", "claims": "తనిఖీ చేసిన ప్రకటనలు: {n}",
        "official": "ఈ ప్రకటనను ధృవీకరించని, ఖండించని అధికారిక పేజీలు: {n}", "pib": "తనిఖీ చేసిన PIB పేజీలు: {n}",
        "meaning_title": "UNVERIFIED అంటే ఏమిటి",
        "meaning": "Sach చదవగలిగిన అధికారిక మూలాలు దీనిని ధృవీకరించలేదు, ఖండించలేదు. ఇది బహుశా నిజం అని కాదు, బహుశా అబద్ధం అని కూడా కాదు.",
        "next_title": "తదుపరి ఏం చేయాలి",
        "next": "తనిఖీ అయ్యే వరకు దీనిని ఫార్వర్డ్ చేయవద్దు. కింద ఉన్న బటన్లతో PIB Fact Check లేదా ఫ్యాక్ట్-చెకర్‌ను అడగండి. సందేశంలో లింక్ లేదా UPI ID ఉంటే లింక్ చెకర్ (#linkcheck)లో తనిఖీ చేయండి.",
        "scope": "PIB కేంద్ర ప్రభుత్వాన్ని కవర్ చేస్తుంది; రాష్ట్ర స్థాయి విషయమైతే ఆ రాష్ట్ర శాఖను అడగండి."},
}


# ---- lookups that can never raise: a language missing from a table falls back to English ------------------------------------------
def tr(table: dict, lang: str):
    """table[lang], or the English entry when this language has none (Manipuri today, or any language added to SUPPORTED later)."""
    return table.get(lang) or table["en"]


def text_lang(lang: str) -> str:
    """The language the card text is really written in: the chosen language, or 'en' when the card falls back to English."""
    return lang if lang in LABEL and lang not in ENGLISH_ONLY else "en"
