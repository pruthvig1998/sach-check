# Evaluation (fallback mode)

> **This run was degraded; it does not measure the full system.** It is saved separately and does not replace `docs/evaluation.md`.

Measured on commit `e81b1cc537d073196e2b8b282cd69289edb71b83` (working tree had uncommitted changes), 2026-11-13 (UTC).

Mode: FALLBACK; web search failed for 3 claims (disabled, out of credits or outage); retrieval: PibRetriever, BraveRetriever, FactCheckToolsRetriever; judges: vertex, groq, gemini, gemini, openrouter.

- Claims: **79** (see limitations)
- Exact-match accuracy: **32/79**
- **Overclaimed FALSE (the unforgivable failure): 0**
- **Overclaimed TRUE (also an overclaim): 0**
- Wrong verdicts other than overclaims (e.g. MISLEADING where a TRUE/FALSE label stands; ERRORs excluded): 1
- System failures (ERROR, judge problem or search failure; see Measures): 3/79
- Latency in ms (p50/p95, 79 samples): 12409.204/31882.936
- Label FALSE: 10/34 correct; 21 abstained as UNVERIFIED
- Label TRUE: 11/34 correct; 22 abstained as UNVERIFIED
- Label UNVERIFIED (controls): 11/11 answered UNVERIFIED as expected
- Seeded (the source's PRID is in data/seed_debunks.json or data/pib_index.jsonl; retrieval is partly circular): 10/29 correct
- Unseeded (retrieval had to find the page itself): 11/39 correct

## Measures, separately

Each measure has its own denominator. Read them separately; none is a score for the others.

| Measure | Count | Denominator | Share |
|---|---|---|---|
| Accuracy (exact match) | 32 | 79 claims | 40.5% |
| Abstention rate (UNVERIFIED where the label is TRUE or FALSE) | 43 | 68 decisive-label claims | 63.2% |
| Overclaim: FALSE (said FALSE, label was not) | 0 | 79 claims | 0.0% |
| Overclaim: TRUE (said TRUE, label was not) | 0 | 79 claims | 0.0% |
| Wrong but not an overclaim (e.g. MISLEADING; ERRORs excluded) | 1 | 79 claims | 1.3% |
| Claims with any failure (see below) | 3 | 79 claims | 3.8% |

Accuracy counts abstentions (UNVERIFIED) and ERRORs as misses: an UNVERIFIED answer to a TRUE or FALSE claim is not an exact match, even though it is safe.

### Failures

- Judge problem (a judge timed out or failed; the claim is degraded): **0**
  - none

- Search failure (web search down or partial): **3**
  - Union Minister Sarbananda Sonowal's office has issued a letter on this matter. (label FALSE, got UNVERIFIED)
  - బేటీ బచావో బేటీ పడావో పథకం కింద ప్రతి ఆడపిల్లకు ప్రభుత్వం 2 లక్షల రూపాయలు ఇస్తుంది, ఈ ఫారం నింపి పంపండి. (label FALSE, got UNVERIFIED)
  - ꯕꯦꯇꯤ ꯕꯆꯥꯎ ꯕꯦꯇꯤ ꯄꯥꯗꯥꯎ ꯌꯣꯖꯅꯥꯒꯤ ꯃꯈꯥꯗꯥ ꯁꯔꯀꯥꯔꯅꯥ ꯅꯨꯄꯤꯃꯆꯥ ꯈꯨꯗꯤꯡꯃꯛꯄꯨ ꯔꯨꯄꯤꯌꯥ ꯲ ꯂꯥꯈ ꯄꯤꯒꯅꯤ, ꯐꯣꯔꯝ ꯑꯁꯤ ꯃꯄꯨꯡ ꯐꯥꯍꯅꯗꯨꯅꯥ ꯊꯥꯕꯤꯌꯨ꯫ (label FALSE, got UNVERIFIED)

- ERROR (checking the claim raised an exception; counted as a failure, never as correct or abstained): **0**
  - none

- Source judgements where the LLM failed (quota or outage), from the checkpoint: **0**

Claims with at least one of the first three kinds of failure: **3** of 79. A claim can have more than one kind, so the three counts can add up to more than this.

## Latency (wall time per claim, seconds)

Nearest-rank percentiles. Each claim's time covers its whole check, including search and judge calls. With `--workers` above 1, claims share the provider, so times include that load.

| Group | Timed claims | p50 | p90 | p95 | max | mean |
|---|---|---|---|---|---|---|
| All claims | 79 | 12.41 | 24.27 | 31.88 | 38.96 | 14.27 |
| Layer: match | 1 | 0.07 | 0.07 | 0.07 | 0.07 | 0.07 |
| Layer: live | 78 | 12.41 | 24.27 | 31.88 | 38.96 | 14.45 |

Claims without timing: **0** (checkpoints written before timing was recorded).

## Which layer answered

Completed checks by layer.

| Layer | Claims | Exact match | Abstained | Overclaims |
|---|---|---|---|---|
| match | 1 | 1 | 0 | 0 |
| live | 78 | 31 | 43 | 0 |

`match` rows were answered by an existing PIB or fact-checker verdict, not by Sach's own check. Eval claims are often paraphrases of published PIB debunks, so match accuracy on this set is circular; run with `--no-match` to measure the live layer alone.


## By language

| Language | n | Exact match | Abstained | Overclaimed FALSE | Overclaimed TRUE | System failures |
|---|---|---|---|---|---|---|
| en | 33 | 20 | 12 | 0 | 0 | 1 |
| hi | 6 | 2 | 3 | 0 | 0 | 0 |
| te | 6 | 1 | 4 | 0 | 0 | 1 |
| hinglish | 3 | 1 | 2 | 0 | 0 | 0 |
| tinglish | 2 | 0 | 2 | 0 | 0 | 0 |
| bn | 2 | 1 | 1 | 0 | 0 | 0 |
| mr | 3 | 1 | 2 | 0 | 0 | 0 |
| ta | 3 | 1 | 2 | 0 | 0 | 0 |
| gu | 2 | 1 | 1 | 0 | 0 | 0 |
| ur | 3 | 1 | 2 | 0 | 0 | 0 |
| kn | 2 | 1 | 1 | 0 | 0 | 0 |
| or | 2 | 0 | 2 | 0 | 0 | 0 |
| ml | 2 | 0 | 2 | 0 | 0 | 0 |
| pa | 2 | 1 | 1 | 0 | 0 | 0 |
| as | 2 | 1 | 1 | 0 | 0 | 0 |
| kok | 2 | 0 | 2 | 0 | 0 | 0 |
| ne | 2 | 0 | 2 | 0 | 0 | 0 |
| mni | 2 | 0 | 1 | 0 | 0 | 1 |

Abstained = Sach said UNVERIFIED where the label was not UNVERIFIED (safe but a miss).

The site card's 'abstained' figure counts every such UNVERIFIED answer across all labels; the abstention rate in Measures counts only TRUE/FALSE-labelled claims. The 11 UNVERIFIED-labelled controls are correct when Sach says UNVERIFIED, so they are in neither count.

## Every claim

| Claim | Lang | Label | Sach | Result |
|---|---|---|---|---|
| Central Government will reduce the retirement age of employees to 50 years. | en | FALSE | FALSE | ok |
| Government has ordered the closure of Ministries. | en | FALSE | FALSE | ok |
| Air India passengers from Chicago were made to pay three times the fare. | en | FALSE | FALSE | ok |
| WHO doctors are advising against wearing masks and social distancing. | en | FALSE | UNVERIFIED | miss (abstained) |
| PIB Fact-Check Unit has issued over 2,900 fact checks. | en | TRUE | TRUE | ok |
| The Cabinet has approved declaring the 14th of every month as National Mango Day. | en | UNVERIFIED | UNVERIFIED | ok |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register. | en | FALSE | UNVERIFIED | miss (abstained) |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | en | FALSE | UNVERIFIED | system failure (not counted as abstained) |
| A Health Ministry office memorandum on state holidays has been issued. | en | FALSE | UNVERIFIED | miss (abstained) |
| Railways has issued a recruitment notification for 19,800 Constable posts in RPF. | en | FALSE | FALSE | ok |
| RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Cabinet Secretariat has advertised recruitment for 1,736 Field Assistant posts. | en | FALSE | FALSE | ok |
| The Centre has removed 55 lakh ration card holders from Punjab. | en | FALSE | UNVERIFIED | miss (abstained) |
| Ration cards of people who do not provide Aadhaar numbers will be cancelled. | en | FALSE | UNVERIFIED | miss (abstained) |
| The Railway Recruitment Board introduced a new method of result preparation for Level 1 results. | en | FALSE | FALSE | ok |
| India Post is offering subsidies and prizes to people who complete an online survey or quiz. | en | FALSE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved a scheme for coal and lignite gasification projects with an outlay of Rs 37,500 crore. | en | TRUE | TRUE | ok |
| The Union Cabinet has approved a scheme to replace old trucks and buses in the Delhi-NCR area. | en | TRUE | TRUE | ok |
| The Union Cabinet has approved Nutrient Based Subsidy rates for Rabi 2026-27 on phosphatic and potassic fertilizers. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet has approved modernization of Command Area Development and Water Management under Pradhan Mantri Krishi Sinchayee Yojana. | en | TRUE | TRUE | ok |
| The Union Cabinet has approved continuation of the Samagra Shiksha scheme from April 2021 to March 2026. | en | TRUE | TRUE | ok |
| The Union Cabinet has approved integration and continuation of two schemes under SARTHAK-PDS. | en | TRUE | UNVERIFIED | miss (abstained) |
| Railways has a recruitment process on for 1,20,579 vacancies notified in 2024 and 2025. | en | TRUE | TRUE | ok |
| Around 99.8% of ration cards have been seeded with Aadhaar. | en | TRUE | TRUE | ok |
| Railways plans to provide 50,000 jobs in financial year 2025-26. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Government has notified PIB's Fact Check Unit as a fact checker of the Central Government under the IT Rules 2021. | en | TRUE | UNVERIFIED | miss (abstained) |
| Suspected fake news can be sent to the PIB Fact Check WhatsApp hotline 8799711259. | en | TRUE | UNVERIFIED | miss (abstained) |
| The Ministry of Culture has declared turmeric the national spice of India. | en | UNVERIFIED | UNVERIFIED | ok |
| The Union Cabinet has approved renaming all national highways after rivers. | en | UNVERIFIED | UNVERIFIED | ok |
| The government has declared the first monsoon rain day of each year a national holiday. | en | UNVERIFIED | UNVERIFIED | ok |
| Every household in India will receive a free solar-powered refrigerator next month. | en | UNVERIFIED | UNVERIFIED | ok |
| ⚠️ ज़रूरी सूचना: NTA ने NEET UG जुलाई 2020 की परीक्षा स्थगित कर दी है, नोटिस वायरल हो रहा है। सबको भेजो! | hi | FALSE | UNVERIFIED | miss (abstained) |
| खुशखबरी! केंद्र सरकार ने कर्मचारियों और पेंशनरों का महंगाई भत्ता 3% बढ़ा दिया है, 1 जुलाई 2026 से लागू। शेयर करें। | hi | TRUE | MISLEADING | WRONG |
| सावधान! अब 2000 रुपये से ऊपर के UPI पेमेंट पर सरकार GST लगाने जा रही है। सबको फॉरवर्ड करो। | hi | FALSE | FALSE | ok |
| रबी विपणन सत्र 2027-28 के लिए गेहूं का MSP बढ़ाकर 2610 रुपये प्रति क्विंटल कर दिया गया है, सरकार का बड़ा फैसला। | hi | TRUE | UNVERIFIED | miss (abstained) |
| बड़ी खबर: केंद्र सरकार ने 1 जनवरी से सभी साइकिल चलाने वालों को हर महीने 500 रुपये 'हरित यात्रा भत्ता' देने का फैसला किया है। | hi | UNVERIFIED | UNVERIFIED | ok |
| सेना के आधुनिकीकरण के लिए सरकार ने नया बैंक खाता खोला है, कैबिनेट का फैसला है और अक्षय कुमार ने शुरू किया है। सब दान करें। | hi | FALSE | UNVERIFIED | miss (abstained) |
| RBI గవర్నర్ గారి వీడియో వైరల్ అవుతోంది: RBI కొత్త పెట్టుబడి పథకం ప్రారంభించింది, అందులో డబ్బు పెడితే భారీ లాభాలు వస్తాయి. అందరికీ షేర్ చేయండి. | te | FALSE | UNVERIFIED | miss (abstained) |
| కేంద్ర మంత్రివర్గం PM-KISAN పథకాన్ని 2026-27 నుంచి 2030-31 వరకు కొనసాగించడానికి ₹3.15 లక్షల కోట్లు ఆమోదించింది. | te | TRUE | UNVERIFIED | miss (abstained) |
| కోవిడ్ వల్ల కేంద్ర ప్రభుత్వ ఉద్యోగుల LTC, లీవ్ ఎన్‌క్యాష్‌మెంట్, మెడికల్ అలవెన్సులు కట్ చేస్తారట. షేర్ చేయండి. | te | FALSE | UNVERIFIED | miss (abstained) |
| వృద్ధాప్య, వితంతు పింఛన్లు ఉన్న జాతీయ సామాజిక సహాయ కార్యక్రమాన్ని (NSAP) 2026-27 నుంచి 2030-31 వరకు ₹53,428 కోట్లతో కొనసాగించడానికి కేబినెట్ ఆమోదించింది. | te | TRUE | UNVERIFIED | miss (abstained) |
| కేంద్ర ప్రభుత్వం ప్రతి గ్రామంలో ఉచితంగా ఒక జత చెప్పులు ఇచ్చే 'పాదరక్ష యోజన' ప్రారంభించింది, రేపటి నుంచి నమోదు మొదలు. | te | UNVERIFIED | UNVERIFIED | ok |
| బేటీ బచావో బేటీ పడావో పథకం కింద ప్రతి ఆడపిల్లకు ప్రభుత్వం 2 లక్షల రూపాయలు ఇస్తుంది, ఈ ఫారం నింపి పంపండి. | te | FALSE | UNVERIFIED | system failure (not counted as abstained) |
| Dhyan do! 1 January se RBI scribble ya likhe hue currency notes nahi lega, banks mana kar denge. Sabko forward karo. | hinglish | FALSE | UNVERIFIED | miss (abstained) |
| Sarkar ne kharif 2026-27 ke liye common paddy ka MSP 2441 rupaye per quintal tay kiya hai. | hinglish | TRUE | UNVERIFIED | miss (abstained) |
| Kal se sarkar har mobile user ko har mahine 5 kilo aam free dene wali hai, bas apna number register karo. | hinglish | UNVERIFIED | UNVERIFIED | ok |
| Petroleum ministry nunchi pettrol bunk dealership direct ga istunnaru ani newspaper lo ad vachindi, andaru apply cheyandi. | tinglish | FALSE | UNVERIFIED | miss (abstained) |
| UGC prakaram 2026 February list lo 32 fake universities unnayi ani prabhutvam cheppindi, andaru jagratta ga undandi. | tinglish | TRUE | UNVERIFIED | miss (abstained) |
| The Union Cabinet approved an incentive scheme for low-value BHIM-UPI person-to-merchant transactions with an outlay of Rs 1,500 crore for 2024-25. | en | TRUE | TRUE | ok |
| The Cabinet has fixed the MSP for milling copra at Rs 12,027 per quintal for the 2026 season. | en | TRUE | TRUE | ok |
| সাবধান! এবার ২০০০ টাকার বেশি UPI পেমেন্টে সরকার GST বসাতে চলেছে। সবাইকে ফরওয়ার্ড করুন। | bn | FALSE | FALSE | ok |
| সুখবর! কেন্দ্রীয় সরকার কর্মচারী ও পেনশনভোগীদের মহার্ঘ ভাতা ৩% বাড়িয়ে দিয়েছে, ১ জুলাই ২০২৬ থেকে কার্যকর। শেয়ার করুন। | bn | TRUE | UNVERIFIED | miss (abstained) |
| ⚠️ জৰুৰী বিজ্ঞপ্তি: NTA-এ NEET UG জুলাই ২০২০ৰ পৰীক্ষা পিছুৱাই দিছে, নোটিছখন ভাইৰেল হৈছে। সকলোলৈ পঠিয়াওক! | as | FALSE | FALSE | ok |
| ভাৰত চৰকাৰে খৰিফ ২০২৬-২৭ৰ বাবে সাধাৰণ ধানৰ MSP প্ৰতি কুইণ্টল ২৪৪১ টকা ঠিক কৰিছে। | as | TRUE | UNVERIFIED | miss (abstained) |
| ꯕꯦꯇꯤ ꯕꯆꯥꯎ ꯕꯦꯇꯤ ꯄꯥꯗꯥꯎ ꯌꯣꯖꯅꯥꯒꯤ ꯃꯈꯥꯗꯥ ꯁꯔꯀꯥꯔꯅꯥ ꯅꯨꯄꯤꯃꯆꯥ ꯈꯨꯗꯤꯡꯃꯛꯄꯨ ꯔꯨꯄꯤꯌꯥ ꯲ ꯂꯥꯈ ꯄꯤꯒꯅꯤ, ꯐꯣꯔꯝ ꯑꯁꯤ ꯃꯄꯨꯡ ꯐꯥꯍꯅꯗꯨꯅꯥ ꯊꯥꯕꯤꯌꯨ꯫ | mni | FALSE | UNVERIFIED | system failure (not counted as abstained) |
| ꯌꯨꯅꯤꯌꯟ ꯀꯦꯕꯤꯅꯦꯠꯅꯥ PM-KISAN ꯌꯣꯖꯅꯥ ꯑꯁꯤ ꯲꯰꯲꯶-꯲꯷ ꯗꯒꯤ ꯲꯰꯳꯰-꯳꯱ ꯐꯥꯑꯣꯕꯥ ꯃꯈꯥ ꯆꯠꯍꯅꯅꯕꯥ ₹꯳.꯱꯵ ꯂꯥꯈ ꯀ꯭ꯔꯣꯔ ꯌꯥꯕꯤꯔꯦ꯫ | mni | TRUE | UNVERIFIED | miss (abstained) |
| लक्ष द्या! १ जानेवारीपासून ज्या नोटांवर काहीही लिहिलेले किंवा खरडलेले असेल त्या नोटा RBI घेणार नाही, बँका नाकारतील. सर्वांना फॉरवर्ड करा. | mr | FALSE | UNVERIFIED | miss (abstained) |
| रब्बी विपणन हंगाम २०२७-२८ साठी गव्हाची MSP वाढवून २६१० रुपये प्रति क्विंटल करण्यात आली आहे, सरकारचा मोठा निर्णय. | mr | TRUE | UNVERIFIED | miss (abstained) |
| सैन्याच्या आधुनिकीकरणाखातीर सरकारान नवें बँक खातें उगडलां, कॅबिनेटाचो निर्णय आसा आनी अक्षय कुमारान तें सुरू केलां. सगळ्यांनी दान करात. | kok | FALSE | UNVERIFIED | miss (abstained) |
| वृद्धापकाळ आनी विधवा पेन्शन आशिल्लो राष्ट्रीय सामाजिक सहाय्य कार्यक्रम (NSAP) २०२६-२७ ते २०३०-३१ मेरेन ₹५३,४२८ कोटींनी चालू दवरपाक केंद्रीय केबिनेटान मंजुरी दिल्ली. | kok | TRUE | UNVERIFIED | miss (abstained) |
| कोभिडका कारण केन्द्र सरकारका कर्मचारीहरूको LTC, बिदा नगदीकरण र मेडिकल भत्ता कटौती गरिने रे। सबैलाई सेयर गर्नुहोस्। | ne | FALSE | UNVERIFIED | miss (abstained) |
| UGC को २०२६ फेब्रुअरीको सूची अनुसार ३२ वटा नक्कली विश्वविद्यालय छन् भनी सरकारले भनेको छ, सबै सतर्क रहनुहोस्। | ne | TRUE | UNVERIFIED | miss (abstained) |
| RBI கவர்னரின் வீடியோ வைரலாகிறது: RBI புதிய முதலீட்டுத் திட்டத்தைத் தொடங்கியுள்ளது, அதில் பணம் போட்டால் பெரிய லாபம் கிடைக்கும். அனைவருக்கும் ஷேர் செய்யுங்கள். | ta | FALSE | UNVERIFIED | miss (abstained) |
| 2026 பருவத்திற்கான அரவைக் கொப்பரைக்கு குறைந்தபட்ச ஆதரவு விலையை (MSP) மத்திய அமைச்சரவை குவிண்டாலுக்கு ரூ 12,027 என நிர்ணயித்துள்ளது. | ta | TRUE | UNVERIFIED | miss (abstained) |
| અખબારમાં જાહેરાત આવી છે કે પેટ્રોલિયમ મંત્રાલય સીધું પેટ્રોલ પંપ ડીલરશિપ આપી રહ્યું છે, બધા અરજી કરો. | gu | FALSE | UNVERIFIED | miss (abstained) |
| કેન્દ્રીય મંત્રીમંડળે ૨૦૨૪-૨૫ માટે ઓછી કિંમતના BHIM-UPI પર્સન-ટુ-મર્ચન્ટ વ્યવહારો માટે રૂ. ૧,૫૦૦ કરોડના ખર્ચ સાથે પ્રોત્સાહન યોજનાને મંજૂરી આપી છે. | gu | TRUE | TRUE | ok |
| ਸਾਵਧਾਨ! ਹੁਣ 2000 ਰੁਪਏ ਤੋਂ ਉੱਪਰ ਦੇ UPI ਪੇਮੈਂਟ 'ਤੇ ਸਰਕਾਰ GST ਲਗਾਉਣ ਜਾ ਰਹੀ ਹੈ। ਸਭ ਨੂੰ ਅੱਗੇ ਭੇਜੋ। | pa | FALSE | FALSE | ok |
| ਸਰਕਾਰ ਨੇ ਖਰੀਫ਼ 2026-27 ਲਈ ਆਮ ਝੋਨੇ ਦਾ MSP 2441 ਰੁਪਏ ਪ੍ਰਤੀ ਕੁਇੰਟਲ ਤੈਅ ਕੀਤਾ ਹੈ। | pa | TRUE | UNVERIFIED | miss (abstained) |
| ବେଟି ବଚାଓ ବେଟି ପଢ଼ାଓ ଯୋଜନାରେ ସରକାର ପ୍ରତ୍ୟେକ ଝିଅକୁ ୨ ଲକ୍ଷ ଟଙ୍କା ଦେବେ, ଏହି ଫର୍ମ ପୂରଣ କରି ପଠାନ୍ତୁ। | or | FALSE | UNVERIFIED | miss (abstained) |
| କେନ୍ଦ୍ର କ୍ୟାବିନେଟ୍ PM-KISAN ଯୋଜନାକୁ ୨୦୨୬-୨୭ ରୁ ୨୦୩୦-୩୧ ପର୍ଯ୍ୟନ୍ତ ଜାରି ରଖିବା ପାଇଁ ₹୩.୧୫ ଲକ୍ଷ କୋଟି ଟଙ୍କା ମଞ୍ଜୁର କରିଛି। | or | TRUE | UNVERIFIED | miss (abstained) |
| ⚠️ ಮುಖ್ಯ ಸೂಚನೆ: NTA NEET UG ಜುಲೈ 2020 ಪರೀಕ್ಷೆಯನ್ನು ಮುಂದೂಡಿದೆ, ನೋಟಿಸ್ ವೈರಲ್ ಆಗುತ್ತಿದೆ. ಎಲ್ಲರಿಗೂ ಕಳುಹಿಸಿ! | kn | FALSE | UNVERIFIED | miss (abstained) |
| 2024-25ಕ್ಕೆ ಕಡಿಮೆ ಮೌಲ್ಯದ BHIM-UPI ವ್ಯಾಪಾರಿ ಪಾವತಿ (ಪರ್ಸನ್-ಟು-ಮರ್ಚೆಂಟ್) ವಹಿವಾಟುಗಳಿಗೆ ರೂ 1,500 ಕೋಟಿ ವೆಚ್ಚದ ಪ್ರೋತ್ಸಾಹ ಯೋಜನೆಗೆ ಕೇಂದ್ರ ಸಚಿವ ಸಂಪುಟ ಅನುಮೋದನೆ ನೀಡಿದೆ. | kn | TRUE | TRUE | ok |
| സൈന്യത്തിന്റെ ആധുനികീകരണത്തിനായി സർക്കാർ പുതിയ ബാങ്ക് അക്കൗണ്ട് തുടങ്ങി, കാബിനറ്റ് തീരുമാനമാണ്, അക്ഷയ് കുമാർ ആണ് തുടക്കം കുറിച്ചത്. എല്ലാവരും സംഭാവന ചെയ്യുക. | ml | FALSE | UNVERIFIED | miss (abstained) |
| 2026 സീസണിലെ മില്ലിങ് കൊപ്രയ്ക്ക് ക്വിന്റലിന് 12,027 രൂപ താങ്ങുവിലയായി (MSP) കേന്ദ്ര മന്ത്രിസഭ നിശ്ചയിച്ചു. | ml | TRUE | UNVERIFIED | miss (abstained) |
| آر بی آئی گورنر کی ویڈیو وائرل ہو رہی ہے: RBI نے نئی سرمایہ کاری اسکیم شروع کی ہے، اس میں پیسے لگائیں تو بھاری منافع ملے گا۔ سب کو شیئر کریں۔ | ur | FALSE | UNVERIFIED | miss (abstained) |
| خوشخبری! مرکزی حکومت نے ملازمین اور پنشنرز کا مہنگائی بھتہ 3% بڑھا دیا ہے، 1 جولائی 2026 سے نافذ۔ شیئر کریں۔ | ur | TRUE | UNVERIFIED | miss (abstained) |
| केंद्र सरकारने 'पतंग प्रोत्साहन भत्ता' जाहीर केला आहे, पतंग उडवणाऱ्या प्रत्येकाला दरमहा ४२० रुपये मिळतील, उद्यापासून नोंदणी सुरू. | mr | UNVERIFIED | UNVERIFIED | ok |
| மத்திய அரசு ஒவ்வொரு வீட்டிற்கும் ஆண்டுக்கு 2 மூங்கில் குடைகளை இலவசமாக வழங்கும் 'குடை நல யோஜனா' நாளை முதல் தொடங்குகிறது, உடனே பதிவு செய்யுங்கள். | ta | UNVERIFIED | UNVERIFIED | ok |
| حکومت نے اعلان کیا ہے کہ جس کے پاس پرانی دیوار گھڑی ہے اسے 'وقت سمان اسکیم' کے تحت ہر ماہ 650 روپے ملیں گے، ابھی رجسٹر کریں۔ | ur | UNVERIFIED | UNVERIFIED | ok |

## Failed, abstained and wrong cases

Every claim whose result is not an exact match: 47 of 79. Nothing is left out of this table.

| Claim | Lang | Label | Sach | Layer | Reason codes | Result | Why | ms | Error |
|---|---|---|---|---|---|---|---|---|---|
| WHO doctors are advising against wearing masks and social distancing. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 12409.204 | - |
| Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 13213.919 | - |
| Union Minister Sarbananda Sonowal's office has issued a letter on this matter. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | search failure, abstained | 31882.936 | - |
| A Health Ministry office memorandum on state holidays has been issued. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 12276.429 | - |
| RPF has announced recruitment of 4,208 Constables and 452 Sub-Inspectors. | en | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9744.078 | - |
| The Centre has removed 55 lakh ration card holders from Punjab. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 17428.233 | - |
| Ration cards of people who do not provide Aadhaar numbers will be cancelled. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 10478.608 | - |
| India Post is offering subsidies and prizes to people who complete an online survey or quiz. | en | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 16156.869 | - |
| The Union Cabinet has approved Nutrient Based Subsidy rates for Rabi 2026-27 on phosphatic and potassic fertilizers. | en | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 16964.805 | - |
| The Union Cabinet has approved integration and continuation of two schemes under SARTHAK-PDS. | en | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 10301.925 | - |
| Railways plans to provide 50,000 jobs in financial year 2025-26. | en | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9442.584 | - |
| The Government has notified PIB's Fact Check Unit as a fact checker of the Central Government under the IT Rules 2021. | en | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 7734.849 | - |
| Suspected fake news can be sent to the PIB Fact Check WhatsApp hotline 8799711259. | en | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9429.625 | - |
| ⚠️ ज़रूरी सूचना: NTA ने NEET UG जुलाई 2020 की परीक्षा स्थगित कर दी है, नोटिस वायरल हो रहा है। सबको भेजो! | hi | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 13008.377 | - |
| खुशखबरी! केंद्र सरकार ने कर्मचारियों और पेंशनरों का महंगाई भत्ता 3% बढ़ा दिया है, 1 जुलाई 2026 से लागू। शेयर करें। | hi | TRUE | MISLEADING | live | core_fact_distorted | WRONG | wrong verdict | 16283.447 | - |
| रबी विपणन सत्र 2027-28 के लिए गेहूं का MSP बढ़ाकर 2610 रुपये प्रति क्विंटल कर दिया गया है, सरकार का बड़ा फैसला। | hi | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 7788.389 | - |
| सेना के आधुनिकीकरण के लिए सरकार ने नया बैंक खाता खोला है, कैबिनेट का फैसला है और अक्षय कुमार ने शुरू किया है। सब दान करें। | hi | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 11316.723 | - |
| RBI గవర్నర్ గారి వీడియో వైరల్ అవుతోంది: RBI కొత్త పెట్టుబడి పథకం ప్రారంభించింది, అందులో డబ్బు పెడితే భారీ లాభాలు వస్తాయి. అందరికీ షేర్ చేయండి. | te | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 14601.072 | - |
| కేంద్ర మంత్రివర్గం PM-KISAN పథకాన్ని 2026-27 నుంచి 2030-31 వరకు కొనసాగించడానికి ₹3.15 లక్షల కోట్లు ఆమోదించింది. | te | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9820.182 | - |
| కోవిడ్ వల్ల కేంద్ర ప్రభుత్వ ఉద్యోగుల LTC, లీవ్ ఎన్‌క్యాష్‌మెంట్, మెడికల్ అలవెన్సులు కట్ చేస్తారట. షేర్ చేయండి. | te | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9164.624 | - |
| వృద్ధాప్య, వితంతు పింఛన్లు ఉన్న జాతీయ సామాజిక సహాయ కార్యక్రమాన్ని (NSAP) 2026-27 నుంచి 2030-31 వరకు ₹53,428 కోట్లతో కొనసాగించడానికి కేబినెట్ ఆమోదించింది. | te | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9307.356 | - |
| బేటీ బచావో బేటీ పడావో పథకం కింద ప్రతి ఆడపిల్లకు ప్రభుత్వం 2 లక్షల రూపాయలు ఇస్తుంది, ఈ ఫారం నింపి పంపండి. | te | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | search failure, abstained | 31685.494 | - |
| Dhyan do! 1 January se RBI scribble ya likhe hue currency notes nahi lega, banks mana kar denge. Sabko forward karo. | hinglish | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 11924.592 | - |
| Sarkar ne kharif 2026-27 ke liye common paddy ka MSP 2441 rupaye per quintal tay kiya hai. | hinglish | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 30442.581 | - |
| Petroleum ministry nunchi pettrol bunk dealership direct ga istunnaru ani newspaper lo ad vachindi, andaru apply cheyandi. | tinglish | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 16792.462 | - |
| UGC prakaram 2026 February list lo 32 fake universities unnayi ani prabhutvam cheppindi, andaru jagratta ga undandi. | tinglish | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 14164.362 | - |
| সুখবর! কেন্দ্রীয় সরকার কর্মচারী ও পেনশনভোগীদের মহার্ঘ ভাতা ৩% বাড়িয়ে দিয়েছে, ১ জুলাই ২০২৬ থেকে কার্যকর। শেয়ার করুন। | bn | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 11545.405 | - |
| ভাৰত চৰকাৰে খৰিফ ২০২৬-২৭ৰ বাবে সাধাৰণ ধানৰ MSP প্ৰতি কুইণ্টল ২৪৪১ টকা ঠিক কৰিছে। | as | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 6937.159 | - |
| ꯕꯦꯇꯤ ꯕꯆꯥꯎ ꯕꯦꯇꯤ ꯄꯥꯗꯥꯎ ꯌꯣꯖꯅꯥꯒꯤ ꯃꯈꯥꯗꯥ ꯁꯔꯀꯥꯔꯅꯥ ꯅꯨꯄꯤꯃꯆꯥ ꯈꯨꯗꯤꯡꯃꯛꯄꯨ ꯔꯨꯄꯤꯌꯥ ꯲ ꯂꯥꯈ ꯄꯤꯒꯅꯤ, ꯐꯣꯔꯝ ꯑꯁꯤ ꯃꯄꯨꯡ ꯐꯥꯍꯅꯗꯨꯅꯥ ꯊꯥꯕꯤꯌꯨ꯫ | mni | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | search failure, abstained | 31923.637 | - |
| ꯌꯨꯅꯤꯌꯟ ꯀꯦꯕꯤꯅꯦꯠꯅꯥ PM-KISAN ꯌꯣꯖꯅꯥ ꯑꯁꯤ ꯲꯰꯲꯶-꯲꯷ ꯗꯒꯤ ꯲꯰꯳꯰-꯳꯱ ꯐꯥꯑꯣꯕꯥ ꯃꯈꯥ ꯆꯠꯍꯅꯅꯕꯥ ₹꯳.꯱꯵ ꯂꯥꯈ ꯀ꯭ꯔꯣꯔ ꯌꯥꯕꯤꯔꯦ꯫ | mni | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 10294.461 | - |
| लक्ष द्या! १ जानेवारीपासून ज्या नोटांवर काहीही लिहिलेले किंवा खरडलेले असेल त्या नोटा RBI घेणार नाही, बँका नाकारतील. सर्वांना फॉरवर्ड करा. | mr | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 10925.403 | - |
| रब्बी विपणन हंगाम २०२७-२८ साठी गव्हाची MSP वाढवून २६१० रुपये प्रति क्विंटल करण्यात आली आहे, सरकारचा मोठा निर्णय. | mr | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 10560.35 | - |
| सैन्याच्या आधुनिकीकरणाखातीर सरकारान नवें बँक खातें उगडलां, कॅबिनेटाचो निर्णय आसा आनी अक्षय कुमारान तें सुरू केलां. सगळ्यांनी दान करात. | kok | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 6501.687 | - |
| वृद्धापकाळ आनी विधवा पेन्शन आशिल्लो राष्ट्रीय सामाजिक सहाय्य कार्यक्रम (NSAP) २०२६-२७ ते २०३०-३१ मेरेन ₹५३,४२८ कोटींनी चालू दवरपाक केंद्रीय केबिनेटान मंजुरी दिल्ली. | kok | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 38963.833 | - |
| कोभिडका कारण केन्द्र सरकारका कर्मचारीहरूको LTC, बिदा नगदीकरण र मेडिकल भत्ता कटौती गरिने रे। सबैलाई सेयर गर्नुहोस्। | ne | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 5697.541 | - |
| UGC को २०२६ फेब्रुअरीको सूची अनुसार ३२ वटा नक्कली विश्वविद्यालय छन् भनी सरकारले भनेको छ, सबै सतर्क रहनुहोस्। | ne | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9825.344 | - |
| RBI கவர்னரின் வீடியோ வைரலாகிறது: RBI புதிய முதலீட்டுத் திட்டத்தைத் தொடங்கியுள்ளது, அதில் பணம் போட்டால் பெரிய லாபம் கிடைக்கும். அனைவருக்கும் ஷேர் செய்யுங்கள். | ta | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 8816.22 | - |
| 2026 பருவத்திற்கான அரவைக் கொப்பரைக்கு குறைந்தபட்ச ஆதரவு விலையை (MSP) மத்திய அமைச்சரவை குவிண்டாலுக்கு ரூ 12,027 என நிர்ணயித்துள்ளது. | ta | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 11263.013 | - |
| અખબારમાં જાહેરાત આવી છે કે પેટ્રોલિયમ મંત્રાલય સીધું પેટ્રોલ પંપ ડીલરશિપ આપી રહ્યું છે, બધા અરજી કરો. | gu | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 15795.311 | - |
| ਸਰਕਾਰ ਨੇ ਖਰੀਫ਼ 2026-27 ਲਈ ਆਮ ਝੋਨੇ ਦਾ MSP 2441 ਰੁਪਏ ਪ੍ਰਤੀ ਕੁਇੰਟਲ ਤੈਅ ਕੀਤਾ ਹੈ। | pa | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 11563.968 | - |
| ବେଟି ବଚାଓ ବେଟି ପଢ଼ାଓ ଯୋଜନାରେ ସରକାର ପ୍ରତ୍ୟେକ ଝିଅକୁ ୨ ଲକ୍ଷ ଟଙ୍କା ଦେବେ, ଏହି ଫର୍ମ ପୂରଣ କରି ପଠାନ୍ତୁ। | or | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 12583.294 | - |
| କେନ୍ଦ୍ର କ୍ୟାବିନେଟ୍ PM-KISAN ଯୋଜନାକୁ ୨୦୨୬-୨୭ ରୁ ୨୦୩୦-୩୧ ପର୍ଯ୍ୟନ୍ତ ଜାରି ରଖିବା ପାଇଁ ₹୩.୧୫ ଲକ୍ଷ କୋଟି ଟଙ୍କା ମଞ୍ଜୁର କରିଛି। | or | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 24269.713 | - |
| ⚠️ ಮುಖ್ಯ ಸೂಚನೆ: NTA NEET UG ಜುಲೈ 2020 ಪರೀಕ್ಷೆಯನ್ನು ಮುಂದೂಡಿದೆ, ನೋಟಿಸ್ ವೈರಲ್ ಆಗುತ್ತಿದೆ. ಎಲ್ಲರಿಗೂ ಕಳುಹಿಸಿ! | kn | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 11909.829 | - |
| സൈന്യത്തിന്റെ ആധുനികീകരണത്തിനായി സർക്കാർ പുതിയ ബാങ്ക് അക്കൗണ്ട് തുടങ്ങി, കാബിനറ്റ് തീരുമാനമാണ്, അക്ഷയ് കുമാർ ആണ് തുടക്കം കുറിച്ചത്. എല്ലാവരും സംഭാവന ചെയ്യുക. | ml | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 14708.3 | - |
| 2026 സീസണിലെ മില്ലിങ് കൊപ്രയ്ക്ക് ക്വിന്റലിന് 12,027 രൂപ താങ്ങുവിലയായി (MSP) കേന്ദ്ര മന്ത്രിസഭ നിശ്ചയിച്ചു. | ml | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 23050.692 | - |
| آر بی آئی گورنر کی ویڈیو وائرل ہو رہی ہے: RBI نے نئی سرمایہ کاری اسکیم شروع کی ہے، اس میں پیسے لگائیں تو بھاری منافع ملے گا۔ سب کو شیئر کریں۔ | ur | FALSE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 9884.822 | - |
| خوشخبری! مرکزی حکومت نے ملازمین اور پنشنرز کا مہنگائی بھتہ 3% بڑھا دیا ہے، 1 جولائی 2026 سے نافذ۔ شیئر کریں۔ | ur | TRUE | UNVERIFIED | live | no_evidence | miss (abstained) | abstained | 12058.481 | - |

## Limitations (read before citing these numbers)
- The set is small (79 claims here). Every non-control row was checked by fetching the cited official page and reading it; rows are not bulk-scraped. PIB has no listing page for debunks and its RSS feed returns only the latest 20 items, so a real 100+ set needs more manual work or a crawl. Rows added in the v2 revision carry the fetch date in `verified_on`; the original 31 rows were verified in the original build and were not re-fetched.
- The Hindi, Telugu, Hinglish and Tinglish rows were written by an AI model and have not been reviewed by a native speaker. Real forwards are messier. Treat per-language numbers as a smoke test, not a measurement of how Sach does on real forwards in that language.
- Per-language groups are tiny (a handful of rows each), so one claim moves a percentage a lot.
- Rows marked `seeded` have their PIB page in the hand-seeded list or the harvested index, so retrieval for them is partly circular and their accuracy is optimistic. Many FALSE claims paraphrase PIB debunk titles for the same reason.
- Relabel disclosure: the first control ("free laptops to all students") scored as an overclaim, but Brave found genuine official debunks of it (newsonair.gov.in), so the LLM was right and the label was wrong. Control replaced with an invented claim after seeing that result.
- Relabel disclosure 2: the RPF 4,208 Constable / 452 SI claim was first labelled FALSE (from PIB debunk 2009349), but that debunk was about a fake notice on one website; a genuine PIB release (PRID 2246142) lists those same vacancy numbers. Sach said TRUE; relabelled TRUE after inspecting the evidence. Two labels were changed after seeing results, so treat headline accuracy as indicative only.
- Retrieval varies run to run (live search results change), so single-run numbers move by a claim or two. The evaluation runs with the verdict cache switched off (`SACH_NO_CACHE=1`).
- Official-domain rule is *.gov.in / *.nic.in / who.int (plus a few listed hosts), so news sites such as newsonair.gov.in count as official; PIB is treated as the strongest tier.
- There are no true MISLEADING rows: PIB items tagged "misleading" are labelled FALSE, so a MISLEADING verdict on them counts as a wrong verdict here.

## What this run did not measure

- Real-user outcomes: this measures Sach's verdicts against labelled claims. It does not measure whether people who receive a forward are helped, or what they do after a check.
- The eval set was written by the builders, not collected from real forwards. Claims are cleaner than real forwards (no typos, mixed scripts, emoji or long chains).
- Seeded vs unseeded: seeded rows can be found in Sach's own index, so their retrieval is partly circular. The split is shown, but it is not a clean test of retrieval.
- Non-English claims were written by the builders (by an AI model for most), and no native speaker has reviewed them.
- Single run: one run, no repeats. Live search results and model output vary, so a difference of a claim or two is noise.
- Provider variability: which LLM and search provider answered, and any fallback, changes results and latency. Latency also depends on provider load and on `--workers`.

## Previous runs

- None archived yet.
