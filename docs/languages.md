# Languages

Sach reads a forward in English or in one of 15 Indian languages, checks it, and replies with a verdict card in the forward's language, or in a reply language the person picks ("Reply in"). The card always carries the English meaning beside it for a non-English reply.

**Status of the wording: not native-reviewed.** Every string for every language except English was written by an AI model. Hindi and Telugu predate this work and were also never reviewed. Treat all of it as a first draft until a native speaker has been through it (see [How to review](#how-to-review)).

## The languages

The single source of truth is `sach/lang.py` (`SUPPORTED`, `NAMES`, `NATIVE`, `BCP47`, `RTL`). Everything else imports it. The order below is the order of the "Reply in" selector: English, then Indian languages by number of first-language speakers, then the romanised option.

| Code | Language | Script | How it is detected | Known limit |
|---|---|---|---|---|
| `en` | English | Latin | no Indian-script letters, not Hinglish or Tinglish | |
| `hi` | Hindi | Devanagari | Devanagari, unless Marathi, Konkani or Nepali markers clearly win | the default for all Devanagari text; Hinglish (Hindi in Latin letters) is detected as `hi` |
| `bn` | Bengali | Bengali | Bengali script, unless Assamese letters or markers | Manipuri written in the Bengali script also lands here |
| `mr` | Marathi | Devanagari | Devanagari plus Marathi marker words | short messages with fewer than two markers stay `hi` |
| `te` | Telugu | Telugu | script | |
| `ta` | Tamil | Tamil | script | |
| `gu` | Gujarati | Gujarati | script | |
| `ur` | Urdu | Perso-Arabic, **right to left** | script (U+0600-06FF, U+0750-077F, U+FB50-FDFF, U+FE70-FEFF) | Sindhi, Kashmiri, Persian and Arabic text also lands here |
| `kn` | Kannada | Kannada | script | |
| `or` | Odia | Odia | script | |
| `ml` | Malayalam | Malayalam | script | |
| `pa` | Punjabi | Gurmukhi | script | Punjabi in the Shahmukhi (Perso-Arabic) script is detected as `ur` |
| `as` | Assamese | Bengali-Assamese | Bengali-script text with the Assamese-only letters ৰ (U+09F0) or ৱ (U+09F1), or two or more Assamese function words | Assamese with neither (rare) is detected as `bn` |
| `kok` | Konkani | Devanagari | Devanagari plus Konkani marker words | short messages stay `hi`; Konkani in Roman or Kannada script is not recognised as Konkani |
| `ne` | Nepali | Devanagari | Devanagari plus Nepali marker words | short messages stay `hi` |
| `mni` | Manipuri (Meitei) | Meitei Mayek | Meitei Mayek script only | Manipuri in the Bengali script cannot be told from Bengali, so it is detected as `bn` (it gets a Bengali reply card; the person can switch). **Cards are English for now, see below.** |
| `tl` | Tinglish | Latin (Telugu in English letters) | distinctive Telugu words in Latin letters | unchanged from before |

Languages not in the table (for example Maithili, Bhojpuri and other Devanagari-script languages count as Hindi; Santali in Ol Chiki, Dogri in Dogra, Bodo and Kashmiri in its own script are not detected) fall back to whatever script rule fits, usually `hi` or English. Anyone can still pick a reply language by hand.

### The detection rule

`detect_language(text)` in `sach/lang.py`:

1. Count letters (and the vowel signs that belong to them) per script. Digits, punctuation, spaces, URLs and emoji are ignored.
2. The Indian script with the most letters wins, provided it has **more than 5** letters. A message that mixes scripts therefore goes to the dominant one. A Hindi message with some English words is still Hindi. (As before this work, any message with more than five Indian-script letters is decided by its Indian script even if it contains a lot of Latin text; Latin only competes when there are five or fewer.)
3. **Devanagari** (`hi` / `mr` / `kok` / `ne`): each word of the text is looked up whole in four lists of very common function words (Hindi: है, हैं, नहीं, और, के, की, में, से, को …; Marathi: आहे, आहेत, नाही, आणि, मध्ये, साठी, करण्यात …; Konkani: आसा, आसात, आनी, हांव, तुमी, जाल्यार, खातीर …; Nepali: छ, छन्, गर्न, भएको, गरेको, सरकारले, र …), plus a few suffixes only one language uses (Marathi -च्या, -णार, -ण्यात; Nepali -हरू). Nukta and chandrabindu are normalised first. A regional language wins only if it has **at least 2 marker hits**, **at least `2 × (Hindi hits) + 1`**, and **more hits than each other regional language**. Otherwise the text is `hi`. So a Hindi sentence that happens to contain one Marathi-looking word stays Hindi, and so does any Devanagari text with no markers. A wrong Marathi, Konkani or Nepali guess only changes the reply language, and the person can switch it.
   Konkani's own "ना" is left out of its list on purpose: it is also an ordinary Hindi particle.
4. **Bengali script** (`bn` / `as`): `as` if the text contains ৰ or ৱ, or if it has at least two Assamese function words (and more than Bengali's equivalents). Otherwise `bn`.
5. **Latin** text is `en`, `tl` (Tinglish) or `hi` (Hinglish) by the same word lists as before.

All the thresholds are constants at the top of `sach/lang.py` and are pinned by `tests/test_languages.py`.

## Coverage

About 90% of Indians by first language. This follows the Census of India 2011, table C-16 ("Population by mother tongue"). The first-language shares that table gives for the largest scheduled languages: Hindi 43.6%, Bengali about 8.0%, Marathi about 6.9%, Telugu about 6.7%, Tamil about 5.9%, Gujarati about 4.5%, Urdu about 4.2%. Every other language Sach supports (Kannada, Odia, Malayalam, Punjabi, Assamese, Konkani, Nepali, Manipuri) is between roughly 0.1% and 4% each. We did not add the figures up to a precise total here; "about 90%" is the order of magnitude, and the figure depends on how the Hindi mother-tongue groupings are counted. First language is not the same as the language someone reads comfortably on WhatsApp, and many people read English or Hindi as well. Please check the census table before quoting a more exact number.

## What exists per language

| Surface | Where | Status |
|---|---|---|
| Verdict card (label, one-line why, source label, "fact-checker, not official" note) | `sach/i18n.py` `LABEL`, `WHY`, `SOURCE_LABEL`, `FC_NOTE` | translated for every language except Manipuri |
| "No claim found" card | `NOCLAIM`, `NOCLAIM_LABEL` | same |
| Reply-language selector, hero line, Languages section, FAQ, API docs | `sach/site.py` | English text; native language names |
| Fonts | `FONTS` in `sach/site.py` | Noto Sans for every script, Noto Nastaliq Urdu on screen (card text), Noto Sans Arabic in the downloadable image |
| Share image (Download image) | canvas code in `sach/site.py` | all scripts; right to left for Urdu |
| Voice: speak the forward / listen to the card | `sach/voice.py` | see below |
| Scam "warning signs" box | `sach/scamsigns.py` | English, Hindi, Telugu only. Every other language shows the English box (marked `lang="en"`). **Not translated yet.** |
| Voice and progress texts on the page | `sach/voice.py` `STRINGS` | English, Hindi, Telugu only; other languages show English. The "no voice installed" message works for every language name |
| Telegram bot | `sach/telegram_bot.py` | `/lang <code>` accepts every code; help text is English plus Hindi and Telugu |
| Words for fake / false / not (offline heuristics) | `sach/langwords.py` | every language except Manipuri, which has no debunk word listed (only negation) |
| Sentence splitting | `sach/extract.py` | splits on `.` `!` `?` `।` `॥` `۔` `؟` `꯫` |
| Digits | `sach/lang.py` `DIGITS` | 2000 equals ২০০০, २०००, ٢٠٠٠, ꯲꯰꯰꯰ and every other native digit set |

### Manipuri (Meitei): the card is English for now

Detection, translation, search and the verdict all work for Meitei Mayek forwards. The **card text** is English for now (`ENGLISH_ONLY` in `sach/i18n.py`) and is marked `lang="en"`. This is deliberate: verdict wording in Meitei Mayek cannot be authored reliably without a native speaker, and a wrong word on a fact-check card is worse than English. To switch it on, add `"mni"` rows to the six tables in `sach/i18n.py` and remove `"mni"` from `ENGLISH_ONLY`; the tests then check the rest.

### Voice

* **Speak in** (speech recognition) lists the languages browsers commonly support: English, Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Urdu, Kannada, Malayalam, Punjabi (`en-IN`, `hi-IN`, `bn-IN`, `mr-IN`, `te-IN`, `ta-IN`, `gu-IN`, `ur-IN`, `kn-IN`, `ml-IN`, `pa-IN`). Odia (`or-IN`) and Assamese (`as-IN`) are left out because support could not be confirmed. Konkani, Nepali and Manipuri are left out too. Tinglish pre-selects Telugu. **These tags were not verified on a device**; for Punjabi in particular, some Chrome builds expect a script-qualified tag, so check it.
* **Listen** (read aloud) attempts every language. If the phone has no voice for the card language, the button is disabled with a message that names the language and points to "Listen in English". For Odia, Assamese, Konkani, Nepali and Manipuri the button stays enabled (the phone may still do something with the language tag) and the message says Sach will try.

## How to review

You do not need to read code. Every file below marks AI-written wording with `NOT NATIVE-REVIEWED` and the tables are plain text.

1. **Verdict cards**: `sach/i18n.py`, the block after the "Indian languages added by the LANG work package" banner. Six tables: `LABEL` (the four verdict words, the most important), `WHY` (one line per verdict; `{src}` is replaced by the source name, for example "PIB"; keep it), `SOURCE_LABEL`, `FC_NOTE`, `NOCLAIM`, `NOCLAIM_LABEL`. Read them as a careful family-group message would: short, natural, not officialese. Check especially that FALSE, MISLEADING and UNVERIFIED cannot be confused with each other.
2. **Fake / false / not words**: `sach/langwords.py` (`DEBUNK`, `NEGATION`). Only common, unambiguous words belong there. Remove any word that is ambiguous in your language; add ones that are missing.
3. **Devanagari markers** (Marathi, Konkani, Nepali, Hindi): `sach/lang.py` (`_MR`, `_KOK`, `_NE`, `_HI`). Words must be common function words that only that language uses.
4. **Assamese words**: `sach/lang.py` (`_AS_WORDS`).
5. **Call-to-action words** ("share", "forward", "click", "link"): the second half of `_BOILER` in `sach/extract.py`.
6. **Language names** in their own script: `NATIVE` in `sach/lang.py`.
7. **Page texts** that are still English only: `sach/voice.py` `STRINGS`, `sach/scamsigns.py` `TEXT` and `UI`.

To contribute: edit the strings, run `python -m pytest -q tests/test_languages.py`, and open a pull request that says who reviewed which language. Once a language has been reviewed by a native speaker, change its comment from `NOT NATIVE-REVIEWED` to `Reviewed by <name or handle>, <date>` and mention it in this file. If you cannot edit code, open an issue with the corrected strings in a table; that is enough.

## Tests

`tests/test_languages.py` covers detection (at least three realistic forwards per new language, the Hindi / Marathi / Konkani / Nepali and Bengali / Assamese cases, mixed scripts), sentence splitting, native digits, tokenising every script, the language tables, rendering (`lang` and `dir="rtl"` on the card, the selector, the hero counts), the JSON API and Telegram for every code, and end-to-end Bengali, Tamil, Urdu and Manipuri forwards with fake sources and a fake model.
