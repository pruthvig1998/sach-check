# Sach on Telegram (free)

People forward a message to your Telegram bot and get Sach's cited verdict card back in the same chat. Telegram's Bot API is free, so this costs $0.

## 1. Create the bot (2 minutes)
1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a display name, then a username ending in `bot` (for example `SachCheckBot`).
3. BotFather replies with a **token** that looks like `123456789:AAH...`. Treat it like a password. Do not paste it in chat, email or GitHub.
4. Optional: send `/setdescription` and `/setabouttext` to BotFather to describe the bot. Do not turn off group privacy: it keeps the bot quiet in groups unless someone addresses it.

## 2. Put the two secrets into Vercel
Copy the token from BotFather (select it, Cmd+C), then in Terminal:

```
cd ~/Downloads/sach-check && pbpaste | tr -d '[:space:]' | vercel env add TELEGRAM_BOT_TOKEN production
```

Now make a random webhook secret (this is just a password Telegram will send back so we know calls really come from Telegram). Copy it to the clipboard and store it:

```
openssl rand -hex 24 | tee /dev/stderr | pbcopy
cd ~/Downloads/sach-check && pbpaste | tr -d '[:space:]' | vercel env add TELEGRAM_WEBHOOK_SECRET production
```

Optional (lets people mention the bot in groups): `printf 'SachCheckBot' | vercel env add TELEGRAM_BOT_USERNAME production` (your username, without the @).

## 3. Redeploy
```
cd ~/Downloads/sach-check && vercel --prod
```
Until both variables exist the endpoint answers 503 and the bot does nothing.

## 4. Connect Telegram to Sach
The script needs the same two values locally. Put them in `.env` (it is git-ignored) as `TELEGRAM_BOT_TOKEN=...` and `TELEGRAM_WEBHOOK_SECRET=...`, then:

```
cd ~/Downloads/sach-check && .venv/bin/python scripts/set_telegram_webhook.py
```
The site address it points Telegram at is `SACH_SITE_URL` (for example your custom domain), or pass `--url https://your-site.example`; unset, it uses the built-in default (currently `https://sach-check-lilac.vercel.app`). It prints `OK: webhook set`. Check with `--info` (the token is never printed).

## 5. Test
Open your bot in Telegram, press Start, then forward a message. You should see "typing...", then the verdict card with links. Try `/lang hi`.

## Turning it off
`.venv/bin/python scripts/set_telegram_webhook.py --delete` stops Telegram sending messages. To disable fully, also run `vercel env rm TELEGRAM_WEBHOOK_SECRET production` and redeploy (the route then answers 503).

## How it behaves
- **Private chats:** every text message is checked. **Groups:** only `/check <text>`, `/check` as a reply to a message, a reply to the bot, or an @mention. Other bots' messages are ignored.
- **Limits:** 6 checks per minute per chat (one polite "slow down" message). Messages over 4,000 characters are refused with a friendly note. Photos, stickers and voice notes get "I can only read text for now".
- **Replies are plain text** (no Markdown/HTML), so a hostile forward can never inject formatting or links. Link previews are off. Long replies are split on line boundaries under Telegram's 4096-character limit.
- **Slow checks: done inline, not in a background thread.** A check takes 10 to 30 seconds. On Vercel a function is frozen as soon as it returns its response, so a background thread could be killed before it sends the answer. So the webhook sends "typing...", runs the check (the pipeline has its own 48 s budget, Vercel allows 60 s), sends the reply, then answers 200. If Telegram retries a slow call, the `update_id` is remembered for an hour and the repeat is ignored. Any error returns 200 (so Telegram never retries forever) after a short apology.

## Privacy
What the bot stores: a language preference per chat id (`tg:lang:<chat_id>`, up to a year) and each handled update id for one hour (`tg:seen:<id>`), in the same store the site uses. Claims are recorded in the public evidence ledger exactly like website checks (claim text, verdict, sources, language, date). It never stores your name, username, phone number, the full message or the chat history, and the bot token never appears in logs or replies.
