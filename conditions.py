#!/usr/bin/env python3
"""conditions.py: the week board's kickoff conditions, from GoCheckMyWeather's Worker (S-2b item 0).

Program 7 (Jack, 12 October 2026): conditions come only from the conditions Worker, which reads
the National Weather Service. The ESPN feed's weather is never read. The contract is
gocheckmyweather/docs/CONDITIONS-API.md; where it and the Worker disagree, the Worker is right.

AT BUILD, ONCE. `/stadiums` is read once; then one `/game?venue=&kickoff=&league=` per NFL and
FBS game on the week board, with the venue id and the kickoff the schedule already carries. The
answer is written to site/data/conditions.json and published at /data/conditions.json. No page
calls the Worker: a page prints the build's numbers with the NWS stamp (live reads wait for S-4).

THE MATCH. An NFL game matches the row whose `espn_venue_id` (or an `alt_venue_ids` entry) is
the feed's venue id. A college game matches the row whose name is ESPN's venue name, exactly;
where two rows share a name, the feed's city and state choose. Nothing is matched loosely.

WHAT EACH GAME GETS (`status`):
  forecast       the Worker's slice: kickoff hour, hours, flags, alerts, roof, credit, stamps
  indoor         a fixed roof: no forecast, one line, "Indoor"
  roofed         a retractable or fixed roof in the stadium table: no forecast, no flag, one line,
                 "Roof . usually closed" (S-3a, 15 October 2026)
  out_of_range   past the NWS hourly product: "Forecast from Sat, Oct 17", the day it comes in
  outside_nws    an international venue (Wembley): "Outside NWS coverage" (Jack, 13 October)
  missing        no row in the table, or a row the Worker cannot place: prints nothing, and
                 the build log lists it
  error          the Worker failed: prints nothing, and the build log says so
A game already over is answered `in_range: false, in_range_from: null` by the Worker. Its strip
is the record, so the entry the last build published is carried forward unchanged, stamp and all.

`alerts: null` means the Worker could not check; the words say "Alerts not checked", never
"No alerts". `alerts: []` means checked and none, and the words say nothing about alerts.

USAGE  python3 conditions.py --report     read the committed or built file
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site", "data", "conditions.json")
WORKER = "https://conditions.gocheckmybrands.workers.dev"
PUBLISHED = "https://gocheckmysports.com/data/conditions.json"
UA = "GoCheckMySports build (desk@gocheckmysports.com)"
TIMEOUT = 20
ET = ZoneInfo("America/New_York")
LEAGUE = {"NFL": "nfl", "CFB": "cfb"}
US = {"USA", "US", "United States"}

ROOF_WORDS = {"open": "Open air", "retractable": "Retractable roof", "fixed": "Roof", "indoor": "Indoor"}

# S-3a, Jack's ruling of 15 October 2026: a game at a stadium with a roof is played under a roof the
# team decides about, so the weather outside is not the game's weather. The STADIUM TABLE's roof field
# says which stadiums those are (not a name list), and such a game reads like a dome row: no flag, no
# alert, no forecast plates. "roof_state" ("open" or "closed") is the venue's published state when a
# source carries one; with none, the words say what is usual.
ROOFED = ("retractable", "fixed")
ROOF_LINES = {"open": "Roof \u00b7 open", "closed": "Roof \u00b7 closed"}
ROOF_USUAL = "Roof \u00b7 usually closed"


def roofed(e):
    return bool(e) and e.get("roof") in ROOFED


def roofed_entry(e):
    """A forecast entry for a roofed stadium becomes status "roofed": the forecast, the flags and
    the alerts are dropped, the words say the roof. Anything else is returned untouched, and a
    roofed entry is returned as it is (idempotent: the build applies this to what it reads)."""
    if not e or e.get("status") != "forecast" or not roofed(e):
        return e
    out = {k: v for k, v in e.items()
           if k not in ("kickoff_hour", "hours", "flags", "alerts", "alerts_status", "nws", "words")}
    out["status"] = "roofed"
    out["words"] = {"line": ROOF_LINES.get(e.get("roof_state") or "", ROOF_USUAL),
                    "roof": ROOF_WORDS.get(e.get("roof") or "", "Roof")}
    return out


def fetch(path):
    """GET a Worker path. Returns (http_status, json or None). Never raises."""
    req = urllib.request.Request(WORKER + path, headers={"User-Agent": UA,
                                                         "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception:
        return 0, None


def _published():
    """The entries the last build published, for the finals that keep their strip."""
    try:
        req = urllib.request.Request(PUBLISHED, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return (json.loads(r.read()) or {}).get("games") or {}
    except Exception:
        pass
    try:
        return (json.load(open(OUT, encoding="utf-8")) or {}).get("games") or {}
    except Exception:
        return {}


def match_row(rows, game):
    """The stadium row for a game, or None. NFL by the feed's venue id; college by ESPN's
    venue name, exactly, with the city and state choosing between rows of one name."""
    vid = str(game.get("venue_id") or "")
    if game.get("league") == "NFL":
        for r in rows:
            if vid and (r.get("espn_venue_id") == vid or vid in (r.get("alt_venue_ids") or [])):
                return r
        return None
    name = game.get("venue") or ""
    hits = [r for r in rows if name and r.get("name") == name]
    if len(hits) > 1:
        hits = [r for r in hits if r.get("city") == game.get("venue_city")
                and r.get("state") == game.get("venue_state")]
    return hits[0] if len(hits) == 1 else None


def _kick_param(start_utc):
    """The schedule's kickoff as the Worker takes it: 2026-10-16T00:15Z."""
    s = (start_utc or "").strip()
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _et_day(iso):
    try:
        d = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
    except Exception:
        return None
    return d.strftime("%a, %b ") + str(d.day)


def _hour(h):
    keep = ("start", "end", "temp_f", "feels_like_f", "feels_like_kind", "wind_mph", "gust_mph",
            "wind_dir", "wind_from_deg", "pop_pct", "precip_type", "sky", "is_daytime")
    return {k: h.get(k) for k in keep}


def _alert(a):
    keep = ("event", "headline", "severity", "sender_name", "onset", "expires", "ends")
    return {k: a.get(k) for k in keep}


def _ts(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None


def _ends_before(a, window_from):
    """True when the alert is over before the game's window opens. The Worker sends what is
    in force over the point at the read; a Tuesday watch is not Sunday's weather. NWS's
    `ends` is the event's end; with none, the message's `expires` is the bound."""
    end, start = _ts(a.get("ends") or a.get("expires")), _ts(window_from)
    return bool(end and start and end <= start)


def _reflag(flags, alerts):
    """The alert flag and `any`, recomputed over the alerts that reach the window."""
    if not isinstance(flags, dict):
        return flags
    f = dict(flags)
    if alerts is None:
        f["alert"] = dict(f.get("alert") or {}, on=None, count=None)
    else:
        f["alert"] = dict(f.get("alert") or {}, on=bool(alerts), count=len(alerts))
    f["any"] = any((f.get(k) or {}).get("on") for k in ("wind", "precip", "feels", "alert"))
    return f


def words(e):
    """The printed words for one entry. Every string here comes from a number the Worker
    gave; a number it did not give is not worded."""
    st = e.get("status")
    if st == "indoor":
        return {"line": "Indoor", "roof": "Indoor"}
    if st == "outside_nws":
        return {"line": "Outside NWS coverage"}
    if st == "out_of_range":
        day = _et_day(e.get("in_range_from") or "")
        return {"line": f"Forecast from {day}" if day else ""}
    if st != "forecast":
        return {}
    k = e.get("kickoff_hour") or {}
    w = {}
    t = k.get("temp_f")
    if isinstance(t, (int, float)):
        w["temp"] = f"{round(t)}°"
        f = k.get("feels_like_f")
        if isinstance(f, (int, float)) and round(f) != round(t):
            w["feel"] = f"feels {round(f)}°"
    wd = (k.get("wind") or {}).get("text")
    if wd:
        w["wind"] = wd
    p = k.get("pop_pct")
    if isinstance(p, (int, float)):
        w["precip"] = f"{round(p)}% {k.get('precip_type') or 'precip'}"
    w["roof"] = ROOF_WORDS.get(e.get("roof") or "", "")
    if e.get("alerts") is None:
        w["alert"] = "Alerts not checked"
    elif e.get("alerts"):
        w["alert"] = e["alerts"][0].get("event") or ""
    if k.get("sky"):
        w["sky"] = k["sky"]
    return w


def entry(game, row, status, ans):
    """One game's entry from the Worker's answer. `ans` is the parsed body or None."""
    e = {"status": status, "league": game.get("league"), "kickoff": _kick_param(game.get("start_utc")),
         "venue_id": str(game.get("venue_id") or ""), "venue": game.get("venue") or ""}
    if row:
        e["stadium"] = {k: row.get(k) for k in ("slug", "espn_venue_id", "name", "city", "state",
                                                "roof", "orientation_deg")}
        e["stadium"]["page"] = f"https://gocheckmyweather.com/stadiums/{row.get('slug')}.html"
        e["roof"] = row.get("roof")
    ans = ans or {}
    if status == "out_of_range":
        e["in_range_from"] = ans.get("in_range_from")
        e["reason"] = ans.get("reason")
    if status == "forecast":
        e["roof"] = ans.get("roof") or e.get("roof")
        e["window"] = ans.get("window")
        e["kickoff_hour"] = dict(_hour(ans.get("kickoff_hour") or {}),
                                 wind=(ans.get("kickoff_hour") or {}).get("wind"))
        e["hours"] = [_hour(h) for h in ans.get("hours") or []]
        e["flags"] = ans.get("flags")
        al = ans.get("alerts")
        e["alerts"] = None if al is None else [_alert(a) for a in al
                                               if not _ends_before(a, (e["window"] or {}).get("from"))]
        e["flags"] = _reflag(e["flags"], e["alerts"])
        e["alerts_status"] = ans.get("alerts_status")
        e["stale"] = bool(ans.get("stale"))
        n = ans.get("nws") or {}
        e["nws"] = {k: n.get(k) for k in ("generated_at", "generated_et", "read_at", "stale")}
        e["credit"] = ans.get("credit")
        e["worker_at"] = (ans.get("worker_at") or {}).get("utc")
    if status in ("indoor", "forecast") and not e.get("credit") and row:
        e["credit"] = {"text": "Conditions by GoCheckMyWeather, NWS",
                       "url": e["stadium"]["page"]}
    e["words"] = words(e)
    return roofed_entry(e)


def game_key(g):
    return str(g.get("id") or "")


def refresh(games, now=None, get=fetch, published=_published, log=print):
    """Read the Worker for every board game and write OUT. Returns the payload."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    code, st = get("/stadiums")
    rows = (st or {}).get("rows") or [] if code == 200 else []
    if not rows:
        log(f"conditions: /stadiums answered {code}; no conditions this build")
    prior = None
    out, missing, errors = {}, [], []
    for g in games:
        key = game_key(g)
        if not key or g.get("league") not in LEAGUE:
            continue
        label = (f'{g.get("league")} {(g.get("away") or {}).get("abbr", "")} at '
                 f'{(g.get("home") or {}).get("abbr", "")}, {g.get("venue") or "no venue"}')
        country = (g.get("venue_country") or "").strip()
        if country and country not in US:
            out[key] = entry(g, None, "outside_nws", None)
            continue
        if not rows:
            out[key] = entry(g, None, "error", None)
            continue
        row = match_row(rows, g)
        kick = _kick_param(g.get("start_utc"))
        if not row or not kick:
            out[key] = entry(g, None, "missing", None)
            missing.append(label + (f' (venue id {g.get("venue_id")})' if g.get("venue_id") else ""))
            continue
        q = urllib.parse.urlencode({"venue": row["espn_venue_id"], "kickoff": kick,
                                    "league": LEAGUE[g["league"]]})
        code, ans = get(f"/game?{q}")
        ans = ans or {}
        if code == 200 and ans.get("roof") == "indoor":
            out[key] = entry(g, row, "indoor", ans)
        elif code == 200 and ans.get("in_range") is False and ans.get("in_range_from"):
            out[key] = entry(g, row, "out_of_range", ans)
        elif code == 200 and ans.get("in_range") is False:
            # the game is over: its strip is the record, carried from the last build
            if prior is None:
                prior = published()
            old = prior.get(key)
            if old and old.get("status") == "forecast":
                out[key] = dict(old, record=True)
            else:
                out[key] = entry(g, row, "over", ans)
        elif code == 200 and ans.get("hours") is not None:
            out[key] = entry(g, row, "forecast", ans)
        elif code in (404, 503) and ans.get("error") in ("unknown_venue", "no_coordinates"):
            out[key] = entry(g, row, "missing", ans)
            missing.append(f'{label} ({ans.get("error")})')
        else:
            out[key] = entry(g, row, "error", ans)
            errors.append(f'{label} (HTTP {code} {ans.get("error") or ""})'.strip())
    payload = {"built_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "GoCheckMyWeather conditions Worker, from the National Weather Service",
               "worker": WORKER, "stadiums_built": (st or {}).get("built"),
               "games": out, "missing": missing, "errors": errors}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    by = {}
    for v in out.values():
        by[v["status"]] = by.get(v["status"], 0) + 1
    log("conditions: " + ", ".join(f"{n} {k}" for k, n in sorted(by.items())) +
        f" ({len(out)} games)")
    for m in missing:
        log(f"conditions: missing venue: {m}")
    for m in errors:
        log(f"conditions: Worker error: {m}")
    return payload


def load():
    try:
        return json.load(open(OUT, encoding="utf-8"))
    except Exception:
        return None


def for_game(data, g):
    """The game's entry as the pages read it: a roofed stadium's forecast is a roof line, whatever
    an older file held (roofed_entry is idempotent)."""
    return roofed_entry(((data or {}).get("games") or {}).get(game_key(g)))


def main():
    d = load()
    if not d:
        print("conditions: no file")
        return 0
    for k, v in d["games"].items():
        print(f"  {k:10} {v['status']:12} {json.dumps(v.get('words'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
