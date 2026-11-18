"""News tier, social signal and the display of the extra knowledge layers.

Why: no government page records an actor's death, a match result or a film release, so those claims could never be confirmed or denied.
What this adds, WITHOUT a new route to TRUE or FALSE (sach/verdict.py ignores the news tier):
  REPORTED             at least two independent established news organisations report it (three for a death, unless one is a news agency)
  DENIED BY NEWS       at least two report that it is not true (for example a death hoax)
  NO RELIABLE REPORT   a claim that a person has died, and none of the outlets searched reports it
The machine verdict stays UNVERIFIED; these are a separate, clearly labelled finding in the claim's trace ("reported").

The social signal counts public posts a web search finds on X, Facebook and Instagram and names established accounts among them. Sach cannot
read those posts (the platforms have no free API), and many posts do not make a claim true: viral false claims are posted by many genuine
people. So the count is shown as a signal and never decides anything.

Switches (all off by default): SACH_NEWS_TIER=1, SACH_SOCIAL_SIGNAL=1."""
from __future__ import annotations
import os, re
from urllib.parse import urlparse
from .fetch import host_of, _under
from .models import UNVERIFIED

TIER_NEWS = "news"

# Established news organisations, by owner, so two titles of one company count once. A news agency ("wire") supplies many outlets.
# shortcut: outlets that reprint one agency story still count separately, upgrade by comparing article text when this matters.
NEWS_GROUPS = {
    "ptinews.com": "PTI", "aninews.in": "ANI", "uniindia.com": "UNI",
    "newsonair.gov.in": "All India Radio", "ddnews.gov.in": "DD News",        # public broadcasters: news reports, not government orders
    "thehindu.com": "The Hindu", "thehindubusinessline.com": "The Hindu",
    "indianexpress.com": "The Indian Express", "financialexpress.com": "The Indian Express",
    "timesofindia.indiatimes.com": "Times of India", "economictimes.indiatimes.com": "Times of India",
    "hindustantimes.com": "Hindustan Times", "livemint.com": "Hindustan Times", "livehindustan.com": "Hindustan Times",
    "ndtv.com": "NDTV", "indiatoday.in": "India Today", "aajtak.in": "India Today",
    "deccanherald.com": "Deccan Herald", "prajavani.net": "Deccan Herald",
    "newindianexpress.com": "The New Indian Express", "dinamani.com": "The New Indian Express",
    "telegraphindia.com": "ABP", "anandabazar.com": "ABP", "abplive.com": "ABP",
    "news18.com": "Network18", "firstpost.com": "Network18", "moneycontrol.com": "Network18",
    "business-standard.com": "Business Standard", "tribuneindia.com": "The Tribune", "deccanchronicle.com": "Deccan Chronicle",
    "thenewsminute.com": "The News Minute", "scroll.in": "Scroll", "theprint.in": "ThePrint", "thewire.in": "The Wire",
    "eenadu.net": "Eenadu", "sakshi.com": "Sakshi", "andhrajyothy.com": "Andhra Jyothy",
    "jagran.com": "Dainik Jagran", "bhaskar.com": "Dainik Bhaskar", "amarujala.com": "Amar Ujala",
    "mathrubhumi.com": "Mathrubhumi", "manoramaonline.com": "Malayala Manorama", "onmanorama.com": "Malayala Manorama",
    "dinamalar.com": "Dinamalar", "lokmat.com": "Lokmat", "loksatta.com": "The Indian Express",
    "bbc.com": "BBC", "bbc.co.uk": "BBC", "reuters.com": "Reuters", "apnews.com": "AP",
}
WIRES = {"PTI", "ANI", "UNI", "Reuters", "AP", "All India Radio", "DD News"}
PER_QUERY = 4
# The news search names its outlets. An unrestricted query goes to the Google-grounded provider first, which by design returns only government
# and fact-checker pages, so every news result was lost (found by the live test on 18 Nov 2026). A site: query skips that provider by policy.
QUERY_HOSTS = ("ptinews.com", "aninews.in", "newsonair.gov.in", "thehindu.com", "indianexpress.com", "timesofindia.indiatimes.com",
               "hindustantimes.com", "ndtv.com", "indiatoday.in", "news18.com", "deccanherald.com", "eenadu.net", "sakshi.com", "bbc.com")
NEWS_Q = "(" + " OR ".join("site:" + h for h in QUERY_HOSTS) + ")"

# Broad: any wording that may be about a death. Used only to RAISE the number of outlets needed, so a false hit is harmless.
_DEATH = re.compile(r"\b(died|dies|dead|death|passed away|passes away|pass away|is no more|demise|demised|funeral|killed|murdered|succumbed|"
                    r"lost (?:his|her|their) life)\b|निधन|मृत्यु|मौत|देहांत|नहीं रहे|మృతి|మరణ|కన్నుమూ|చనిపో|ఇకలేరు", re.I)
# Narrow: a plain statement or question that a person has died. Only for this does finding no report mean anything, and only when the text
# names no past year (silence about "X died in 1948" says nothing). Other events are left out on purpose: the search is too shallow.
_DEATH_NOW = re.compile(r"\b(died|dies|ka nidhan|nidhan ho|passed away|passes away|pass away|succumbed|lost (?:his|her|their) life)\b|"
                        r"का निधन|निधन हो|देहांत हो|की मृत्यु हो|నిధనం|కన్నుమూశ|మృతి చెంద|మరణించ|చనిపోయ", re.I)


def _recent_death_claim(text: str) -> bool:
    import time
    years = [int(y) for y in re.findall(r"(?<!\d)((?:18|19|20)\d\d)(?!\d)", text or "")]
    return bool(_DEATH_NOW.search(text or "")) and not any(y < time.gmtime().tm_year for y in years)


def news_enabled() -> bool:
    return os.environ.get("SACH_NEWS_TIER", "0") == "1"


def social_enabled() -> bool:
    return os.environ.get("SACH_SOCIAL_SIGNAL", "0") == "1"


def group_of(url: str) -> str:
    h = host_of(url)
    for d, g in NEWS_GROUPS.items():
        if h and _under(h, d):
            return g
    return ""


def is_news(url: str) -> bool:
    return bool(group_of(url))


def is_death_claim(text: str) -> bool:
    return bool(_DEATH.search(text or ""))


def assess(claim: str, evidence: list, searched: bool) -> dict | None:
    """What established news organisations say about `claim`, from the judged news-tier evidence. None when the news tier has nothing to say.
    `searched`: the news search ran and answered, so finding no report is itself information (for event-type claims only)."""
    conf, den = {}, {}
    for e in evidence:
        if getattr(e, "tier", "") != TIER_NEWS:
            continue
        g = group_of(e.url)
        if not g:
            continue
        if e.stance == "confirms":
            conf.setdefault(g, e)
        elif e.stance == "contradicts":
            den.setdefault(g, e)
    need = 3 if is_death_claim(claim) and not (set(conf) & WIRES) else 2      # a death needs more than two retellings of a rumour
    if conf and den:
        status = "conflicting"
    elif len(conf) >= need:
        status = "reported"
    elif len(den) >= 2:
        status = "denied"
    elif conf or den:
        status = "single_report"
    elif searched and _recent_death_claim(claim):
        status = "no_reliable_report"
    else:
        return None
    outlets = [{"source": g, "url": e.url, "fetched_at": e.fetched_at, "says": "reports it" if e.stance == "confirms" else "says it is not true"}
               for g, e in list(conf.items()) + list(den.items())]
    return {"status": status, "outlets": outlets[:6]}


# ---------------------------------------------------------------- social signal (a count, never evidence)
SOCIAL_Q = "(site:x.com OR site:twitter.com OR site:facebook.com OR site:instagram.com)"
_PLATFORM = {"x.com": "X", "twitter.com": "X", "facebook.com": "Facebook", "instagram.com": "Instagram"}
# Accounts of bodies Sach already treats as official or as established news organisations (lower case).
KNOWN_HANDLES = {"pibfactcheck": "PIB Fact Check", "pib_india": "PIB India", "mygovindia": "MyGov", "airnewsalerts": "All India Radio News",
                 "ddnewslive": "DD News", "pti_news": "PTI", "ani": "ANI", "the_hindu": "The Hindu", "indianexpress": "The Indian Express",
                 "timesofindia": "Times of India", "httweets": "Hindustan Times", "ndtv": "NDTV", "indiatoday": "India Today"}
_SKIP = {"hashtag", "search", "i", "home", "explore", "share", "sharer", "watch", "groups", "p", "reel", "reels", "stories", "events", "login"}


def platform_of(url: str) -> str:
    h = host_of(url)
    return next((p for d, p in _PLATFORM.items() if h and _under(h, d)), "")


def is_social(url: str) -> bool:
    return bool(platform_of(url))


def social_signal(urls) -> dict | None:
    """Counts of public posts a search found, by platform, and the established accounts among them. Sach has not read the posts."""
    plats, known, n = {}, [], 0
    for u in dict.fromkeys(urls or []):
        p = platform_of(u)
        if not p:
            continue
        n += 1
        plats[p] = plats.get(p, 0) + 1
        seg = [s for s in urlparse(u).path.split("/") if s]
        handle = seg[0].lower().lstrip("@") if seg and seg[0].lower() not in _SKIP else ""
        if handle in KNOWN_HANDLES and KNOWN_HANDLES[handle] not in known:
            known.append(KNOWN_HANDLES[handle])
    return {"posts": n, "platforms": plats, "established_accounts": known} if n else None


# ---------------------------------------------------------------- wording. Hindi and Telugu are NOT NATIVE-REVIEWED.
REPORTED_TEXT = {
    "en": {"alerts_title": "Recent official alerts (NDMA)", "alerts_open": "Open the alert", "alerts_note": "Alerts issued in the last 24 hours through the National Disaster Management Authority's system for a place named in your message. Many last only a few hours, so check the time. They are shown for reference and are not a verdict on the message.",
           "fc_title": "A published fact-check of this claim", "fc_note": "Found by matching the words of your message, not checked by Sach. Open it to read what the fact-checker found.",
           "reported": "REPORTED by news outlets", "denied": "News outlets report this is NOT true", "conflicting": "News outlets disagree",
           "single_report": "One news outlet reports on this", "no_reliable_report": "NO RELIABLE REPORT found",
           "note": "This is what news organisations report. It is not an official confirmation, and news reports can be wrong.",
           "none_note": "Sach searched established news organisations and found no report of this. The death of a public figure is normally reported within hours. This is not proof that it is false: the search is limited.",
           "answer": "ANSWER", "source": "Source", "dates_title": "Official dates",
           "social_title": "Posts on social media", "social_found": "Public posts found", "social_known": "From established accounts",
           "social_note": "Sach could not read these posts, so they are not evidence. Many posts do not make a claim true: false claims also spread through many genuine accounts."},
    "hi": {"alerts_title": "हाल की आधिकारिक चेतावनियाँ (NDMA)", "alerts_open": "चेतावनी खोलें", "alerts_note": "पिछले 24 घंटों में राष्ट्रीय आपदा प्रबंधन प्राधिकरण की प्रणाली से जारी चेतावनियाँ, जिनमें आपके संदेश की किसी जगह का नाम है। कई चेतावनियाँ कुछ ही घंटों की होती हैं, इसलिए समय देखें। ये संदर्भ के लिए हैं, संदेश पर फ़ैसला नहीं।",
           "fc_title": "इस दावे का प्रकाशित फ़ैक्ट-चेक", "fc_note": "आपके संदेश के शब्द मिलाकर खोजा गया है, Sach ने इसे जाँचा नहीं है। फ़ैक्ट-चेकर ने क्या पाया, यह जानने के लिए इसे खोलें।",
           "reported": "समाचार संस्थानों ने यह खबर दी है", "denied": "समाचार संस्थानों के अनुसार यह सच नहीं है", "conflicting": "समाचार संस्थानों की खबरें अलग-अलग हैं",
           "single_report": "एक समाचार संस्थान ने इस पर खबर दी है", "no_reliable_report": "कोई भरोसेमंद खबर नहीं मिली",
           "note": "यह समाचार संस्थानों की खबर है। यह आधिकारिक पुष्टि नहीं है, और खबरें गलत भी हो सकती हैं।",
           "none_note": "Sach ने स्थापित समाचार संस्थानों में खोजा और इसकी कोई खबर नहीं मिली। ऐसी असली घटना की खबर आम तौर पर कुछ घंटों में आ जाती है। यह इस बात का सबूत नहीं है कि दावा झूठ है।",
           "answer": "उत्तर", "source": "स्रोत", "dates_title": "आधिकारिक तारीखें",
           "social_title": "सोशल मीडिया पर पोस्ट", "social_found": "मिली सार्वजनिक पोस्ट", "social_known": "स्थापित खातों से",
           "social_note": "Sach ये पोस्ट पढ़ नहीं सका, इसलिए ये सबूत नहीं हैं। बहुत सी पोस्ट होने से कोई दावा सच नहीं हो जाता।"},
    "te": {"alerts_title": "ఇటీవలి అధికారిక హెచ్చరికలు (NDMA)", "alerts_open": "హెచ్చరికను తెరవండి", "alerts_note": "గత 24 గంటల్లో జాతీయ విపత్తు నిర్వహణ సంస్థ వ్యవస్థ ద్వారా జారీ అయిన హెచ్చరికలు, మీ సందేశంలోని ఒక ప్రాంతం పేరు వీటిలో ఉంది. చాలా హెచ్చరికలు కొన్ని గంటలే వర్తిస్తాయి, కాబట్టి సమయం చూడండి. ఇవి సూచన కోసం మాత్రమే, సందేశంపై తీర్పు కాదు.",
           "fc_title": "ఈ ప్రకటనపై ప్రచురిత ఫ్యాక్ట్-చెక్", "fc_note": "మీ సందేశంలోని పదాల పోలిక ఆధారంగా దొరికింది, Sach దీన్ని తనిఖీ చేయలేదు. ఫ్యాక్ట్-చెకర్ ఏమి కనుగొన్నారో తెలుసుకోవడానికి దీన్ని తెరవండి.",
           "reported": "వార్తా సంస్థలు ఈ వార్తను ప్రచురించాయి", "denied": "వార్తా సంస్థల ప్రకారం ఇది నిజం కాదు", "conflicting": "వార్తా సంస్థల కథనాలు వేర్వేరుగా ఉన్నాయి",
           "single_report": "ఒక వార్తా సంస్థ దీనిపై కథనం ఇచ్చింది", "no_reliable_report": "నమ్మదగిన వార్త ఏదీ దొరకలేదు",
           "note": "ఇది వార్తా సంస్థల కథనం. ఇది అధికారిక ధృవీకరణ కాదు, వార్తలు తప్పు కూడా కావచ్చు.",
           "none_note": "Sach ప్రముఖ వార్తా సంస్థలలో వెతికింది, దీని గురించి ఏ వార్తా దొరకలేదు. ఇలాంటి నిజమైన సంఘటన సాధారణంగా కొన్ని గంటల్లోనే వార్తల్లో వస్తుంది. ఇది అబద్ధం అనడానికి ఇది రుజువు కాదు.",
           "answer": "సమాధానం", "source": "మూలం", "dates_title": "అధికారిక తేదీలు",
           "social_title": "సోషల్ మీడియాలో పోస్టులు", "social_found": "దొరికిన పబ్లిక్ పోస్టులు", "social_known": "ప్రముఖ ఖాతాల నుండి",
           "social_note": "Sach ఈ పోస్టులను చదవలేకపోయింది, కాబట్టి ఇవి సాక్ష్యం కావు. చాలా పోస్టులు ఉన్నంత మాత్రాన ఒక ప్రకటన నిజం కాదు."},
}


def _t(lang: str) -> dict:
    return REPORTED_TEXT.get(lang) or REPORTED_TEXT["en"]


def _reported(res: dict) -> dict | None:
    """The first claim's news finding, only under a complete live UNVERIFIED result."""
    if res.get("verdict") != UNVERIFIED or res.get("no_claims") or res.get("layer") != "live":
        return None
    return next(((c.get("trace") or {}).get("reported") for c in res.get("claims") or [] if (c.get("trace") or {}).get("reported")), None)


def card_line(results, lang: str) -> str:
    """One line for the shareable card when the news tier found something. `results`: the ClaimVerdict list."""
    rep = next((v.trace.get("reported") for v in results if isinstance(getattr(v, "trace", None), dict) and v.trace.get("reported")), None)
    if not rep:
        return ""
    t, names = _t(lang), ", ".join(dict.fromkeys(o["source"] for o in rep.get("outlets", [])))
    return "📰 " + t[rep["status"]] + (f": {names}" if names else "")


def answer_card(facts: list, lang: str) -> str:
    from .refstore import fmt_date
    t = _t(lang)
    lines = [f"ℹ️ {t['answer']}"] + [f"{f['name']}: {fmt_date(f['date'])}" + (f" ({f['note']})" if f.get("note") else "") for f in facts]
    src = dict.fromkeys((f["source"], f["url"]) for f in facts)
    return "\n".join(lines + [f"{t['source']}: {n} - {u}" for n, u in src])


def _facts_html(facts: list, lang: str) -> str:
    from .honesty import _e
    from .refstore import fmt_date
    rows = "".join(f'<li style="margin:0 0 8px"><b>{_e(f["name"])}</b>: {_e(fmt_date(f["date"]))}'
                   + (f'<br><span class="note">{_e(f["note"])}</span>' if f.get("note") else "")
                   + f'<br><span class="note">{_e(_t(lang)["source"])}: <a href="{_e(f["url"])}" rel="noopener" target="_blank">{_e(f["source"])}</a></span></li>'
                   for f in facts if str(f.get("url", "")).startswith("https://"))
    return f'<ul style="margin:0;padding-left:18px">{rows}</ul>' if rows else ""


def answer_block(res: dict) -> str:
    """The whole result area for a question answered from the reference store. Not a verdict."""
    from .honesty import _e
    lang = res.get("language", "en")
    return (f'<div class="result" id="result"><div><div class="stamp big UNVERIFIED">{_e(_t(lang)["answer"])}</div></div>'
            f'<div><p class="kicker">{_e(_t(lang)["dates_title"])}</p>{_facts_html(res.get("answer") or [], lang)}'
            f'<p class="note" style="margin-top:14px">This is an answer from an official document, not a fact-check verdict.</p></div></div>')


def panels_html(res: dict) -> str:
    """Never raises: a stored result with malformed values simply shows no extra panels."""
    try:
        return _panels_html(res)
    except Exception:
        return ""


def _panels_html(res: dict) -> str:
    """Extra panels under a result: official dates named in the text, what news organisations report, and the social-media signal."""
    from .honesty import _e, _NEUTRAL
    lang, t, out = res.get("language", "en"), _t(res.get("language", "en")), ""
    if res.get("reference") and not res.get("answer"):
        out += (f'<section class="ref-dates" style="{_NEUTRAL}"><p style="margin:0 0 8px"><b>{_e(t["dates_title"])}</b></p>'
                f'{_facts_html(res["reference"], lang)}</section>')
    rep = _reported(res)
    if rep:
        items = "".join(f'<li style="margin:0 0 6px"><a href="{_e(o["url"])}" rel="noopener" target="_blank"><b>{_e(o["source"])}</b></a> '
                        f'<span class="note">{_e(o.get("says", ""))}</span></li>' for o in rep.get("outlets", []) if isinstance(o, dict) and str(o.get("url", "")).startswith("https://"))
        note = t["none_note"] if rep["status"] == "no_reliable_report" else t["note"]
        out += (f'<section class="reported" style="{_NEUTRAL}"><p style="margin:0 0 6px"><b>📰 {_e(t[rep["status"]])}</b></p>'
                f'<p class="note" style="margin:0 0 10px">{_e(note)}</p>' + (f'<ul style="margin:0;padding-left:18px">{items}</ul>' if items else "") + '</section>')
    if res.get("verdict") == UNVERIFIED and res.get("layer") == "live":
        import time as _time
        ad = res.get("alerts") if isinstance(res.get("alerts"), dict) else {}
        fresh = isinstance(ad.get("at"), (int, float)) and 0 <= _time.time() - ad["at"] < 3 * 3600     # never an old alert from a cached or shared result
        al = [a for a in (ad.get("items") or []) if isinstance(a, dict) and str(a.get("url", "")).startswith("https://sachet.ndma.gov.in/")] if fresh else []
        if al:
            items = "".join(f'<li style="margin:0 0 8px">{_e(a.get("title", ""))} <span class="note">{_e(a.get("published", ""))}</span> '
                            f'<a href="{_e(a["url"])}" rel="noopener" target="_blank">{_e(t["alerts_open"])}</a></li>' for a in al[:3])
            out += (f'<section class="alerts" style="{_NEUTRAL}"><p style="margin:0 0 6px"><b>{_e(t["alerts_title"])}</b></p>'
                    f'<p class="note" style="margin:0 0 10px">{_e(t["alerts_note"])}</p><ul style="margin:0;padding-left:18px">{items}</ul></section>')
        fc = [f for f in res.get("related_factchecks") or [] if isinstance(f, dict) and str(f.get("url", "")).startswith("https://")]
        if fc:                                          # no rating words here: a FALSE beside Sach's UNVERIFIED would read as a verdict
            items = "".join(f'<li style="margin:0 0 8px"><a href="{_e(f["url"])}" rel="noopener" target="_blank"><b>{_e(f.get("publisher", ""))}</b></a>: '
                            f'“{_e(f.get("claim", ""))}”' + (f' <span class="note">{_e(f["date"])}</span>' if f.get("date") else "") + '</li>' for f in fc[:3])
            out += (f'<section class="related-fc" style="{_NEUTRAL}"><p style="margin:0 0 6px"><b>{_e(t["fc_title"])}</b></p>'
                    f'<p class="note" style="margin:0 0 10px">{_e(t["fc_note"])}</p><ul style="margin:0;padding-left:18px">{items}</ul></section>')
    soc = next(((c.get("trace") or {}).get("social") for c in res.get("claims") or [] if (c.get("trace") or {}).get("social")), None)
    if soc and res.get("verdict") == UNVERIFIED:
        plats = ", ".join(f"{_e(k)} {int(v)}" for k, v in (soc.get("platforms") or {}).items())
        known = ", ".join(_e(x) for x in soc.get("established_accounts") or [])
        out += (f'<section class="social-signal" style="{_NEUTRAL}"><p style="margin:0 0 6px"><b>{_e(t["social_title"])}</b></p>'
                f'<p style="margin:0 0 6px">{_e(t["social_found"])}: {plats}' + (f'<br>{_e(t["social_known"])}: {known}' if known else "") + '</p>'
                f'<p class="note" style="margin:0">{_e(t["social_note"])}</p></section>')
    return out
