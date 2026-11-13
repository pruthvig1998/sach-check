# Short, truthful demo

Start a local instance with Python 3.13 after installing `requirements-dev.txt`:

```sh
python -m sach.web
```

Open `http://localhost:8080`. With no provider credentials, explain that the app is in limited mode; do not present it as the full live configuration. Use synthetic/public example claims only because the current app can store claim text in a public ledger and shared-report cache.

## 90-second test path

1. Paste: “Government is giving Rs 1000 to everyone under Corona Sahayata Yojana, click the link to register.” Read the returned layer and citation. If it matches an archived published fact-check, say whose review it is; do not narrate an invented live investigation.
2. Open the trace and source. Explain that the final live verdict uses deterministic policy gates and that a source title is not the same thing as the deciding quoted sentence. The proposed source-sentence feature is not shipped by this patch.
3. Paste: “Every household in India will receive a free solar-powered refrigerator next month.” Show the actual result; the expected safe behavior is UNVERIFIED. Explain that absence of evidence is not proof of falsity. If providers are unavailable, describe that limitation explicitly.
4. Show the existing share preview, without sending it to anyone. Check that uncertainty and source attribution survive sharing.

These are demo inputs, not newly measured live benchmark outcomes. Network conditions and current source content can change results.

## Extend to 2–3 minutes

- Upload a synthetic screenshot and demonstrate editing OCR text before checking, especially amounts and negations.
- Open the impact page. Explain that checks can include repeats/test traffic; they are not unique people or measured improvements. An incomplete legacy benchmark should show as unavailable.
- Explain the next improvements: exact cited source sentences, source freshness, deliberate private sharing and optional feedback after privacy work. Do not demonstrate a proposed feature as implemented.
- End with the actual evidence: deterministic test results in `EVIDENCE.md`, separately labelled offline fixtures, and the missing live benchmark/pilot/eligibility artifacts.

Before an event, rehearse against the intended deployed revision. HTTP 200 alone is not an end-to-end demo test. Do not deploy unreviewed changes just to make this script match a deadline.
