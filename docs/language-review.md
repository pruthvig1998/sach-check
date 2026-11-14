# Hindi and Telugu review: how to help

Sach shows its answers in English and 15 Indian languages. The Hindi and Telugu text was written by an AI model and edited by a reviewer who is
not a native speaker, so the site says it is **not native-reviewed**. We would like a native speaker of each language to check it.

**The file:** [language-review-pack.csv](language-review-pack.csv). It has one row per string the site can show: English on the left, then Hindi and
Telugu exactly as users see them. It opens in Google Sheets or Excel. Regenerate it any time with `python scripts/export_review_pack.py`.

**What to do (about 45 minutes per language):**
1. In "Hindi: OK or your correction" (or Telugu), write `OK` or the wording you would use instead.
2. Mark anything that is wrong, confusing, too formal for a family WhatsApp group, or that changes the meaning in the Notes column.
3. Pay most attention to these, because a wrong word here could mislead someone:
   - what UNVERIFIED means ("could not confirm or deny", never "probably false" or "probably true");
   - the "Limited check" notices (the check could not finish);
   - the scam and link-check advice (never share an OTP or PIN, type the official address yourself).
4. Send the file back. We will apply the changes, replace the "not native-reviewed" notes with a dated reviewer credit (only with your permission), and
   run the tests.

**What we are not asking:** you do not need to check any code or verdict logic. Nothing here changes how Sach decides; it only changes the words.

## Message you can send to a volunteer
> Hi, I built a free fact-checker for WhatsApp forwards (sachcheck.in). It replies in Hindi and Telugu, but a machine wrote those strings. Could you spend about 45 minutes reading them and marking anything that sounds wrong or unclear? Here is a spreadsheet; just write OK or your correction next to each line. Thank you.
