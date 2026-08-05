# Desktop pet

A small creature that lives on your screen, walks over when it wants your
attention, and — from Phase 2 on — does work for you when you ask it out loud.

Same character as the Jarvis phone app, so the PC pet and the phone mascot read
as one creature rather than two mascots.

## Run it

```bash
pip install -r requirements.txt
copy .env.example .env      # optional; sensible defaults without it
python main.py              # or double-click run.bat for no console window
```

Drag to move it. Click to poke it. Right-click the tray icon for the menu and
to quit.

## What it does today (Phase 1)

- Lives along the bottom of your screen, wanders, blinks, follows your cursor
  with its eyes, and naps if you ignore it.
- **Water reminders** on an interval.
- **Charging reminders** from the real battery — nags you to plug in below
  `BATTERY_LOW_PCT`, and to unplug above `BATTERY_FULL_PCT` so you stop
  cooking the cells at 100%. Edge-triggered, so it says it once per crossing.
- **Motivational quotes**, offline. No API key, no rate limit, no wifi.
- Speaks out loud via offline Windows TTS. Toggle from the tray.
- Quiet hours (`QUIET_START_HOUR`/`QUIET_END_HOUR`). Low-battery warnings
  ignore them on purpose.
- **Opens Windows apps.** Double-click the pet, type `open brave`. It indexes
  your Start Menu (158 apps here) and launches by name.
- **Listens.** Say *"Jarvis, open Brave"* — or just *"Jarvis"*, wait for it to
  answer, then talk. Entirely offline: faster-whisper on the CPU, no speech
  API, nothing leaves the machine. Toggle it from the tray.
- **Understands loose phrasing**, via a local model, but only as a fallback —
  see below.

Everything is tunable in `.env` — see `.env.example`.

### The app launcher is the never-guess rule in miniature

Ask for `brave` and it just opens it — one clear best match. Ask for something
vague like `my browser`, or something it's never heard of, and it **refuses to
guess**: it walks over, says it doesn't know that one, and shows you a picker.
Whatever you choose gets written to `recipes.json`, and from then on that
phrase is a dictionary lookup — no matching, no model, no drift.

That's the whole pattern the bigger tasks will use. Teach once, replay forever.

### The model is a fallback, not the main path

`open brave` is handled by ordinary string parsing — instant, and structurally
incapable of inventing anything. Only phrasing that fails to parse goes to the
local model, which takes about four seconds.

That ordering isn't just about speed. Asked about *"i'm so tired today"*,
phi4-mini returned `{"action": "reminder", "target": "take some rest"}` — a
task nobody requested. So two guards exist:

- Only actions on a **whitelist** (`brain.ACTIONABLE`) are ever carried out.
  Everything else the model dreams up is discarded.
- Anything the model interpreted needs a **confirmation click**, even opening
  an app. Plain-parsed commands don't. Set `CONFIRM_MODEL_ACTIONS=false` to
  drop that, but read the paragraph above first.

Ollama isn't kept running in the background — the pet starts it the first time
it actually needs it.

## Web forms — teach once, replay forever

```
teach internship form https://forms.gle/xxxx     # you fill it, it watches
fill internship form                             # it fills, you approve
```

**Teaching.** The pet opens the form in Brave and *steps back*. You fill it in
yourself. Then it reads back what you put and stores it. It never submits
during a teaching session.

**Replaying.** It fills in what you taught it, then stops and shows you exactly
what it filled and anything it couldn't. Nothing is submitted until you click.
That gate stays forever — it's cheap, and a submitted form isn't undoable.

Answers are stored **keyed by question text**, not by CSS selector. Google
obfuscates class names and re-renders constantly, so a recorded selector rots
within weeks; "What is your name?" does not.

**When the form has changed**, the pet fills what it still recognises and
*reports the rest* — a renamed option or a deleted question shows up in the
approval list rather than being guessed at or silently dropped. If it can't
fill anything, it refuses rather than submitting a blank form.

Brave runs from its own profile (`browser_profile/`), so the pet never locks or
borrows the window you're using. You sign into Google there once.

## Design decisions worth knowing

**The pet never guesses.** If it hasn't been shown how to do something, it does
not improvise — it walks over, asks you to do it, and *watches*. What you did
becomes a recorded recipe, and from then on it replays that recipe
deterministically. This is why the automation path needs no LLM at all: no
hallucinated form field, no prompt injection, no per-run cost, no "it worked
last week". An unknown task is a five-minute teaching session, once.

**Nothing you say leaves the machine.** Speech is transcribed by
faster-whisper locally; loose phrasing is interpreted by phi4-mini locally.
Writing prose, like a cold email draft, is a rare hard job that may call a
cloud model — but that's opt-in and one env var, not a dependency.

**Draft, then ask.** Anything that leaves the machine — a form submit, a sent
email — shows you a filled preview and waits for a click. This stays even when
it feels slow, because one wrong recipient on a cold mail is unrecoverable.

**Hand-painted, not sprites.** The mascot is drawn with QPainter
(`shell/mascot.py`), same choice as `Jarvis/lib/widgets/mascot.dart`. Scales to
any DPI, zero assets, and its mood is a parameter instead of a folder of PNGs.

## Roadmap

| Phase | What | State |
|---|---|---|
| 1 | Pet shell + water/battery/quote nudges | **done** |
| 1.5 | Command bar, recipe book, opening Windows apps | **done** |
| 2 | Offline voice + local brain as a gated fallback | **done** |
| 3a | Google Forms: teach once in Brave, replay with approval | **done** |
| 3b | Cold mail — Gmail SMTP, drafted then held for approval | not started |
| 4 | Phone — largely covered by OpenClaw's existing WhatsApp link | |

Browser work uses **Brave** (auto-detected into `config.BROWSER_PATH`). It's
Chromium, so Playwright drives it via `executable_path` — no bundled browser
download. Recorded tasks run in their own profile (`browser_profile/`) so the
pet never locks or borrows the window you're actually using.

Phone comes last on purpose: a phone can't drive Chrome, so the PC stays the
executor and Jarvis becomes a remote for it.

## Layout

```
main.py              entry point
config.py            every tunable, read from .env
core/    events.py    the signal bus nudges and skills talk through
         voice.py     TTS on a worker thread (blocking it would freeze the pet)
         ears.py      offline listening: PyAudio + faster-whisper, wake word
         brain.py     the local model. Fallback only, and it starts Ollama.
         recipes.py   everything the pet has been taught -> recipes.json
         commander.py routes a request. Plain parse first, model second.
skills/  apps.py      find and open Windows apps
         gform.py     read/fill Google Forms, keyed by question text
         webtask.py   a browser session on its own thread; teach and replay
shell/   mascot.py    the creature, drawn in a normalised 100x100 box
         window.py    frameless translucent window, walking, speech queue
         bubble.py    the speech bubble
         ask.py       command bar + the picker it uses when it doesn't know
         tray.py      tray icon + menu
nudges/  lines.py     everything it says on a schedule
         scheduler.py when it says it
tools/   preview.py   render every mood to a PNG without launching the pet
         smoketest.py run the real event loop for 18s and assert nothing broke
         test_apps.py check app matching against your real Start Menu
```

## Developing

```bash
python tools/preview.py out.png    # contact sheet of every mood + bubbles
python tools/smoketest.py          # 18s live run, asserts fps and delivery
python tools/test_apps.py          # app matching, launches nothing
python tools/test_brain.py         # is the local model good enough to route?
python tools/test_routing.py       # plain-vs-model paths and the confirm gate
python tools/test_ears.py          # speech chain + whether your mic works
python tools/test_gform.py         # form reading/filling, incl. changed forms
python tools/test_webtask.py       # full teach->replay cycle + approval gate
python tools/test_formrouting.py   # "fill x" / "teach x <url>" parsing
```

`test_ears.py` speaks its own test phrases through the offline Windows voice
and feeds them back through Whisper, so you don't have to talk to it. Bear in
mind synthesised speech is cleaner than a real room — it proves the plumbing,
not that it will hear *you*. The microphone level check at the end is the part
that says something about your setup.

`smoketest.py` fires reminders faster than the pet can deliver them, on
purpose — the speech queue must never drop one. It also overflows the queue to
prove that only *optional* chatter gets shed.

`test_apps.py`'s most important assertions are the negative ones: vague and
nonsense queries must come back **not confident**, so the pet asks rather than
opening the wrong thing. Same for `test_routing.py` — the assertion that
matters is that *"i'm so tired today"* produces no task at all.

### If the pet can't hear you

Windows will happily hand out a **virtual audio cable** as the default input —
on this machine the default was `Voice.ai Audio Cable`, which delivers pure
silence. The pet now skips anything that looks virtual and picks a real mic,
and it says so out loud if the device it opened turns out to be silent. If it
still picks wrong, run `tools/test_ears.py` for the device list and set
`MIC_INDEX` in `.env`.
