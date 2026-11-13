"""Terms, Privacy, Refund and Contact pages (needed for payment-gateway activation; also just good practice).

Plain-language, written to match what the code actually does. The operator can edit the wording below.
Contact email is optional: set SACH_CONTACT_EMAIL to show it; otherwise people are pointed to GitHub issues.
"""
from __future__ import annotations
import os, re
from .site import layout, esc, REPO

UPDATED = "12 November 2026"
PAGES = ("terms", "privacy", "refund", "contact")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")

def contact_email() -> str | None:
    e = (os.environ.get("SACH_CONTACT_EMAIL") or "").strip()
    return e if _EMAIL.match(e) else None

def _contact_line() -> str:
    e = contact_email()
    issues = f'<a href="{esc(REPO)}/issues" rel="noopener">open an issue on GitHub</a>'
    return (f'email <a href="mailto:{esc(e)}">{esc(e)}</a> or {issues}') if e else issues

_TERMS = lambda: f"""
<h3>What Sach is</h3>
<p>Sach is a free, open-source tool that checks viral messages against official sources (mainly PIB and government websites) and returns a verdict with citations. It is run by an individual developer in India as a public-interest project. It is <b>not</b> a government service and does not speak for any official body.</p>
<h3>Using Sach</h3>
<ul><li>Sach gives information, not legal, medical or financial advice. A verdict of <b>UNVERIFIED</b> means Sach could not find an official source either way. It is not a claim that the message is false.</li>
<li>Verdicts can be wrong or out of date. Check the cited sources before you act or forward anything.</li>
<li>Don't use Sach to harass people, to flood it with automated requests, or to break the law. We may rate-limit or block abusive use.</li>
<li>The software is open source under the MIT licence (see the source code link). The service itself is provided "as is", without warranties, and may change or stop at any time.</li></ul>
<h3>Tips</h3>
<p>Tips are <b>optional, voluntary gifts</b> that help cover running costs. They don't buy anything and <b>never affect a verdict</b>. See the <a href="/?view=refund">Refund policy</a> for mistaken or duplicate payments.</p>
<h3>Liability</h3>
<p>To the extent the law allows, the operator is not liable for loss arising from using or relying on Sach. Nothing here limits rights you have under Indian consumer law that cannot be waived. These terms are governed by the laws of India.</p>
<h3>Questions</h3><p>{_contact_line()}.</p>
<p class="note">Last updated {UPDATED}.</p>"""

_PRIVACY = lambda: f"""
<h3>The short version</h3>
<p>Sach doesn't have accounts, doesn't ask for your name, and doesn't sell data. Here is exactly what happens to what you paste or pay.</p>
<h3>When you check a forward</h3>
<ul><li>Your text is split into separate claims. Each claim is sent to search sources and to AI language-model providers (currently Google Gemini, with fallbacks to other providers) so they can compare it with official pages. Don't paste anything private, like personal details or one-time passwords.</li>
<li>If you upload a screenshot, the image is sent to Google's Gemini service to read its text. Sach does not store the image or the text it reads.</li>
<li>A share link shows the checked message and Sach's result to anyone who has the link; it expires when the stored result expires (7 days for TRUE/FALSE/MISLEADING, 6 hours for UNVERIFIED); links are not indexed by search engines.</li>
<li>If you share an image into Sach, it is sent to Google's Gemini to read the text, and it is not stored.</li>
<li>For each checked claim Sach keeps a <b>public record</b> in the <a href="/?view=ledger">evidence ledger</a>: the claim text, its verdict, the sources cited, the language and the date. The full original message, your name, your phone number and your IP address are <b>not</b> stored in that record.</li>
<li><b>On your device only:</b> "My checks" keeps your last 20 checks (the claim, its verdict and the date) in your browser's local storage. It never leaves your device, and you can clear it from the page. Sach's service worker saves only the public home page, the icons and the app manifest for offline use, never your text or results.</li>
<li>Links, numbers and UPI IDs you check are looked up by their hostname only; Sach does not open the page, and does not store what you paste.</li>
<li>To limit abuse, the server briefly remembers your IP address in memory to count requests per minute. The hosting provider (Vercel) may also keep standard server logs.</li></ul>
<h3>When you tip</h3>
<ul><li><b>Card / UPI checkout:</b> payment is handled by <b>Razorpay</b>. Razorpay collects the details needed to process the payment and may show the operator your name, contact and payment method in its dashboard. Sach itself never sees or stores your card, UPI or bank details. Razorpay's own privacy policy applies to that data.</li>
<li><b>UPI QR code:</b> the payment goes directly between your UPI app and the operator's bank account. Sach doesn't see it.</li>
<li>Sach doesn't link tips to the claims you checked.</li></ul>
<h3>Visit statistics</h3>
<p>Sach uses Vercel Web Analytics to count page views. It does not use cookies and does not identify you; it does not see what you paste into the checker.</p>
<h3>Cookies</h3>
<p>Sach doesn't set tracking cookies. Your browser may store your light/dark preference locally. Razorpay's checkout window, when opened, may set its own cookies.</p>
<h3>Your choices</h3>
<p>You can use Sach without tipping. To ask about data tied to a payment, contact Razorpay or {_contact_line()}. The public ledger holds claim text only. If a claim in it contains personal information, tell us and we'll remove it.</p>
<p class="note">Last updated {UPDATED}.</p>"""

_REFUND = lambda: f"""
<h3>Tips are voluntary</h3>
<p>Tips are gifts to support Sach, so they are normally <b>not refundable</b>.</p>
<h3>Mistakes we will fix</h3>
<p>If you were charged twice, charged the wrong amount, or the payment went through by accident, tell us <b>within 7 days</b> and we'll refund it in full. Please include the payment date, amount and the payment ID shown on your Razorpay receipt or bank message.</p>
<h3>How refunds are paid</h3>
<p>Refunds go back to the original payment method through Razorpay and usually reach your account in <b>5 to 7 business days</b>, depending on your bank. If a payment failed but money left your account, the bank or Razorpay normally reverses it automatically within a few days.</p>
<h3>Ask for a refund</h3><p>{_contact_line()}.</p>
<p class="note">Last updated {UPDATED}.</p>"""

_CONTACT = lambda: f"""
<p>Sach is run by one person, so replies can take a few days.</p>
<ul><li><b>Bugs, wrong verdicts, takedown requests:</b> <a href="{esc(REPO)}/issues" rel="noopener">GitHub issues</a>.</li>
{('<li><b>Email:</b> <a href="mailto:' + esc(contact_email()) + '">' + esc(contact_email()) + '</a></li>') if contact_email() else ''}
<li><b>Payment problems or refunds:</b> see the <a href="/?view=refund">Refund policy</a>, then contact us using the details above.</li></ul>
<p>Sach is not a government service. If you need an official answer, contact the source named in the verdict card.</p>"""

_TITLES = {"terms": "Terms of use", "privacy": "Privacy policy", "refund": "Refund policy", "contact": "Contact"}
_BODIES = {"terms": _TERMS, "privacy": _PRIVACY, "refund": _REFUND, "contact": _CONTACT}

def legal_page(slug: str) -> bytes | None:
    if slug not in PAGES:
        return None
    nav = " · ".join(f'<a href="/?view={s}"{" aria-current=page" if s == slug else ""}>{_TITLES[s]}</a>' for s in PAGES)
    body = (f'<div class="wrap"><section style="border:0;max-width:760px"><p class="kicker">Sach · {esc(_TITLES[slug])}</p><h1 class="h2">{esc(_TITLES[slug])}</h1>'
            f'<p class="note" style="margin:0 0 18px">{nav}</p>{_BODIES[slug]()}</section></div>')
    return layout(body, f"{_TITLES[slug]} — Sach", path=f"/?view={slug}")
