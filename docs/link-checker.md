# Link checker: check a link, number, UPI ID or app before you trust it

Code: `sach/linkcheck.py`. Data: `data/official_brands.json`. Tests: `tests/test_linkcheck.py`. No AI/LLM calls anywhere. Costs nothing to run.

## What it claims, and what it does not

For each link, UPI ID, phone number or app mention in pasted text, Sach gives one of four answers:

| Answer | Meaning | Colour and shape |
|---|---|---|
| `OFFICIAL` "On the verified official list" | The host is on `sach/fetch.py`'s official list or in `data/official_brands.json` | green, check mark |
| `LOOKALIKE` "Imitates <brand>" | A concrete rule (below) fired. The card names the rule and the real address | red, cross |
| `SUSPICIOUS_PATTERN` "Looks like a scam pattern" | A recognised scam pattern (see below) | amber, exclamation mark |
| `UNKNOWN` "Not on the official list: Sach cannot vouch for it" | Everything else. This is the default | grey, question mark |

**Sach never says an address, number or app is safe.** It can prove an address is on its list, that it imitates one, or that it matches a pattern. For everything else it says it cannot vouch for it and shows how to check. Tests scan every rendered output for the words safe, secure, legitimate, trusted and genuine on items that are not on the official list (the one allowed phrase is the product name "Google Safe Browsing").

A false "imitates X" is as bad as a false FALSE verdict, so LOOKALIKE needs concrete, explainable evidence, and a guard list of 60+ ordinary domains (google.com, sbicard.com, hdfclife.com, paytm.com, amazon.com.au, news sites ...) is tested to never be flagged.

It never fetches the page you paste. Lookups use the hostname only (RDAP registration data, optional Safe Browsing). The single guarded exception is the "Show where this short link goes" button (below).

## LOOKALIKE rules (all in `_lookalike_rules`)

| Rule id | Fires when | Example | Near-miss that does not fire |
|---|---|---|---|
| `official_prefix` | An official domain appears at the start or middle of a different address | `sbi.co.in.verify-now.xyz`, `pib.gov.in.evil.com` | `online.sbi.co.in` (a true subdomain), `amazon.com.au` (Amazon's own country site) |
| `brand_plus_scam_word` | A brand word plus a scam word (kyc update verify login claim register offer bonus refund reward lucky gift prize cashback free yojana helpline support customer care apply status link) in a name that is not the brand's | `sbi-kyc-update.com`, `pm-kisan-yojana-registration.in` | `sbicard.com`, `hdfclife.com` (listed), `sbi-news.in` (no scam word), `kyc-help-center.in` (no brand) |
| `typosquat_lookalike_chars` | After folding look-alike characters (rn to m, vv to w, 0 to o, 1 to l or i, 5 to s, Cyrillic and Greek letters via NFKC and a confusables table) the name equals an official name | `paytrn.com`, `раytm.com` (Cyrillic) | `paytm.com` itself, `paytm.in` (same name, other ending: not flagged) |
| `typosquat_hyphen_digit` | The name is an official name plus hyphens or digits | `pay-tm.com`, `paytm1.com` | `axis360.com` (official name is 4 letters: too short to compare) |
| `typosquat_edit_distance` | One letter away from an official name (two for names of 8+ letters); 5-letter names only for an added or dropped letter | `paytmm.com`, `flipcart.com`, `airtell.in` | `kodak.com` (one letter from `kotak`, but `kotak` is a 5-letter ordinary word and is not compared), `amazing.com` |
| `userinfo_trick` | `https://pib.gov.in@evil.com/`: text before the @ looks like an address | `https://pib.gov.in@evil.com/` | `https://user@example.com/` |
| `punycode_brand` | An internationalised name (`xn--...`) that folds to a brand word | `раytm.com` | `münchen.de`, `भारत.in` |

IP-address hosts, `javascript:` and `data:` links, and names that mix alphabets are `SUSPICIOUS_PATTERN`, because they are concrete red flags but do not name a brand.

## SUSPICIOUS_PATTERN

A shortener (bit.ly, tinyurl.com, t.co, cutt.ly, rb.gy, is.gd, goo.gl, ow.ly, shorturl.at ...) or an unusual ending (.xyz .top .click .site .shop .live .vip ...) **together with money or government words** in the pasted text; any `.apk` link (even on an official host: Sach flags every app-file link); a bare IP address; a domain registered under 30 days ago beside any of those signs; a UPI ID in a message that matches the "pay or approve to receive money" trick; a Google Safe Browsing match. A bare shortener with no money or government context stays `UNKNOWN` with a note.

## Verified brand data (`data/official_brands.json`)

Single source of truth for "official" and for look-alike comparison. 30 brands with 53 listed domains (66 official domains once the extra bodies from `sach/fetch.py` are included), plus every host and suffix in `sach/fetch.py` (`.gov.in`, `.nic.in`, `.bank.in` subdomains, `who.int` and the extra list). Each domain records its evidence URL and how it was confirmed (the brand's own site redirecting or linking it, or a regulator or government page linking it) and the date checked (2026-11-13). Some entries are own-site evidence only; the `how` field says so.

### How to add a brand or domain

1. Find an official page that confirms the domain: the brand's own site (an old domain that redirects to the new one counts), or a regulator or government page that links it. Do not add from memory.
2. Add the domain under an existing brand, or add a brand with `brand`, `short`, `tokens` (the words people use for it; short tokens of 3 letters or fewer match only as a whole word), `kind` and `domains: [{"d", "evidence", "how", "body"?}]`.
3. `body` is only needed when the company differs from the brand name (for example SBI Life under SBI).
4. Record the date in `checked`, run `pytest tests/test_linkcheck.py`, and add the domain to the false-positive list if it is a name that could look like a typo of another.

### Dropped (could not be confirmed on 2026-11-13)

`unionbankofindia.co.in` (certificate hostname mismatch / timeout), `bhimupi.org.in` (certificate did not verify; BHIM is covered by `npci.org.in`), `icicilombard.com` (not checked against an official page), `yesbank.bank.in` (does not exist). They are listed in the file's `dropped` array.

## Phone numbers and UPI IDs

* A number is shown as official only if it is in the `phones` array with an evidence URL: PIB Fact Check WhatsApp +91 87997 11259 (factcheck.pib.gov.in), 1930 cyber-crime helpline, 112, 181, 1909 (TRAI DND), 14422 and 1800 110 420 (Sanchar Saathi, sancharsaathi.gov.in), 1947 (UIDAI, uidai.gov.in), 1800 103 0025 (Income Tax, incometax.gov.in). Everything else: "Sach cannot verify who owns a phone number", with 1930, cybercrime.gov.in and Chakshu at sancharsaathi.gov.in.
* UPI IDs: format is validated and the handle is shown as written. Sach does **not** map handles to banks: NPCI's public pages (checked 2026-11-13) list live members but not a readable handle table. `KNOWN_HANDLES` is empty on purpose; add one only with an NPCI or bank evidence URL. Every UPI ID card shows the hard rules: you never need a PIN or a collect request to receive money; never pay a "processing fee" or "send Rs 1".

## Optional lookups

* **RDAP domain age.** The IANA bootstrap (`https://data.iana.org/rdap/dns.json`) maps the ending to its RDAP server; a small fallback table (`.in`, `.com`, `.net`) is used if the bootstrap fails. The `registration` event gives the age; cached per registrable domain for 7 days via `sach/store.py`; 3 second timeout; at most 5 hostnames per request. Any failure means no information (never "old", never "safe"). Under 30 days adds a high-risk note, 30 to 180 days a caution note. This sends the hostname (not the page, not the message) to the registry's RDAP server.
* **Google Safe Browsing.** If `GOOGLE_SAFEBROWSING_API_KEY` is set, the hostname is checked with the Lookup API v4 `threatMatches:find` (https://developers.google.com/safe-browsing/v4/lookup-api). Google's overview (https://developers.google.com/safe-browsing) says the Safe Browsing API is for **non-commercial use only** (commercial users are pointed to Web Risk), so leave the key unset if that does not fit. A match adds "Google Safe Browsing lists this address as dangerous". No key or any error means no information; the key is never printed. Because only the hostname is sent, a match is a bonus signal, not a clean bill of health.
* **Short-link expansion** (`POST /?api=linkexpand`, 6 per minute per IP). Only for hosts on the shortener list. Each hop: http or https only, no credentials, ports 80/443 only, every resolved address must be a public address (loopback, private, link-local including 169.254.169.254, CGNAT, multicast, reserved, and IPv6 forms that embed IPv4 are blocked), and the connection goes to the address that was checked, so DNS rebinding cannot swap it. HEAD first, then a ranged GET (`Range: bytes=0-0`); no body is ever read; no cookies; honest User-Agent; 3 second total; at most 3 redirects. It only follows a redirect to another listed shortener: the final destination is reported and analysed by name but **never contacted**.

## Limits

* No page scanning: Sach cannot tell whether a page asks for an OTP. It judges names, not content.
* The brand list is deliberately small. A brand that is not on it can still be flagged by the generic patterns, but cannot be named.
* Typo-squat checks only compare against 5+ letter official names; `kotak` and `umang` are skipped because one-letter neighbours are ordinary words.
* RDAP and Safe Browsing are optional and may be unreachable; their absence changes nothing else.
* Hindi and Telugu strings are `# NOT NATIVE-REVIEWED`; reasons and actions are English only for now.
* Positions and shown text come from the pasted text after hidden characters are removed and defanged links (`hxxp`, `[.]`, `(dot)`) are restored.
