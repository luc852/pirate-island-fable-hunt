# Pirate Island: Treasure Hunt

The sequel to [Pirate Island Coin Hunt](https://github.com/luc852/pirate-island-coin-hunt),
which it grew out of and which stays available as it was.

A small pygame arcade game: sail between islands, collect every coin, dodge the
crabs and the tide pools, dig up the buried treasure, and get your name into the
Hall of Fame.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![pygame](https://img.shields.io/badge/pygame-2.5%2B-green)

## Playing in a browser

The game is compiled to WebAssembly and deployed as a static site, so it runs
in the browser with nothing to install.

## Playing on the desktop

```bash
pip install -r requirements.txt
python main.py
```

On Windows you can also just double-click `Play PirateGame.bat`.

**Controls**

| Key | Does |
| --- | --- |
| Arrows / `WASD` | Move |
| `Space` (or `E`) | Dig where you stand |
| `C` | Re-read the island's clue |
| `P` / `Esc` | Pause (and abandon the voyage) |
| `M` | Sound on / off |
| `Enter` | Continue past a card |

You start with 3 lives across all islands. Touching a crab, a tide pool or a
kraken arm costs a life and grants a short window of invincibility.

## What is on an island

- **Buried treasure.** Every island hides one chest under plain sand and washes
  up one message in a bottle. The message is a riddle that gets harder as you
  go: plain paces, paces from a landmark, mirror writing, a letter-shift cipher,
  and a row-and-column crossing. You get three digs per island, and the shovel
  tells you how warm a wrong hole was. Positions are re-rolled every voyage.
- **Random events.** A storm (rain, wind that pushes you, the tide surging over
  the sand, and coins worth double), the kraken (arms bursting out of
  telegraphed holes) or a golden crab to chase down.
- **The old map.** Each chest holds a fragment. What happens with all five is
  for you to find out.
- **Time of day.** The islands run from dawn to a lantern-lit night.

## Scoring

| Source | Points |
| --- | --- |
| Coin | 10, times the combo multiplier |
| Combo | every 3 coins chained within 2.6 s raises the multiplier, up to x5; a hit resets it |
| Storm | coins count double while it rages |
| Bottle / chest | 25 / 200 + 50 per island, plus a bonus for finding it with the first dig |
| Golden crab / kraken dodged | 200 / 150 |
| Island cleared | 100 x island number |
| Swift sailing | 3 per second under the island's par time |
| Untouched | 150 for an island without a hit |
| Lives to spare | 150 each, on winning |

The HUD shows the live score, the combo and its timer, the clock against par,
digs left and map fragments. Each island ends with an itemised tally, and the
run ends with a full breakdown by category and a pirate rank.

## Players and scores

The title screen has two ways aboard:

- **Returning pirate** — pick your name from the list, which is ranked by best
  score so you can see who is ahead.
- **New pirate** — type a name. If it matches someone already registered the two
  are consolidated, so `luc`, `Luc` and `LUC` are all the same pirate. The
  *Save my name and score* checkbox is on by default; unticking it gives you a
  guest run that is played but never recorded.

Scores live in `scores.json` next to the code. Each player keeps a best score and
a count of games played, the overall best is recomputed from the roster, and the
ten best individual voyages are kept for the Hall of Fame (reachable from the
title screen). Rosters saved by older versions load unchanged.

## Layout

| File | What it holds |
| --- | --- |
| `main.py` | Entry point |
| `game.py` | Game loop, screens, HUD |
| `sprites.py` | Player, crabs, coins, tide pools |
| `art.py` | Moods, obstacles, treasure props, parchment and lettering |
| `fx.py` | Particles, score popups, the animated sea, rain, screen shake |
| `levels.py` | Level grids and per-level tuning (mood, par time, clue, events) |
| `treasure.py` | Where the chest hides and how the riddle says so |
| `events.py` | The storm, the kraken and the golden crab |
| `scoring.py` | Points, combos, bonuses, ranks |
| `audio.py` | Sound playback (degrades to silence if there is no mixer) |
| `data.py` | The player roster and score persistence |
| `ui.py` | Title-screen widgets: combo box, text field, checkbox |
| `make_sounds.py` | Regenerates `assets/sounds/` (needs numpy; not needed to play) |
| `assets/` | Coin sprites (Kenney, CC0 — see `assets/images/KENNEY_LICENSE.txt`) and the synthesized sounds |
| `build_web.py` | Compiles the game to WebAssembly into `web/` |
| `web/` | The built browser version; this is what Vercel serves |

The `*.dc.html` files and `canvas.json` are design mockups of the screens, not
part of the running game.

## Rebuilding the browser version

```bash
pip install pygbag
python build_web.py
```

Then commit `web/` — that folder is what gets served. The same source runs both
ways; three details make the browser build work:

- `main.py` imports `pygame` explicitly, because pygbag reads that file's
  imports to decide what to load into the runtime.
- The frame is scaled with `transform.scale` rather than `smoothscale` on the
  web. `smoothscale` costs most of the frame budget in WebAssembly, which
  starves the browser's event delivery and makes the game stop responding.
- `VIDEORESIZE` only rebuilds the display on a genuinely new size, otherwise
  the canvas oscillates and the game never gets to read input.
- The sounds are `.wav`. pygbag prefers OGG and refuses WAV unless told
  otherwise, so `build_web.py` passes `--disable-sound-format-error`; the files
  load fine in the browser.

To try a build locally, serve `web/` and open it at `http://127.0.0.1:<port>`.
Use `127.0.0.1`, not `localhost`: on `localhost` pygbag expects its own
development server on port 8000 and the page stays grey.

**Scores in the browser are per-browser.** There is no shared server: they live
in that browser profile's local storage, so everyone using the same browser on
the same machine shares one roster, and nobody else sees it. The desktop version
still uses `scores.json`.

## Credits

Coin artwork from [Kenney](https://kenney.nl) under CC0. All sound is synthesized
by `make_sounds.py`; nothing is sampled.

To restyle the lettering, drop `display.ttf` and/or `body.ttf` into
`assets/fonts/`. Without them the game uses pygame's bundled font everywhere, so
the desktop and the browser lay text out identically.
