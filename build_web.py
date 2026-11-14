"""Build the browser (WebAssembly) version of the game into ./web.

    python build_web.py

The game itself is unchanged: pygbag compiles the same source that `python
main.py` runs. This script only controls *what* gets compiled and patches one
bug in the generated page.

Run it again after changing any game code, then commit ./web, since that folder
is what Vercel actually serves.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# Only the running game. Deliberately excludes the .dc.html design mockups, the
# 2.3 MB redesign document, scores.json (the browser uses localStorage instead)
# and .claude/, all of which pygbag would otherwise pack into the public bundle.
GAME_FILES = ["main.py", "game.py", "sprites.py", "levels.py", "data.py", "ui.py",
              "art.py", "audio.py", "events.py", "fx.py", "scoring.py", "treasure.py"]
GAME_DIRS = ["assets"]

APP = "pirate-island-treasure-hunt"
STAGE = ROOT / "build" / APP
OUT = ROOT / "web"

# pygbag 0.9.3 only handles an integer devicePixelRatio. Windows at 150% display
# scaling reports 1.5, and the canvas is then left at 1x1 - a blank grey page.
# Pinning it to 1 costs a little sharpness on HiDPI screens and nothing else.
DPR_SHIM = (
    '<html lang="en-us"><script>'
    "Object.defineProperty(window,'devicePixelRatio',"
    "{get:function(){return 1;},configurable:true});"
    "</script>"
)


def stage():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    for name in GAME_FILES:
        shutil.copy2(ROOT / name, STAGE / name)
    for name in GAME_DIRS:
        shutil.copytree(ROOT / name, STAGE / name)
    print(f"staged {len(GAME_FILES)} modules + {len(GAME_DIRS)} asset folder(s)")


def build():
    subprocess.run(
        [sys.executable, "-m", "pygbag", "--build",
         "--width", "900", "--height", "600",
         "--app_name", APP,
         "--title", "Pirate Island: Treasure Hunt",
         "--ume_block", "0",
         # pygbag would rather have OGG, but nothing here can encode it and
         # SDL_mixer's built-in WAV loader works in the browser.
         "--disable-sound-format-error",
         str(STAGE)],
        check=True,
    )


def patch_and_collect():
    web = STAGE / "build" / "web"
    index = web / "index.html"
    html = index.read_text(encoding="utf-8")
    if "devicePixelRatio" not in html:
        html = html.replace('<html lang="en-us">', DPR_SHIM, 1)
        index.write_text(html, encoding="utf-8")

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(web, OUT)
    # Keep both archives. The .apk is what the banner names, but the loader
    # actually fetches the .tar.gz; dropping it fails with "tarfile.ReadError:
    # empty file" once the runtime is already up.

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"\n-> {OUT} ({total / 1024:.0f} KB)")
    for f in sorted(OUT.rglob("*")):
        if f.is_file():
            print(f"   {f.relative_to(OUT)}  {f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    stage()
    build()
    patch_and_collect()
