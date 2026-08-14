# StockSeer → Jarvis: how it all connects

Everything from "an IPO exists somewhere on NSE" to "your phone buzzes in your
pocket". Read the first two diagrams and you have the whole picture.

---

## 1. The big picture

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │                        DATA SOURCES  (all free)                      │
   │                                                                      │
   │   NSE public API          Angel One SmartAPI        Yahoo Finance    │
   │   IPO dates, prices       live ticks, candles       fallback, delayed│
   └───────────┬──────────────────────┬────────────────────────┬──────────┘
               │                      │                        │
               ▼                      ▼                        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                    STOCKSEER  (Python, on your PC)                   │
   │                                                                      │
   │   ipo/registry.py    who is listing, and when                        │
   │   ipo/calendar.py    "closes today" / "lists tomorrow"               │
   │   ipo/watcher.py     listing-morning price tracking                  │
   │            │                                                         │
   │            └──────────► notify.py  ── the alert queue ──┐            │
   │                                                         │            │
   │   web/server.py   Flask, port 8765  ◄───────────────────┘            │
   └──────────────────────────────┬───────────────────────────────────────┘
                                  │
                     HTTP  (one of three links)
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
   same wifi / LAN          Tailscale             Cloudflare Tunnel
   http://192.168.x.x       http://100.x.y.z      https://xxx.trycloudflare.com
   free, local only         free, works anywhere  free, works anywhere
   no token needed          no token needed       TOKEN REQUIRED
                                  │
                                  ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                     JARVIS  (Flutter, your phone)                    │
   │                                                                      │
   │   StockAlertService     polls, discovers the PC, schedules alarms    │
   │            │                                                         │
   │            ▼                                                         │
   │   ReminderService  ──►  Android notification  ──►  📳 VIBRATION      │
   └──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Two delivery paths — this is the key idea

Alerts reach your phone in **two completely different ways**, because the two
kinds of alert have different timing needs.

```
PATH A — IPO CALENDAR                    PATH B — LISTING MORNING
"BLEL closes today"                      "BUY at 122.00", "STOP HIT"

Dates are known days ahead.              Prices cannot be known ahead.
        │                                        │
        ▼                                        ▼
Jarvis fetches /api/ipo/calendar         StockSeer watches live prices
        │                                        │
        ▼                                        ▼
Schedules LOCAL ALARMS on the phone      Pushes alerts into notify.py queue
        │                                        │
        ▼                                        ▼
Phone fires them by itself               Jarvis POLLS every 5-20s and fires
        │                                        │
        ▼                                        ▼
✅ Works with Jarvis CLOSED              ❌ Needs Jarvis OPEN
✅ Works with the PC OFF                 ❌ Needs the PC ON and running
✅ Works with no network                 ❌ Needs the network link up
```

**Why the difference?** A local alarm just needs a date and a time — Android
holds it. A stop-loss needs a live price, and only the PC has that.

> **On listing morning, keep Jarvis open.** That is the one manual step.
> Everything else looks after itself.

---

## 3. Timeline of an IPO, end to end

```
DAY 1  ──────────────────────────────────────────────────────────────────
  NSE publishes the issue
  StockSeer:  ipo/registry.py fetches it
  Jarvis:     📳 info  "IPO open: SHIPROCKET, Rs.92-97"        (2.1s buzz)

DAY 2  ──────────────────────────────────────────────────────────────────
  Jarvis:     📳 act   "Closes tomorrow: SHIPROCKET"           (2.9s buzz)

DAY 3  ── BIDDING CLOSES ────────────────────────────────────────────────
  Jarvis:     📳 CRIT  "LAST DAY: SHIPROCKET"                  (3.2s buzz)
              "UPI mandate cut-off is usually 5:00 PM"
              ⭐ THIS IS THE ONE THAT MATTERS ⭐
              Allotment averaged +13.5% over 176 mainboard IPOs

DAY 4-6 ── allotment, refunds ───────────────────────────────────────────

DAY 7  ── DAY BEFORE LISTING ────────────────────────────────────────────
  Jarvis:     📳 info  "Lists tomorrow at 10:00"               (2.1s buzz)

DAY 8  ── LISTING DAY ───────────────────────────────────────────────────
  You:        start `stockseer ipo watch`, keep Jarvis open

  09:55       📳 act   "SHIPROCKET lists shortly"              (2.9s buzz)
  10:00       📳 act   "Listed at Rs.120.00 — DO NOT BUY YET"  (2.9s buzz)
                       (53% of listings peak in minute one and fade,
                        so this deliberately is NOT a buy signal)

  10:05       ── watcher checks: did it hold above Rs.120? ──
              ├── NO  → silence. No buy alert. You stay out.
              └── YES → 📳 CRIT "BUY at Rs.122.00"             (3.2s buzz)
                        BUY    Rs.122.00 x 327 sh = Rs.39,894
                        TARGET Rs.126.27  +3.5% = +Rs.1,396
                        STOP   Rs.118.34  -3.0% = -Rs.1,197

  10:05+      ── Jarvis speeds up to poll every 5 seconds ──

              📳 CRIT "Nearing target, +Rs.1,250"              (3.2s buzz)
              📳 CRIT "Falling, closing on the stop"           (3.2s buzz)
              📳 CRIT "TARGET HIT: SELL at Rs.126.27"          (3.2s buzz)
              📳 CRIT "STOP HIT: SELL at Rs.118.34"            (3.2s buzz)
              📳 CRIT "TRAILING STOP: SELL"                    (3.2s buzz)
              📳 CRIT "SESSION CLOSING with a position open"   (3.2s buzz)

              ── after any exit, Jarvis drops back to 20s polling ──
```

---

## 4. Every vibration, in one table

| # | Buzz | Pattern | Length | Fires when |
|---|------|---------|--------|------------|
| 1 | `ipo_opens_soon` | info | 2.1s | An IPO opens in 1–2 days |
| 2 | `ipo_opens_today` | info | 2.1s | Bidding opens |
| 3 | `ipo_closes_tomorrow` | act | 2.9s | Last full day to apply |
| 4 | **`ipo_closes_today`** | **critical** | **3.2s** | **LAST DAY — apply before 5 PM** |
| 5 | `ipo_lists_tomorrow` | info | 2.1s | Listing is tomorrow |
| 6 | `ipo_listing_soon` | act | 2.9s | ~5 min before listing |
| 7 | `ipo_listed` | act | 2.9s | First traded price. **Not a buy signal** |
| 8 | **`ipo_buy`** | **critical** | **3.2s** | Held above the open — buy price, target, stop |
| 9 | `ipo_near_target` | critical | 3.2s | 0.8% from target — get ready to sell |
| 10 | `ipo_near_stop` | critical | 3.2s | 0.8% from stop — decide now |
| 11 | `ipo_exit` | critical | 3.2s | Target / stop / trail / session close |

**The rhythms differ so you can tell them apart from your pocket:**

```
info      ▓▓▓▓▓▓▓▓▓   ▓▓▓▓▓▓▓▓▓                    two slow buzzes
act       ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓               three heavy buzzes
critical  ▓▓▓▓ ▓▓▓▓ ▓▓▓▓ ▓▓▓▓ ▓▓▓▓ ▓▓▓▓            six rapid pulses
```

---

## 5. The API, endpoint by endpoint

### Used by Jarvis

| Method | Endpoint | Purpose | Auth |
|--------|----------|---------|------|
| `GET` | `/api/ping` | "Are you StockSeer?" — used to find the PC | **never** |
| `GET` | `/api/notify/pending` | Alerts not yet delivered. **Polled every 5–20s** | yes |
| `POST` | `/api/notify/ack` | Mark delivered so it buzzes exactly once | yes |
| `GET` | `/api/ipo/calendar` | Dates, to schedule local alarms | yes |
| `POST` | `/api/notify/test` | The "Buzz me" button | yes |
| `GET` | `/api/state` | The "Save & test" button | yes |

### Used by the dashboard only

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/search` | Symbol search across 15,124 instruments |
| `GET` | `/api/candles` | Chart data + rule signal markers |
| `POST` | `/api/jobs` | Run backtest / sweep / plan / rules… |
| `GET` | `/api/jobs/<id>` | Poll a running job, stream its output |
| `GET/POST` | `/api/journal*` | Paper-trading journal |
| `GET/POST` | `/api/advisor/*` | Tip-service auditing |
| `POST` | `/api/ipo/scan` | Force a calendar scan now |
| `GET` | `/api/notify/recent` | Alert history |
| `GET` | `/api/alerts` | Intraday rule alerts |

**Auth** applies only when `STOCKSEER_TOKEN` is set in `.env`. Jarvis sends it as
`X-StockSeer-Token`. `/api/ping` stays open so the phone can still *find* the PC
without holding the secret.

---

## 6. How Jarvis finds the PC

```
  App starts, or 3 polls in a row fail
              │
              ▼
  Try the saved address ──── works? ──► done
              │
              ✗
              ▼
  Is the address remote?  (a hostname, or Tailscale's 100.x)
     ├── YES → stop. "Is the PC awake?"
     │         Nothing to scan: it either answers or it does not.
     │
     └── NO  → sweep the local network
                 │
                 ├─ list this phone's own interfaces (wifi, tether…)
                 ├─ for each, probe every address in its /24
                 ├─ 32 at a time, 400ms each, hitting /api/ping
                 └─ first host replying {"app":"stockseer"} wins → saved
```

Discovery checks the **app name**, not just a `200`, so a router page on port
8765 cannot be mistaken for the PC.

---

## 7. Setup checklist

**On the PC, every time:**

```powershell
python -m stockseer.cli ui --lan          # --lan matters: without it,
                                          # only the PC itself can connect
python -m stockseer.cli ipo watch         # listing mornings only
```

**Once, ever:**

```powershell
# Admin PowerShell — let the phone through the firewall
New-NetFirewallRule -DisplayName "StockSeer" -Direction Inbound `
  -LocalPort 8765 -Protocol TCP -Action Allow
```

**In Jarvis, once:** tap the 📈 icon → **Find my PC automatically**.

**On listing morning:** keep Jarvis open. That is the only manual step.

---

## 8. When something does not work

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No PC found" | Server bound to loopback | Restart with `--lan` |
| "No PC found", `--lan` is on | Firewall | Run the admin rule above |
| "No PC found", both fine | Phone and PC are on different networks | Tailscale or Cloudflare Tunnel |
| "Access code is wrong" | Token mismatch | Match `STOCKSEER_TOKEN` in `.env` |
| Calendar buzzes, listing does not | Jarvis was closed | Path B needs the app open |
| Nothing at all | Alerts toggle is off | Turn it on in the sheet |
| Worked yesterday, not today | Tether IP changed | It self-heals after 3 failures; or tap Find |

---

## 9. What the numbers in the alerts mean

Every listing-day alert carries its base rate, because that is when you need it.

**Applying for the IPO (allotment)** — 176 mainboard IPOs measured:

```
   mean +13.5%      median +7.3%      positive 69% of the time
   ⭐ This is the real edge. It is why alert #4 is the important one.
```

**Buying at the listing open** — 38 listings at minute resolution:

```
   at 11:00:  mean +0.69%   win rate 50%   t = 1.02
   53% of listings peak in their opening minute and fade
   worst single listing day: -20% (lower circuit)
```

`t = 1.02` means **not statistically distinguishable from luck** — you need
about 2.0 to claim an edge. The buy alerts exist because you asked for them and
they are risk-managed, but the tool will not pretend they are a sure thing.

The target (+3.5%) and stop (-3.0%) are not round numbers: they are the measured
average best gain (+3.35%) and average worst dip (-2.80%) before 11:00.

---

## 10. File map

| File | Role |
|------|------|
| `stockseer/ipo/registry.py` | Fetches IPOs from NSE |
| `stockseer/ipo/calendar.py` | Turns dates into alerts (Path A) |
| `stockseer/ipo/watcher.py` | Listing-morning price tracking (Path B) |
| `stockseer/ipo/study.py` | The +13.5% allotment measurement |
| `stockseer/ipo/intraday.py` | The minute-by-minute listing study |
| `stockseer/notify.py` | Alert queue + vibration patterns |
| `stockseer/web/server.py` | Flask API + dashboard |
| `stockseer/live/angel.py` | Angel One SmartAPI feed |
| `Jarvis/lib/services/stock_alert_service.dart` | Polling, discovery, alarms |
| `Jarvis/lib/screens/market_alerts_sheet.dart` | The settings screen |

---

*Research tooling, not investment advice. Every measurement here is
reproducible: `stockseer ipo study` and `stockseer ipo morning` regenerate the
numbers above from live data.*
