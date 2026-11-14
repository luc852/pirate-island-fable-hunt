"""Score persistence.

The roster is open-ended: any name a player types is registered on the spot,
and names are matched case-insensitively so "luc" and "Luc" are one pirate.

Where the roster lives depends on where the game is running. On the desktop it
is scores.json beside the code. Compiled to WebAssembly there is no writable
disk, so it goes to the browser's localStorage instead - which means the roster
is shared by everyone using that browser profile, and by no one else.
"""
import json
import os
import sys
import time

IS_WEB = sys.platform == "emscripten"

SCORES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scores.json")
STORAGE_KEY = "pirate-island-treasure-hunt/scores"

MAX_NAME_LEN = 14
MAX_RUNS = 10

DEFAULT_DATA = {
    "players": {},
    "overall_best": {"name": "", "score": 0},
    # The ten best individual voyages, for the Hall of Fame.
    "runs": [],
}


def clean_name(raw):
    """Trim, collapse inner whitespace and cap the length of a typed name."""
    return " ".join(str(raw).split())[:MAX_NAME_LEN]


def read_raw():
    """The stored roster as JSON text, or None when nothing has been saved."""
    if IS_WEB:
        import platform
        return platform.window.localStorage.getItem(STORAGE_KEY)
    if not os.path.exists(SCORES_PATH):
        return None
    try:
        with open(SCORES_PATH, "r") as f:
            return f.read()
    except OSError:
        return None


def write_raw(text):
    """Persist the roster. Never raises: a lost score beats a crashed game."""
    try:
        if IS_WEB:
            import platform
            platform.window.localStorage.setItem(STORAGE_KEY, text)
        else:
            with open(SCORES_PATH, "w") as f:
                f.write(text)
        return True
    except Exception:
        # Private-browsing quotas, a read-only folder: play on regardless.
        return False


def load_scores():
    raw = read_raw()
    if not raw:
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return json.loads(json.dumps(DEFAULT_DATA))
    if not isinstance(loaded, dict):
        return json.loads(json.dumps(DEFAULT_DATA))

    data = json.loads(json.dumps(DEFAULT_DATA))
    for name, entry in (loaded.get("players") or {}).items():
        name = clean_name(name)
        if not name:
            continue
        try:
            best = int(entry.get("best_score", 0))
            games = int(entry.get("games_played", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        # A file edited by hand may hold two spellings of one pirate; fold them.
        existing = find_player(data, name)
        legend = bool(entry.get("legend", False))
        if existing:
            data["players"][existing]["best_score"] = max(
                data["players"][existing]["best_score"], best)
            data["players"][existing]["games_played"] += games
            data["players"][existing]["legend"] |= legend
        else:
            data["players"][name] = {"best_score": best, "games_played": games,
                                     "legend": legend}

    # Rosters saved before the Hall of Fame existed simply have no runs.
    runs = loaded.get("runs")
    for run in runs if isinstance(runs, list) else []:
        try:
            data["runs"].append({
                "name": clean_name(run["name"]),
                "score": int(run["score"]),
                "islands": int(run.get("islands", 0)),
                "fragments": int(run.get("fragments", 0)),
                "legend": bool(run.get("legend", False)),
                "rank": str(run.get("rank", ""))[:24],
                "date": str(run.get("date", ""))[:10],
            })
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    sort_runs(data)

    refresh_overall_best(data)
    return data


def save_scores(data):
    return write_raw(json.dumps(data, indent=2))


def find_player(data, name):
    """Return the registered spelling matching `name`, or None."""
    key = clean_name(name).lower()
    if not key:
        return None
    for registered in data["players"]:
        if registered.lower() == key:
            return registered
    return None


def refresh_overall_best(data):
    best_name, best_score = "", 0
    for name, entry in data["players"].items():
        if entry["best_score"] > best_score:
            best_name, best_score = name, entry["best_score"]
    data["overall_best"] = {"name": best_name, "score": best_score}
    return data


def sort_runs(data):
    data["runs"].sort(key=lambda r: (-r["score"], r["name"].lower()))
    del data["runs"][MAX_RUNS:]


def is_legend(data, name):
    existing = find_player(data, name)
    return bool(existing and data["players"][existing].get("legend"))


def register_player(data, name):
    """Add the pirate if new, and return the canonical spelling of the name."""
    existing = find_player(data, name)
    if existing:
        return existing
    name = clean_name(name)
    data["players"][name] = {"best_score": 0, "games_played": 0, "legend": False}
    return name


def best_score(data, name):
    existing = find_player(data, name)
    return data["players"][existing]["best_score"] if existing else 0


def ranking(data):
    """(name, best_score) pairs, best first, ties broken alphabetically."""
    return sorted(((n, e["best_score"]) for n, e in data["players"].items()),
                  key=lambda pair: (-pair[1], pair[0].lower()))


def record_score(data, player_name, score, summary=None):
    """Register the pirate if needed, then keep their best run, the overall
    best, and - when the voyage ranks - a line in the Hall of Fame."""
    name = register_player(data, player_name)
    entry = data["players"][name]
    entry["games_played"] += 1
    if score > entry["best_score"]:
        entry["best_score"] = score
    summary = summary or {}
    if summary.get("legend"):
        entry["legend"] = True
    if score > 0:
        data["runs"].append({
            "name": name,
            "score": int(score),
            "islands": int(summary.get("islands", 0)),
            "fragments": int(summary.get("fragments", 0)),
            "legend": bool(summary.get("legend", False)),
            "rank": str(summary.get("rank", "")),
            "date": time.strftime("%Y-%m-%d"),
        })
        sort_runs(data)
    refresh_overall_best(data)
    save_scores(data)
    return data
