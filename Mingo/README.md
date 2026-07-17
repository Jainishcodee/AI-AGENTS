# Mingo

Voice-activated Microsoft Rewards helper.

Say **"Mingo"** → it opens Microsoft Edge and runs the Bing Rewards searches +
daily activity cards on your **spare** Microsoft account, then tells you the
result out loud. In the background it **emails you every 3 hours** to go do your
**main** account by hand.

---

## ⚠️ Read this first

Automating Microsoft Rewards **violates Microsoft's Terms of Service** ("no bots,
macros, scripts, or other automated means"). Accounts that do this get
**suspended and points/redemptions voided** — it does happen. That's why this is
pointed at a throwaway account on purpose.

This tool deliberately does **not** include CAPTCHA solving or
fingerprint/stealth tricks. If Bing throws a challenge, Mingo stops and says so.
Run it at your own risk.

---

## Setup (Windows)

1. **Install Python 3.10+** and **Microsoft Edge** (you have both on Win11).

2. **Install dependencies:**
   ```powershell
   cd "g:\AI AGENTS\Mingo"
   pip install -r requirements.txt
   ```
   - `PyAudio` (needed for the microphone) ships as a wheel for Python 3.8–3.12,
     so `pip` handles it. If it ever fails, grab a wheel from
     <https://www.lfd.uci.edu/~gohlke/pythonlibs/> or `pip install pipwin && pipwin install pyaudio`.
   - Mingo uses your installed Edge (`channel="msedge"`), so you don't *need*
     `playwright install`. Run it only if you'd rather use bundled Chromium.

3. **Configure:**
   ```powershell
   copy .env.example .env
   ```
   Open `.env` and set:
   - `SMTP_APP_PASSWORD` — a **Gmail App Password** (not your real password):
     <https://myaccount.google.com/apppasswords> → make one for "Mail" → paste the 16 chars.
   - (Optional) `MS_EMAIL` / `MS_PASSWORD` for the spare account — or leave them
     blank and just sign in manually the first run (recommended; nothing stored).
   - Tweak `DESKTOP_SEARCHES`, `MOBILE_SEARCHES`, `REMINDER_INTERVAL_HOURS`,
     `WAKE_WORD`, `SPEAK` to taste.

4. **Run it:**
   ```powershell
   python mingo.py
   ```
   - First time: when the Edge window opens, **sign into your spare account** and
     tick "stay signed in". Mingo waits, then continues. After that the session
     is cached in `./edge_profile/` and it won't ask again.
   - Then just say **"Mingo"** near your mic.

Quit with `Ctrl+C`.

---

## What each file does

| File | Role |
|---|---|
| `mingo.py` | Entry point. Starts the reminder thread, listens for the wake word, runs the rewards bot on wake. |
| `voice.py` | `speak()` (pyttsx3 TTS) + `listen_for_wake_word()` (SpeechRecognition). |
| `rewards_bot.py` | Playwright/Edge automation: sign-in, desktop searches, mobile-UA searches, Daily Set cards, points readout. |
| `search_terms.py` | Builds search queries from Google Trends RSS (with a fallback word list). |
| `reminder.py` | Emails you every N hours about your main account (Gmail SMTP). |
| `config.py` | Loads `.env`. |
| `.env` | Your secrets/settings (git-ignored, never uploaded). |
| `edge_profile/` | The cached Edge profile for the spare account (git-ignored). |

---

## Run pieces individually (handy for debugging)

```powershell
python rewards_bot.py     # just do one rewards run, no voice
python reminder.py        # send one reminder email now
```

---

## When it breaks

Bing's rewards page HTML changes often. The **searches are stable**; the
**activity-card clicking is best-effort** — if `rewards_bot.py` reports
"found ~0 activity links", update the CSS selectors in `_CARD_SELECTORS` /
`_QUIZ_OPTION_SELECTORS` near the top of `rewards_bot.py` (open
rewards.bing.com, inspect a card, copy the selector).

---

## Ideas / next steps

- Replace the network-based wake word with `pvporcupine` for a true offline
  always-on "Mingo" (needs a free Picovoice access key).
- Add a Windows Task Scheduler entry so the spare-account run also fires
  automatically each morning, not just on voice.
- Email the *spare* account's daily summary to yourself too.
- Add a system-tray icon as an alternative trigger.
