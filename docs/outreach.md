# Owner actions: switches, keys and outreach

Things only the owner can do. Drafts are ready to send; fill the square brackets. Nothing here has been sent.

## 0. Switch the news tier on (2 minutes)

The code is deployed but off. Run from the project folder, then check one claim on the site.

```bash
printf '1' | vercel env add SACH_NEWS_TIER production
```

A new environment variable applies from the next production deploy: the next push to main picks it up, or press Redeploy on the latest production deployment in the Vercel dashboard.

Optional, costs one more search per unverified claim:

```bash
printf '1' | vercel env add SACH_SOCIAL_SIGNAL production
```

To switch either off again: `vercel env rm SACH_NEWS_TIER production`, then deploy again the same way.

## 1. Free keys to create

| Key | Where | What it unlocks |
|---|---|---|
| data.gov.in API key | sign in at data.gov.in, "My Account" | government datasets with an API (statistics, schemes by ministry) |
| Data Commons API key | apikeys.datacommons.org | census, RBI and health statistics as a graph |
| IMD API access | request through api.imd.gov.in; it appears to need your server's IP address | district weather warnings and nowcasts (the NDMA alert feed already covers alerts) |

Give each key to Sach as a Vercel environment variable yourself; do not paste keys into chat.

## 2. PB-SHABD (Prasar Bharati's free news feed)

- Register at `shabd.prasarbharati.org/register`. Reported as free for registered media organisations until March 2027.
- Print outlets need an RNI certificate, broadcasters need uplink papers. A digital news portal fills a form and is verified by Prasar Bharati.
- Sach is a fact-checking tool, not a registered news outlet, so it may not qualify by itself. Two routes: apply as a digital portal and state the public-interest use plainly, or partner with a registered publisher who already has access.
- Before using any content, read the terms shown after registration. This note does not assume what they allow.

## 3. Email drafts

### To PIB Fact Check (a machine-readable feed of debunks)
Subject: Request for a machine-readable feed of PIB Fact Check debunks

Dear PIB Fact Check team,

I run Sach (sachcheck.in), a free, open-source tool that lets people in India check a WhatsApp forward before passing it on. When a forward matches one of your published fact-checks, Sach shows your verdict with your name and a link to your post. It never presents your finding as its own.

Today Sach collects your debunks from your public posts, which is slow and misses some. Would you be able to offer a feed (RSS, JSON or a spreadsheet) of your fact-checks with the claim, your finding, the date and the link? That would let more people reach your work at the moment they are about to forward a false message.

The code is public at github.com/pruthvig1998/sach-check. I would be glad to show how your fact-checks are displayed.

With thanks,
[Name]
[Contact]

### To a fact-checking organisation (Factly, NewsMeter)
Subject: Sach: showing your fact-checks to people before they forward

Dear [Name],

I run Sach (sachcheck.in), a free, open-source checker for WhatsApp forwards in English, Hindi, Telugu and other Indian languages. When a pasted forward matches a published fact-check, Sach shows the checker's own verdict, name and link. When nothing is found, it says UNVERIFIED and points people to fact-checkers' tiplines, including yours.

I would like to ask two things. First, may Sach index your published ClaimReview data (claim, rating, link) to show your fact-checks, always attributed and linked? Second, would your team be open to reviewing the claims that many Sach users ask about and that have no published fact-check yet? Sach can send you a short list of such claims, with no personal data.

No money is involved on either side. The project is MIT-licensed and makes no accuracy claims it cannot show.

With thanks,
[Name]
[Contact]

### To a state fact-check unit or state police social media cell
Subject: A feed of your rumour debunks for a public fact-checking tool

Dear [Unit],

Sach (sachcheck.in) is a free tool for checking WhatsApp forwards before they are shared. Most rumours people check are local: a state scheme, a school closure, a kidnapping scare. Your unit's debunks are the best answer to those, but they reach people only if they follow your account.

Could you share your debunks in a form a tool can read (a web page list, RSS or a spreadsheet with the claim, your finding, date and link)? Sach would show your finding under your name with a link to your post.

With thanks,
[Name]
[Contact]

## 4. Other routes

- **RTI requests** for datasets that exist but are not published (for example a ministry's list of scheme notifications).
- **A journalism or library partner** at a university for native-language review and for typing in state holiday orders and local notifications that exist only as scanned pages.
- **A wire agency pilot rate** (PTI, ANI) once there is real usage to show. Paid, so outside the present "free sources only" decision.
