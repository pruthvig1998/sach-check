"""The LANG work package: all major Indian languages. Everything offline (fake retriever, fake LLM, in-process server).

NOT NATIVE-REVIEWED: every non-English sentence in this file was written by an AI model to look like a family-group forward. They are test
inputs for script and marker detection, not reviewed translations; a native speaker should replace weak ones (docs/languages.md)."""
import json
import re
import urllib.request as _ur
import urllib.parse as _up

import pytest

import sach.i18n as I18N
import sach.site as SITE
import sach.telegram_bot as T
import sach.web as W
from sach import extract, lang as L, scamsigns, stance, store, voice
from sach.card import render_card
from sach.extract import extract_claims
from sach.models import Evidence, TIER_PIB
from sach.pipeline import check_forward
from tests.test_sach import _post, server  # noqa: F401  (server is a fixture)

NEW = [c for c in L.SUPPORTED if c not in ("en", "hi", "te", "tl")]
TS = "2026-11-12T10:00:00+00:00"

# ---------------------------------------------------------------------------------------------------------------- realistic forwards
FORWARDS = {  # NOT NATIVE-REVIEWED
    "bn": ["সরকার প্রতিটি মহিলাকে ১০০০ টাকা দিচ্ছে বলে একটি বার্তা ছড়াচ্ছে। এটি ভুয়া খবর।",
           "প্রধানমন্ত্রী কিষাণ যোজনায় কৃষকরা বছরে ৬০০০ টাকা পাবেন বলে দাবি করা হচ্ছে।",
           "সব রেশন কার্ড আগামীকাল থেকে বাতিল হয়ে যাবে এই বার্তাটি মিথ্যা, দয়া করে শেয়ার করবেন না।"],
    "as": ["চৰকাৰে প্ৰতিগৰাকী মহিলাক ১০০০ টকা দিব বুলি এটা বাৰ্তা প্ৰচাৰ হৈছে। এয়া মিছা খবৰ।",
           "অসম চৰকাৰৰ নামত চলি থকা এই বাৰ্তাটো সঁচা নহয়, ইয়াত থকা লিংকত ক্লিক নকৰিব।",
           "মোৰ ঘৰৰ সকলোৰে বাবে ৫০০ টকাৰ সহায় পোৱা যাব বুলি কোৱা হৈছে।"],
    "mni": ["ꯁꯔꯀꯥꯔꯅꯥ ꯅꯨꯄꯤ ꯈꯨꯗꯤꯡꯃꯛꯇꯥ ꯇꯥꯀꯥ ꯄꯤꯔꯤ ꯍꯥꯌꯅꯥ ꯋꯥꯐꯃꯁꯤ ꯌꯧꯍꯜꯂꯤ꯫",
            "ꯈꯅꯤꯒꯤ ꯍꯧꯅꯥ ꯑꯣꯏꯅꯥ ꯔꯦꯁꯟ ꯀꯥꯔꯗ ꯄꯨꯝꯅꯃꯛ ꯕꯟꯗ ꯑꯣꯏꯒꯅꯤ ꯍꯥꯌꯅꯥ ꯍꯥꯌꯔꯤ꯫",
            "ꯄꯤꯑꯦꯝ ꯀꯤꯁꯥꯟ ꯌꯣꯖꯅꯥꯗꯥ ꯂꯧꯃꯤ ꯈꯨꯗꯤꯡꯃꯛꯅꯥ ꯆꯍꯤ ꯑꯃꯗꯥ ꯇꯥꯀꯥ ꯌꯧꯒꯅꯤ꯫"],     # script only: may not be natural Meitei
    "mr": ["केंद्र सरकार प्रत्येक महिलेला १००० रुपये देणार आहे. ही बातमी खोटी आहे आणि कृपया शेअर करा.",
           "महाराष्ट्र सरकारच्या नावाने फिरणारा हा संदेश खोटा आहे. असे कोणतेही पैसे मिळणार नाहीत.",
           "उद्यापासून सर्व रेशन कार्ड बंद होणार आहेत असे सांगितले जात आहे, पण ही अफवा आहे आणि अधिकृत सूचना नाही."],
    "kok": ["सरकार दरेका बायलेक १००० रुपया दिता अशें सांगता. हो दावो खोटो आसा आनी तुमी हें शेयर करूं नाकात.",
            "हांव तुमकां सांगता की हो संदेश खोटो आसा. सरकारान अशें कांयच जाहीर केल्लें ना.",
            "ही खबर खरी आसा काय ना हें तपासपाक खातीर आमी सरकारी संकेतस्थळ पळोवपाक जाय आसात."],
    "ne": ["सरकारले सबै महिलालाई १००० रुपैयाँ दिने भनेको छ। यो खबर झुटो हो र पनि सबैले शेयर गरेका छन्।",
           "प्रधानमन्त्रीको नाममा फैलिएको यो सन्देश झुटो छ, सबै जनालाई यो सन्देश पठाउन लागि भनिएको छ।",
           "आजबाट सबै राशन कार्ड बन्द हुन्छ भन्ने खबर फैलिएको छ तर यस्तो कुनै निर्णय भएको छैन, यो अफवाह हो।"],
    "ta": ["அரசு ஒவ்வொரு பெண்ணுக்கும் ரூ.1000 வழங்குகிறது என்ற செய்தி பரவி வருகிறது. இது பொய்.",
           "நாளை முதல் அனைத்து ரேஷன் கார்டுகளும் ரத்து செய்யப்படும் என்று வாட்ஸ்அப்பில் தகவல் பரவுகிறது.",
           "பிரதமர் கிசான் திட்டத்தில் விவசாயிகளுக்கு ஆண்டுக்கு ரூ.6000 கிடைக்கும் என்பது உண்மை அல்ல."],
    "gu": ["સરકાર દરેક મહિલાને 1000 રૂપિયા આપી રહી છે એવો સંદેશ ફેલાઈ રહ્યો છે. આ ખોટું છે.",
           "આવતીકાલથી બધા રેશન કાર્ડ રદ થશે એવો મેસેજ વાયરલ થયો છે, પરંતુ સરકારે આવી કોઈ જાહેરાત કરી નથી.",
           "પીએમ કિસાન યોજનામાં ખેડૂતોને વર્ષે 6000 રૂપિયા મળે છે એ વાત સાચી છે."],
    "pa": ["ਸਰਕਾਰ ਹਰ ਔਰਤ ਨੂੰ 1000 ਰੁਪਏ ਦੇ ਰਹੀ ਹੈ ਇਹ ਸੁਨੇਹਾ ਫੈਲ ਰਿਹਾ ਹੈ। ਇਹ ਝੂਠ ਹੈ।",
           "ਕੱਲ੍ਹ ਤੋਂ ਸਾਰੇ ਰਾਸ਼ਨ ਕਾਰਡ ਬੰਦ ਹੋ ਜਾਣਗੇ, ਇਹ ਖ਼ਬਰ ਗਲਤ ਹੈ ਅਤੇ ਸਰਕਾਰ ਨੇ ਅਜਿਹਾ ਕੁਝ ਨਹੀਂ ਕਿਹਾ।",
           "ਪੀਐਮ ਕਿਸਾਨ ਯੋਜਨਾ ਵਿੱਚ ਕਿਸਾਨਾਂ ਨੂੰ ਸਾਲ ਵਿੱਚ 6000 ਰੁਪਏ ਮਿਲਦੇ ਹਨ।"],
    "or": ["ସରକାର ପ୍ରତ୍ୟେକ ମହିଳାଙ୍କୁ ୧୦୦୦ ଟଙ୍କା ଦେଉଛନ୍ତି ବୋଲି ଏକ ବାର୍ତ୍ତା ବୁଲୁଛି। ଏହା ମିଛ।",
           "କାଲିଠାରୁ ସମସ୍ତ ରେସନ କାର୍ଡ ବନ୍ଦ ହେବ ବୋଲି ଖବର ବ୍ୟାପିଛି, ଏହା ଗୁଜବ ମାତ୍ର।",
           "ପିଏମ କିସାନ ଯୋଜନାରେ ଚାଷୀମାନଙ୍କୁ ବର୍ଷକୁ ୬୦୦୦ ଟଙ୍କା ମିଳେ।"],
    "kn": ["ಸರ್ಕಾರ ಪ್ರತಿ ಮಹಿಳೆಗೆ 1000 ರೂಪಾಯಿ ನೀಡುತ್ತಿದೆ ಎಂಬ ಸಂದೇಶ ಹರಡುತ್ತಿದೆ. ಇದು ಸುಳ್ಳು.",
           "ನಾಳೆಯಿಂದ ಎಲ್ಲಾ ಪಡಿತರ ಚೀಟಿಗಳು ರದ್ದಾಗುತ್ತವೆ ಎಂಬ ಸುದ್ದಿ ಸುಳ್ಳು, ಇದನ್ನು ಹಂಚಿಕೊಳ್ಳಬೇಡಿ.",
           "ಪಿಎಂ ಕಿಸಾನ್ ಯೋಜನೆಯಲ್ಲಿ ರೈತರಿಗೆ ವರ್ಷಕ್ಕೆ 6000 ರೂಪಾಯಿ ಸಿಗುತ್ತದೆ."],
    "ml": ["സർക്കാർ ഓരോ സ്ത്രീക്കും 1000 രൂപ നൽകുന്നു എന്ന സന്ദേശം പ്രചരിക്കുന്നു. ഇത് തെറ്റാണ്.",
           "നാളെ മുതൽ എല്ലാ റേഷൻ കാർഡുകളും റദ്ദാക്കും എന്ന വാർത്ത വ്യാജമാണ്, ദയവായി പങ്കിടരുത്.",
           "പിഎം കിസാൻ പദ്ധതിയിൽ കർഷകർക്ക് വർഷത്തിൽ 6000 രൂപ ലഭിക്കും."],
    "ur": ["حکومت ہر عورت کو 1000 روپے دے رہی ہے یہ پیغام پھیل رہا ہے۔ یہ جھوٹ ہے۔",
           "کل سے تمام راشن کارڈ بند ہو جائیں گے یہ خبر غلط ہے اور حکومت نے ایسا کوئی اعلان نہیں کیا۔",
           "پی ایم کسان اسکیم میں کسانوں کو سال میں 6000 روپے ملتے ہیں۔"],
}
HINDI = [  # these stay hi, including the ones that share words with Marathi, Nepali and Konkani
    "सरकार हर महिला को 5000 रुपये दे रही है। यह खबर सच है और जल्दी शेयर करें।",
    "कल से सभी राशन कार्ड बंद हो जाएंगे, यह खबर झूठ है और सरकार ने ऐसा कुछ नहीं कहा।",
    "पीएम किसान योजना में किसानों को साल में 6000 रुपये मिलते हैं, यह बात सही है।",
    "सरकार हर महिला को पैसे देगी, यह खबर नहीं आहे सही है और सबको भेजें।",      # one Marathi-looking word (आहे): still Hindi
    "यह संदेश खोटा सिक्का है और कृपया इसे सभी ग्रुप में न भेजें, यह खबर नहीं सच है।",  # one Marathi-looking word (खोटा)
    "भारत सरकार ने कहा है कि यह योजना सबको मिलेगी और इसके लिए कोई शुल्क नहीं है।",
]


@pytest.mark.parametrize("code", list(FORWARDS))
def test_every_new_language_is_detected_from_realistic_forwards(code):
    assert len(FORWARDS[code]) >= 3
    for text in FORWARDS[code]:
        assert L.detect_language(text) == code, text


@pytest.mark.parametrize("text", HINDI)
def test_hindi_stays_hindi(text):
    assert L.detect_language(text) == "hi"


def test_devanagari_defaults_to_hindi_when_unsure():
    assert L.detect_language("सरकार योजना घोषणा नई सूचना जानकारी") == "hi"        # no markers at all
    assert L.detect_language("यह योजना सबके लिए है और आहे") == "hi"                  # one Marathi marker is below the minimum
    # a Marathi text with only one marker word is not enough to leave Hindi (documented: the person can switch the reply language)
    assert L.detect_language("सरकार योजना घोषणा नई सूचना आहे") == "hi"


def test_marathi_konkani_nepali_need_a_clear_majority_over_hindi():
    mr = "ही बातमी खोटी आहे आणि कृपया शेअर करा."
    assert L.detect_language(mr) == "mr"
    # the same Marathi message with enough Hindi function words around it is Hindi again
    assert L.detect_language(mr + " यह खबर है और सरकार को भी नहीं पता, इस में से कोई भी नहीं।") == "hi"


def test_assamese_letters_decide_between_assamese_and_bengali():
    bn = "সরকার প্রতিটি মহিলাকে টাকা দিচ্ছে বলে একটি বার্তা ছড়াচ্ছে"
    assert L.detect_language(bn) == "bn"
    assert L.detect_language(bn + " ৰ") == "as" and L.detect_language(bn.replace("প্রতিটি", "প্ৰতিটি")) == "as"     # ৰ (U+09F0)
    assert L.detect_language(bn + " ৱ") == "as"                                                                      # ৱ (U+09F1)
    # Assamese without those letters, from its function words
    assert L.detect_language("সকলো মানুহে জানিব লাগে যে এই খবৰ নহয়, হৈছে মিছা বাৰ্তা") == "as"
    # one Assamese function word in a Bengali sentence stays Bengali
    assert L.detect_language("সরকার সকলো মহিলাকে টাকা দিচ্ছে বলে একটি বার্তা ছড়াচ্ছে") == "bn"


def test_meitei_mayek_is_manipuri_and_bengali_script_manipuri_is_bengali():
    assert L.detect_language(FORWARDS["mni"][0]) == "mni"
    # Manipuri written in the Bengali script cannot be told from Bengali: documented limit, detected as bn
    assert L.detect_language("সরকারে নুপী খুদিংমক্তা তাকা পীরি হায়না ৱাফম অসি") != "mni"


def test_mixed_script_messages_go_to_the_script_with_most_letters():
    bn = FORWARDS["bn"][0]
    assert L.detect_language(bn + " यह खबर है") == "bn"                                   # Bengali outweighs a Hindi tail
    assert L.detect_language("यह खबर है " + FORWARDS["ta"][0]) == "ta"
    assert L.detect_language("WhatsApp group link: " + FORWARDS["ta"][0] + " click here please") == "ta"
    assert L.detect_language(FORWARDS["ur"][0] + " PM Kisan scheme") == "ur"
    assert L.detect_language("PM Kisan योजना ₹6000 सबको मिलेगी, जल्दी शेयर करें") == "hi"      # English words inside Hindi, as before


def test_latin_text_detection_is_unchanged():
    assert L.detect_language("Government will give free laptops to all students") == "en"
    assert L.detect_language("sarkar sabko free paisa degi yeh yojana kal band ho jayegi jaldi bhejo") == "hi"     # Hinglish
    assert L.detect_language("Central sarkaru employees retirement age ni 50 years ki taggistundi ani message vachindi") == "tl"
    assert L.detect_language("") == "en" and L.detect_language("🙏🙏 1234 !!!") == "en"
    assert L.detect_language("ప్రభుత్వం ప్రతి మహిళకు 5000 రూపాయలు ఇస్తుంది") == "te"
    assert L.detect_language("जय हो") == "en"            # five letters or fewer in an Indian script: too little to decide (as before)


def test_digits_and_punctuation_are_not_counted_as_letters():
    # lots of Bengali digits and dandas, but only a Latin sentence: still English
    assert L.detect_language("Government will give Rs ১২৩৪৫৬৭৮৯০ ।।।।।।।। to every woman") == "en"


# ---------------------------------------------------------------------------------------------------------------- the language table
def test_language_table_is_consistent():
    assert L.SUPPORTED[0] == "en" and len(set(L.SUPPORTED)) == len(L.SUPPORTED)
    assert set(L.NAMES) == set(L.NATIVE) == set(L.BCP47) == set(L.SUPPORTED)
    assert L.SUPPORTED == ("en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as", "kok", "ne", "mni", "tl")
    assert L.RTL == {"ur"}
    assert L.BCP47["tl"] == "te-IN" and L.BCP47["bn"] == "bn-IN" and L.BCP47["ur"] == "ur-IN" and L.BCP47["mni"] == "mni-IN"
    assert all(re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", v) for v in L.BCP47.values())
    assert L.INDIAN_LANGS == tuple(c for c in L.SUPPORTED if c not in ("en", "tl")) and len(L.INDIAN_LANGS) == 15
    assert L.html_lang("tl") == "te-Latn" and L.html_lang("ur") == "ur" and L.html_lang("zz") == "en"


# ---------------------------------------------------------------------------------------------------------------- numbers and tokens
DIGITS = {"deva": "२०००", "bn": "২০০০", "pa": "੨੦੦੦", "gu": "૨૦૦૦", "or": "୨୦୦୦", "ta": "௨௦௦௦", "te": "౨౦౦౦", "kn": "೨೦೦೦",
          "ml": "൨൦൦൦", "ur_arabic_indic": "٢٠٠٠", "ur_extended": "۲۰۰۰", "mni": "꯲꯰꯰꯰"}


@pytest.mark.parametrize("script", list(DIGITS))
def test_native_digits_equal_ascii_digits(script):
    d = DIGITS[script]
    assert stance.numbers(f"Rs {d}") == stance.numbers("Rs 2000") == {"2000"}
    assert "2000" in stance.tokens(f"योजना {d} रुपये")


def test_thousands_separators_with_native_digits():
    assert stance.numbers("१,२०,५७९") == stance.numbers("1,20,579") == {"120579"}
    assert stance.numbers("১৯,৮০০") == {"19800"}
    assert stance.numbers("٣٫٥") == {"3.5"}                     # Arabic decimal separator


def test_tokens_tokenise_every_new_script_with_whole_words():
    for code, texts in FORWARDS.items():
        toks = stance.tokens(texts[0])
        assert len(toks) >= 4, code
        # whole words survive: no token is a lone vowel sign or fragment of the first word
        first = re.split(r"[\s,।]+", texts[0])[0]
        assert first.lower() in toks or any(t.startswith(first.lower()[:3]) for t in toks), code
    assert "টাকা" in stance.tokens("প্রতি মহিলাকে ১০০০ টাকা") and "ரூபாய்" in stance.tokens("1000 ரூபாய் வழங்கப்படும்")
    assert "جھوٹ" in stance.tokens("یہ جھوٹ ہے")
    assert "ꯁꯔꯀꯥꯔ" in stance.tokens("ꯁꯔꯀꯥꯔ ꯄꯤꯔꯤ")


def test_bengali_claim_and_page_overlap_with_native_digits():
    claim, page = "সরকার প্রতিটি মহিলাকে ২০০০ টাকা দিচ্ছে", "সরকার প্রতিটি মহিলাকে 2000 টাকা দিচ্ছে বলে প্রচার ভুয়া"
    assert stance.overlap(claim, page) == 1.0 and stance.numbers(claim) <= stance.numbers(page)


def test_debunk_negation_and_denial_words_are_whole_word_matches():
    for text in ("এটি ভুয়া খবর", "இது பொய்", "यह दावा खोटा आहे", "یہ جھوٹ ہے", "ಇದು ಸುಳ್ಳು", "ഇത് വ്യാജ വാർത്ത", "ਇਹ ਝੂਠ ਹੈ",
                 "ଏହା ମିଛ", "આ ખોટું છે", "ये खबर नक्कली है"):
        assert stance._STRICT_DEBUNK.search(text) and stance._DENIAL.search(text), text
    for text in ("এটি সত্য নয়", "இது உண்மை அல்ல", "यह सच नाही", "یہ سچ نہیں", "ಇದು ನಿಜ ಅಲ್ಲ", "ഇത് ശരിയല്ല, അല്ല", "ਇਹ ਸੱਚ ਨਹੀਂ",
                 "ଏହା ସତ ନୁହେଁ", "આ સાચું નથી", "यो सत्य होइन", "ꯃꯁꯤ ꯅꯠꯇꯦ"):
        assert stance._NEGATION.search(text), text
    # short negation words must not fire inside ordinary words (Bengali "যোজনা" = scheme ends in না)
    assert not stance._NEGATION.search("প্রধানমন্ত্রী কিষাণ যোজনা ঘোষণা করেছেন")
    assert not stance._STRICT_DEBUNK.search("প্রধানমন্ত্রী কিষাণ যোজনা ঘোষণা করেছেন")
    # the checks themselves are unchanged for English
    assert stance._STRICT_DEBUNK.search("PIB busts fake claim") and not stance._STRICT_DEBUNK.search("Cabinet approves scheme")


# ---------------------------------------------------------------------------------------------------------------- splitting
def test_sentences_split_on_danda_double_danda_urdu_and_meitei_stops():
    cases = {
        "hi-danda": "सरकार हर महिला को 5000 रुपये देगी। यह योजना कल बंद हो जाएगी। इसे सबको भेजो।",
        "bn-danda": "সরকার প্রতিটি মহিলাকে ১০০০ টাকা দেবে। এই প্রকল্প কাল বন্ধ হয়ে যাবে। এটি সবাইকে জানান।",
        "double-danda": "सरकार हर महिला को 5000 रुपये देगी ॥ यह योजना कल बंद हो जाएगी ॥ ठीक है सब लोग",
        "ur": "حکومت ہر عورت کو 1000 روپے دے رہی ہے۔ یہ اسکیم کل بند ہو جائے گی؟ ہر کوئی یہ پیغام آگے بھیجے",
        "mni": "ꯁꯔꯀꯥꯔꯅꯥ ꯅꯨꯄꯤ ꯈꯨꯗꯤꯡꯃꯛꯇꯥ ꯇꯥꯀꯥ ꯄꯤꯔꯤ꯫ ꯃꯁꯤ ꯍꯌꯥꯎꯅꯥ ꯌꯧꯍꯜꯂꯤ ꯍꯥꯌꯅꯥ ꯋꯥꯐꯃ꯫",
    }
    for name, text in cases.items():
        parts = [c.text for c in extract_claims(text)]
        assert len(parts) >= 2, (name, parts)
        assert all(not re.search("[।॥۔؟꯫]\\s\\S", p) for p in parts), (name, parts)   # no sentence swallowed the next one


def test_rupee_abbreviation_dots_do_not_split_in_the_new_scripts():
    for abbr, text in (("ரூ.", "தமிழ்நாடு அரசு ரூ. 1000 வழங்குகிறது என்று ஒரு செய்தி பரவுகிறது"),
                       ("રૂ.", "સરકાર દરેક મહિલાને રૂ. 1000 આપી રહી છે એવો સંદેશ ફેલાઈ રહ્યો છે"),
                       ("ರೂ.", "ಸರ್ಕಾರ ಪ್ರತಿ ಮಹಿಳೆಗೆ ರೂ. 1000 ನೀಡುತ್ತಿದೆ ಎಂಬ ಸಂದೇಶ ಹರಡುತ್ತಿದೆ"),
                       ("രൂ.", "സർക്കാർ ഓരോ സ്ത്രീക്കും രൂ. 1000 നൽകുന്നു എന്ന സന്ദേശം പ്രചരിക്കുന്നു"),
                       ("రూ.", "ప్రభుత్వం ప్రతి మహిళకు రూ. 1000 ఇస్తుంది అనే సందేశం వ్యాపిస్తోంది"),
                       ("रु.", "सरकार हर महिला को रु. 1000 दे रही है ऐसा संदेश फैल रहा है")):
        claims = extract_claims(text)
        assert len(claims) == 1 and abbr in claims[0].text, abbr
    assert extract_claims("Government gives Rs. 1000 to every woman in the country")[0].text.count("Rs.") == 1


def test_call_to_action_lines_are_dropped_in_the_new_scripts():
    for text in ("এই বার্তা সবাইকে শেয়ার করুন দয়া করে", "இந்த செய்தியை அனைவருக்கும் ஷேர் செய்யுங்கள் உடனே", "یہ پیغام سب کو شیئر کریں جلدی"):
        assert extract_claims(text) == [], text


# ---------------------------------------------------------------------------------------------------------------- i18n tables
TABLES = {"LABEL": I18N.LABEL, "WHY": I18N.WHY, "SOURCE_LABEL": I18N.SOURCE_LABEL, "FC_NOTE": I18N.FC_NOTE,
          "NOCLAIM": I18N.NOCLAIM, "NOCLAIM_LABEL": I18N.NOCLAIM_LABEL}


def test_every_per_language_table_has_every_supported_language_or_the_documented_english_fallback():
    for name, table in TABLES.items():
        missing = set(L.SUPPORTED) - set(table)
        assert missing <= I18N.ENGLISH_ONLY, (name, missing)
        assert set(table) <= set(L.SUPPORTED), (name, set(table) - set(L.SUPPORTED))
    assert I18N.ENGLISH_ONLY == {"mni"}


def test_translated_tables_keep_structure_placeholders_and_are_not_english():
    for code in NEW:
        if code in I18N.ENGLISH_ONLY:
            continue
        assert set(I18N.LABEL[code]) == set(I18N.LABEL["en"]) and set(I18N.WHY[code]) == set(I18N.WHY["en"]), code
        assert len(set(I18N.LABEL[code].values())) == 4, code                       # four distinct verdict words
        for v, why in I18N.WHY[code].items():
            assert why.count("{src}") == I18N.WHY["en"][v].count("{src}"), (code, v)
            assert why != I18N.WHY["en"][v]
            assert not re.search("[A-Za-z]", why.replace("{src}", "")), (code, v)    # no stray English words
        for table in (I18N.LABEL[code].values(), [I18N.SOURCE_LABEL[code], I18N.FC_NOTE[code], I18N.NOCLAIM[code], I18N.NOCLAIM_LABEL[code]]):
            assert all(isinstance(s, str) and s and not re.search("[A-Za-z]", s) for s in table), code
        assert I18N.NOCLAIM[code] != I18N.NOCLAIM["en"]


def test_i18n_source_marks_every_new_table_as_not_native_reviewed():
    src = open(I18N.__file__, encoding="utf-8").read()
    for name in TABLES:
        assert re.search(name + r"\.update\(\{\s*# NOT NATIVE-REVIEWED", src), name


def test_tr_and_text_lang_never_raise_and_fall_back_to_english():
    assert I18N.tr(I18N.LABEL, "mni") == I18N.LABEL["en"] and I18N.tr(I18N.WHY, "zz") == I18N.WHY["en"]
    assert I18N.tr(I18N.NOCLAIM, "ta") == I18N.NOCLAIM["ta"]
    assert I18N.text_lang("mni") == "en" and I18N.text_lang("zz") == "en" and I18N.text_lang("bn") == "bn" and I18N.text_lang("tl") == "tl"
    cite = [{"source": "PIB", "url": "https://pib.gov.in/x", "tier": TIER_PIB, "date_accessed": "2026-11-12", "fetched_at": TS}]
    for v in ("TRUE", "FALSE", "MISLEADING", "UNVERIFIED"):
        assert render_card(v, "mni", cite) == render_card(v, "en", cite) == render_card(v, "zz", cite)
    # a language that is in SUPPORTED but missing from one table must not crash the card
    saved = I18N.FC_NOTE.pop("ta")
    try:
        c2 = [{**cite[0], "tier": "factchecker"}]
        assert "Fact-checker (not official)" in render_card("UNVERIFIED", "ta", c2)
    finally:
        I18N.FC_NOTE["ta"] = saved


@pytest.mark.parametrize("code", [c for c in L.SUPPORTED if c not in I18N.ENGLISH_ONLY])
@pytest.mark.parametrize("verdict", ["TRUE", "FALSE", "MISLEADING", "UNVERIFIED"])
def test_card_leads_with_the_verdict_word_in_every_language(code, verdict):
    cite = [{"source": "PIB", "url": "https://pib.gov.in/x", "tier": TIER_PIB, "date_accessed": "2026-11-12", "fetched_at": TS}]
    card = render_card(verdict, code, cite)
    first = card.splitlines()[0]
    assert I18N.LABEL[code][verdict] in first and I18N.EMOJI[verdict] in first
    assert "https://pib.gov.in/x" in card
    if verdict != "UNVERIFIED":
        assert "PIB" in card


# ---------------------------------------------------------------------------------------------------------------- rendering
def _result(code, card_en=True):
    cite = [{"source": "PIB (Press Information Bureau)", "url": "https://pib.gov.in/x", "tier": TIER_PIB, "date_accessed": "2026-11-12", "fetched_at": TS}]
    claim = {"text": "Retirement age is cut", "domain": "scheme", "english": "Retirement age is cut"}
    res = {"verdict": "FALSE", "language": code, "card": render_card("FALSE", code, cite), "checked_at": "2026-11-12T10:00:00+00:00", "trace": {},
           "claims": [{"claim": claim, "verdict": "FALSE", "citations": [{**cite[0], "date_accessed": "2026-11-12"}], "reason_code": "pib_debunk", "english": "x"}]}
    if card_en and code != "en":
        res["card_en"] = render_card("FALSE", "en", cite)
    return res


@pytest.mark.parametrize("code", L.SUPPORTED)
def test_result_renders_with_the_right_lang_and_dir_attribute(code):
    block = SITE.result_block(_result(code), chosen=True)
    m = re.search(r'<div class="bubble"([^>]*)><span id="cardtext">', block)
    assert m, code
    attrs = m.group(1)
    real = I18N.text_lang(code)
    assert f'lang="{L.html_lang(real)}"' in attrs
    assert ('dir="rtl"' in attrs) == (code == "ur")
    assert block.count('dir="rtl"') == (1 if code == "ur" else 0)             # only the card: the English meaning below stays left-to-right
    if code != "en":
        assert 'id="cardtext_en"' in block
    assert 'id="copy"' in block and "wa.me/?text=" in block                      # Copy and Share are still there
    if code == "mni":
        assert 'lang="en"' in attrs                                              # the card text is English until a native speaker adds Meitei


def test_urdu_share_link_and_copy_text_carry_the_whole_card():
    res = _result("ur")
    block = SITE.result_block(res, chosen=True)
    link = re.search(r'href="(https://wa\.me/\?text=[^"]+)"', block).group(1)
    # CHANGED (SHARE package): the WhatsApp message is now the whole card followed by the claim, evidence link and an invitation
    assert _up.unquote(link.split("text=", 1)[1]).replace("&amp;", "&").startswith(res["card"])
    assert "جھوٹ" in res["card"] and "innerText" in SITE.JS


def test_no_claims_card_gets_lang_and_dir_too():
    out = check_forward("🙏 " + "ꯃꯁꯤ", [], None, reply_lang="ur")
    assert out["no_claims"] and out["language"] == "ur" and out["card"].startswith(I18N.NOCLAIM_LABEL["ur"])
    block = SITE.result_block(out, chosen=True)
    assert 'lang="ur" dir="rtl"' in block
    assert check_forward("Good morning 🙏", [], None, reply_lang="mni")["card"].startswith(I18N.NOCLAIM_LABEL["en"])


def test_selector_lists_every_language_once_in_the_right_order():
    home = SITE.home().decode()
    sel = re.search(r'<select id="lang" name="lang">(.*?)</select>', home, re.S).group(1)
    values = re.findall(r'<option value="([^"]+)"', sel)
    assert values == list(SITE.REPLY_LANGS) and values[0] == "auto" and len(values) == len(set(values)) == len(L.SUPPORTED) + 1
    assert tuple(values[1:]) == L.SUPPORTED
    assert values[:14] == ["auto", "en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as"] and values[-1] == "tl"
    for code in L.INDIAN_LANGS:
        assert f"{L.NATIVE[code]} · {L.NAMES[code]}" in sel
    assert '<label for="lang"' in home and ">Reply in<" in home
    assert 'value="ta" selected' in SITE.home(reply="ta").decode() and SITE.home(reply="auto").decode().count(" selected") >= 1


def test_hero_meta_and_languages_section_counts_come_from_supported():
    n = len([c for c in L.SUPPORTED if c not in ("en", "tl")])
    assert n == SITE.N_INDIAN == len(L.INDIAN_LANGS)
    home = SITE.home().decode()
    assert home.count(f"English and {n} Indian languages") >= 4          # meta description, og description, hero line, section text
    assert re.search(r'<meta name="description" content="[^"]*English and %d Indian languages' % n, home)
    assert 'href="#languages"' in home and 'id="languages"' in home
    section = re.search(r'<section id="languages">.*?</section>', home, re.S).group(0)
    for code in L.SUPPORTED:
        if code != "en":
            assert section.count(f"<b>{L.NATIVE[code]}</b>") == 1, code


def test_fonts_cover_every_script_and_stay_lightweight():
    for fam in ("Bengali", "Gurmukhi", "Gujarati", "Oriya", "Tamil", "Kannada", "Malayalam", "Meetei+Mayek"):
        assert f"family=Noto+Sans+{fam}:wght@400;600" in SITE.FONTS
    assert "Noto+Nastaliq+Urdu" in SITE.FONTS or "Noto+Sans+Arabic" in SITE.FONTS
    assert SITE.FONTS.endswith("display=swap") and SITE.FONTS.count("display=swap") == 1
    assert "wght@700" not in SITE.FONTS.split("Noto+Sans+Devanagari")[1]
    page = SITE.home().decode()
    assert "'Noto Sans Bengali'" in page and "'Noto Sans Meetei Mayek'" in page
    canvas = page[page.index("sachBindCard"):]
    assert "Noto Sans Malayalam" in canvas and "Noto Sans Arabic" in canvas and "setTimeout(r,2500)" in canvas      # same 2.5 s timeout and fallback


def test_page_still_has_no_extra_script_tags():
    assert SITE.home().decode().count("<script>") == 4


# ---------------------------------------------------------------------------------------------------------------- voice
def test_voice_maps_cover_every_language_and_the_picker_lists_the_supported_ones():
    assert set(voice.CARD_BCP47) == set(L.SUPPORTED) and voice.CARD_BCP47["bn"] == "bn-IN" and voice.CARD_BCP47["tl"] == "en-IN"
    tags = [t for t, _ in voice.SPEAK_LANGS]
    assert tags == ["en-IN", "hi-IN", "bn-IN", "mr-IN", "te-IN", "ta-IN", "gu-IN", "ur-IN", "kn-IN", "ml-IN", "pa-IN"]
    assert "or-IN" not in tags and "as-IN" not in tags                                # unconfirmed: left out of the picker ...
    assert voice.CARD_BCP47["or"] == "or-IN" and voice.CARD_BCP47["as"] == "as-IN"     # ... but read-aloud still attempts them
    assert voice.REC_DEFAULT["tl"] == "te-IN" and voice.REC_DEFAULT["ur"] == "ur-IN"
    js = voice.VOICE_JS
    assert '"kok": "kok-IN"' in js and '"or"' in js and "voiceMsg" in js


def test_listen_buttons_use_the_real_text_language():
    assert 'data-lang="ur"' in voice.listen_buttons("ur", True) and 'data-lang="en"' in voice.listen_buttons("mni", True)
    assert voice.listen_buttons("zz", False).count('data-listen="card"') == 1
    assert voice.STRINGS["en"]["voice_missing"].count("{lang}") == 1 and "English" in voice.STRINGS["en"]["voice_missing"]


# ---------------------------------------------------------------------------------------------------------------- other surfaces
def test_signs_box_falls_back_to_english_with_the_right_lang_attribute():
    sign = {"id": "asks_secret", "severity": "high", "title": "Asks for a secret code", "why": "x", "evidence": "share your OTP"}
    for code in L.SUPPORTED:
        h = scamsigns.signs_html([sign], code)
        assert "Warning signs in this message" in h or code in ("hi", "te")
        assert f'lang="{code}"' in h if code in ("en", "hi", "te") else 'lang="en"' in h


def test_json_api_accepts_each_language_code(server):
    class Rec:
        def search(self, q):
            return [Evidence("PIB", "https://pib.gov.in/x", TIER_PIB, TS, "Fake: Government will give Rs 1000 to every woman", "")]

    class Llm:
        def translate(self, t): return "Government will give Rs 1000 to every woman"
        def stance(self, claim, title, text, tier=""): return "contradicts"
    W.Handler.retrievers, W.Handler.llm = [Rec()], Llm()
    try:
        for code in L.SUPPORTED:
            W._hits.clear()
            status, body = _post(server, "Government will give Rs 1000 to every woman in the country.", f"/?format=json&lang={code}")
            d = json.loads(body)
            assert status == 200 and d["language"] == code and d["verdict"] == "FALSE", code
            assert d["card"].splitlines()[0].startswith(I18N.EMOJI["FALSE"]) and I18N.tr(I18N.LABEL, code)["FALSE"] in d["card"]
        W._hits.clear()
        status, body = _post(server, "Government will give Rs 1000 to every woman in the country.", "/?format=json&lang=klingon")
        assert status == 200 and json.loads(body)["language"] == "en"                     # unknown -> auto, as before
        W._hits.clear()
        status, page = _post(server, "x y z w v", raw=_up.urlencode({"text": "Government will give Rs 1000 to every woman in the country.", "lang": "ur"}).encode())
        assert status == 200 and 'lang="ur" dir="rtl"' in page and 'value="ur" selected' in page
        W._hits.clear()
        status, page = _post(server, "x", raw=_up.urlencode({"text": "Government will give Rs 1000 to every woman in the country.", "lang": "xx"}).encode())
        assert status == 200 and "(matched to the forward)" in page
    finally:
        W.Handler.llm = None


def test_api_docs_on_the_home_page_list_every_code():
    home = SITE.home().decode()
    assert ", ".join(L.SUPPORTED) in home


class _Sent(list):
    def __call__(self, method, payload):
        self.append((method, payload)); return True

    def texts(self):
        return [p["text"] for m, p in self if m == "sendMessage"]


@pytest.fixture
def tg(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"[:35])
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cr3t_" + "x" * 20)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    T._hits.clear(); store.reset()
    calls = []
    monkeypatch.setattr(T, "check_forward", lambda text, r, llm, reply_lang=None, **k: calls.append(reply_lang) or {"verdict": "FALSE", "card": "x", "language": "en", "claims": []})
    return calls


def _tg_msg(text, uid):
    return {"update_id": uid, "message": {"message_id": 7, "chat": {"id": 1, "type": "private"}, "from": {"id": 5, "is_bot": False}, "text": text}}


def test_telegram_lang_command_accepts_every_code_and_lists_them(tg):
    for i, code in enumerate(L.SUPPORTED):
        sent = _Sent()
        T.handle_update(_tg_msg(f"/lang {code}", 100 + i), [], None, send=sent)
        assert L.NAMES[code] in sent.texts()[0], code
        assert store.get_store().get("tg:lang:1") == code
        T._hits.clear()                                  # the bot rate-limits checks per chat
        T.handle_update(_tg_msg("some claim text to check", 300 + i), [], None, send=_Sent())
        assert tg[-1] == code
    sent = _Sent()
    T.handle_update(_tg_msg("/lang klingon", 999), [], None, send=sent)
    for code in L.SUPPORTED:
        assert code in sent.texts()[0]
    assert "/lang en" in sent.texts()[0]
    sent = _Sent()
    T.handle_update(_tg_msg("/help", 1000), [], None, send=sent)
    assert all(code in sent.texts()[0] for code in L.SUPPORTED) and len(sent.texts()[0]) < T.TG_LIMIT


def test_ledger_and_impact_counters_cover_every_language():
    from sach import impact, ledger
    assert all("lang:" + c in ledger.COUNTERS for c in L.SUPPORTED)
    d = impact.impact_data()
    assert set(L.SUPPORTED) <= set(d["languages"])


# ---------------------------------------------------------------------------------------------------------------- end to end
class _Pib:
    def __init__(self): self.q = None
    def search(self, q):
        self.q = q
        return [Evidence("PIB (Press Information Bureau)", "https://pib.gov.in/PressReleasePage.aspx?PRID=1", TIER_PIB, TS,
                         "Fake: Government will give Rs 1000 to every woman", "")]


class _Llm:
    def translate(self, t): return "Government will give Rs 1000 to every woman"
    def stance(self, claim, title, text, tier=""): return "contradicts" if "1000" in claim else "none"


E2E = {  # NOT NATIVE-REVIEWED
    "bn": "সরকার প্রতিটি মহিলাকে ১০০০ টাকা দিচ্ছে বলে একটি বার্তা ছড়াচ্ছে, সবাইকে জানান।",
    "ta": "அரசு ஒவ்வொரு பெண்ணுக்கும் ரூ.1000 வழங்குகிறது என்ற செய்தி பரவி வருகிறது.",
    "ur": "حکومت ہر عورت کو 1000 روپے دے رہی ہے یہ پیغام پھیل رہا ہے۔",
}


@pytest.mark.parametrize("code", list(E2E))
def test_known_debunk_in_bengali_tamil_urdu_gives_false_with_card_in_that_language(code):
    pib = _Pib()
    res = check_forward(E2E[code], [pib], _Llm())
    assert res["input_language"] == code and res["language"] == code and res["verdict"] == "FALSE"
    assert pib.q == "Government will give Rs 1000 to every woman"                  # searched in English via the translation
    first = res["card"].splitlines()[0]
    assert I18N.LABEL[code]["FALSE"] in first and "FALSE" not in res["card"]
    assert res["card_en"].splitlines()[0].endswith("FALSE") and "https://pib.gov.in/" in res["card_en"]      # the English meaning is present
    assert res["claims"][0]["english"] == "Government will give Rs 1000 to every woman"
    assert "PIB" in res["card"] and "https://pib.gov.in/PressReleasePage.aspx?PRID=1" in res["card"]
    block = SITE.result_block(dict(res, warning_signs=[]), chosen=False)
    assert f'lang="{code}"' in block and ('dir="rtl"' in block) == (code == "ur") and 'id="english"' in block
    # the same forward with the reply language forced to English gives the English card
    forced = check_forward(E2E[code], [_Pib()], _Llm(), reply_lang="en")
    assert forced["input_language"] == code and forced["language"] == "en" and forced["verdict"] == "FALSE"
    assert forced["card"].splitlines()[0].endswith("FALSE") and "card_en" not in forced


def test_manipuri_forward_is_checked_and_answered_in_english_until_reviewed():
    pib = _Pib()
    res = check_forward("ꯁꯔꯀꯥꯔꯅꯥ ꯅꯨꯄꯤ ꯈꯨꯗꯤꯡꯃꯛꯇꯥ ꯇꯥꯀꯥ ꯄꯤꯔꯤ ꯍꯥꯌꯅꯥ ꯋꯥꯐꯃꯁꯤ ꯌꯧꯍꯜꯂꯤ ꯀꯃꯨꯟ ꯇꯥꯕꯅꯥ ꯌꯥꯎ꯫", [pib], _Llm())
    assert res["input_language"] == "mni" and res["verdict"] == "FALSE" and res["card"].splitlines()[0].endswith("FALSE")
    assert pib.q == "Government will give Rs 1000 to every woman"
    assert 'lang="en"' in SITE.result_block(res, chosen=False)


def test_forcing_any_reply_language_on_an_english_forward():
    for code in L.SUPPORTED:
        res = check_forward("Government will give Rs 1000 to every woman in the country.", [_Pib()], _Llm(), reply_lang=code, use_cache=False)
        assert res["language"] == code and res["input_language"] == "en" and res["verdict"] == "FALSE"
        assert I18N.tr(I18N.LABEL, code)["FALSE"] in res["card"]
        assert ("card_en" in res) == (code != "en")
