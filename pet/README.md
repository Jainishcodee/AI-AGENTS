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

Everything is tunable in `.env` — see `.env.example`.

### The app launcher is the never-guess rule in miniature

Ask for `brave` and it just opens it — one clear best match. Ask for something
vague like `my browser`, or something it's never heard of, and it **refuses to
guess**: it walks over, says it doesn't know that one, and shows you a picker.
Whatever you choose gets written to `recipes.json`, and from then on that
phrase is a dictionary lookup — no matching, no model, no drift.

That's the whole pattern the bigger tasks will use. Teach once, replay forever.

## Design decisions worth knowing

**The pet never guesses.** If it hasn't been shown how to do something, it does
not improvise — it walks over, asks you to do it, and *watches*. What you did
becomes a recorded recipe, and from then on it replays that recipe
deterministically. This is why the automation path needs no LLM at all: no
hallucinated form field, no prompt injection, no per-run cost, no "it worked
last week". An unknown task is a five-minute teaching session, once.

**Two different brains, not one.** Hearing you and understanding intent is a
constant, tiny job — that runs on a *local* model (Ollama, phi-4-mini at ~3 GB,
fits a 4 GB card) so it's free, offline, and your voice never leaves the
machine. Writing prose, like a cold email draft, is a rare, hard job and can
call a cloud model. The provider is one env var; nothing is locked to Gemini.

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
| 2 | Wake word + local intent parsing (Ollama, phi-4-mini) | next |
| 3 | Web tasks: record once in Brave, replay forever; cold mail | |
| 4 | Jarvis phone bridge — phone asks, PC executes | |

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
         recipes.py   everything the pet has been taught -> recipes.json
         commander.py routes what you typed to a skill. Plain code, no model.
skills/  apps.py      find and open Windows apps
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
```

`smoketest.py` fires reminders faster than the pet can deliver them, on
purpose — the speech queue must never drop one. It also overflows the queue to
prove that only *optional* chatter gets shed.

`test_apps.py`'s most important assertions are the negative ones: vague and
nonsense queries must come back **not confident**, so the pet asks rather than
opening the wrong thing.
