#!/usr/bin/env python3
"""lines.py: the line at open, kept because the feed does not keep it.

WHY THIS FILE EXISTS. The 20 September law asks the card to show "the line at open
beside the line now", and on finals whether the favourite covered and whether the total
went over. Neither is possible from the scoreboard feed alone: ESPN carries the `odds`
object only while a game is still scheduled and drops it at kickoff. Measured on the
Sunday night slate, 0 of 61 finals carried a provider line and 0 of 6 live games did.
So a line nobody logged before kickoff is a line that is gone for good, and two clauses
of the law can never render.

WHAT IT KEEPS. One record per game: the FIRST line ever seen for it, the LATEST, and a
count of how many times it changed in between. The first is never overwritten once
written, which is the entire point of the file.

WHAT IT IS NOT. Not a history of every tick, and not a prediction of anything. It is
two readings and a count, so the card can say "opened KC -6, now KC -6.5" as a pair of
facts with one provider named on both.

FAIL-SAFE. A game that cannot be read keeps whatever the file already had for it. A file
that cannot be parsed is rebuilt from this build's games rather than crashing the build,
because a missing open line costs one line on one card and never the site.

Entries are dropped once a game's kickoff is more than KEEP_DAYS old, so the file stays
proportional to the season in play rather than growing for ever.

USAGE  python3 lines.py --report     read the committed file
       (the build calls log() with the games it already fetched)
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site", "data", "lines.json")
KEEP_DAYS = 12
NUM_KEYS = ("detail", "spread", "total", "ml_away", "ml_home")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(s):
    try:
        return datetime.datetime.strptime(s or "", "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def load():
    try:
        d = json.load(open(OUT, encoding="utf-8"))
        if isinstance(d.get("games"), dict):
            return d
    except Exception:
        pass
    return {"updated_at": None, "games": {}}


def _reading(ln, at):
    out = {k: ln[k] for k in NUM_KEYS if ln.get(k) is not None}
    out["at"] = at
    return out


def _same(a, b):
    return all(a.get(k) == b.get(k) for k in NUM_KEYS)


def log(games, now=None):
    """Fold this build's lines into the file. Returns the loaded record either way, so
    a caller can use it immediately without a second read."""
    now = now or _now()
    at = _iso(now)
    doc = load()
    rec = doc["games"]
    wrote = opened = moved = 0
    for g in games or []:
        gid = str(g.get("id") or "")
        ln = g.get("line") or {}
        if not gid or not ln.get("provider"):
            continue
        r = _reading(ln, at)
        cur = rec.get(gid)
        if not cur:
            rec[gid] = {"provider": ln["provider"], "kick": g.get("start_utc") or "",
                        "open": r, "now": dict(r), "moves": 0}
            opened += 1
            wrote += 1
            continue
        cur["provider"] = ln["provider"]
        cur["kick"] = g.get("start_utc") or cur.get("kick") or ""
        if not _same(cur.get("now") or {}, r):
            cur["moves"] = int(cur.get("moves") or 0) + 1
            moved += 1
        cur["now"] = r
        wrote += 1

    cut = now - datetime.timedelta(days=KEEP_DAYS)
    dropped = [k for k, v in rec.items()
               if (_dt(v.get("kick")) or now) < cut]
    for k in dropped:
        rec.pop(k, None)

    doc["updated_at"] = at
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        tmp = OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
        os.replace(tmp, OUT)
    except Exception as e:
        print(f"lines: could not write ({type(e).__name__}); kept in memory only")
    print(f"lines: {wrote} logged, {opened} new, {moved} moved, "
          f"{len(rec)} on file"
          + (f", {len(dropped)} expired" if dropped else ""))
    return doc


def for_game(doc, gid):
    return ((doc or {}).get("games") or {}).get(str(gid or "")) or None


def report():
    doc = load()
    rec = doc.get("games") or {}
    print(f"lines: {len(rec)} game(s), updated {doc.get('updated_at')}")
    moved = [(k, v) for k, v in rec.items() if int(v.get("moves") or 0)]
    print(f"  {len(moved)} with a move logged")
    for k, v in sorted(moved, key=lambda kv: -int(kv[1].get("moves") or 0))[:8]:
        print(f"   {k}: {v['provider']} open {v['open'].get('detail')} "
              f"-> now {v['now'].get('detail')} ({v['moves']} move(s))")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        print("lines: nothing to do; the build calls log(). Try --report")
