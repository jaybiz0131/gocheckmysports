#!/usr/bin/env python3
"""kickoff_weather.py: NWS conditions at kickoff, for outdoor games (S-B5).

WHY NOT THE SCOREBOARD'S OWN WEATHER, which is right there in the payload. Measured
2026-09-13: it carries temperature, a condition id and a gust, and NO SUSTAINED WIND at
all, which is the one number S-B5 asks us to flag on. It is AccuWeather, not a source
this family would cite. And its displayValue and conditionId are transposed between
games: one returns displayValue "1" with conditionId "Sunny", another the reverse, so
neither field can be trusted to hold what its name says. Ruled 2026-09-13: weather comes
from NWS through GoCheckMyWeather only, and the feed's weather is not read.

NWS gives what the flag needs, hourly, free, no key: temperature, sustained windSpeed,
probabilityOfPrecipitation and a short forecast, in 156 hourly periods.

DOMES ARE NOT FORECAST. venues.json carries the roof, and an indoor venue says
"indoors" rather than reporting the weather outside a closed building. The roof is a
boolean in the league's own data; nothing distinguishes a fixed dome from a retractable
roof that happens to be open, so neither does this.

USAGE  python3 kickoff_weather.py            refresh
       python3 kickoff_weather.py --report   read the committed file
"""

import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "site", "data", "kickoff-weather.json")
VENUES = os.path.join(HERE, "site", "data", "venues.json")
W2W = os.path.join(HERE, "site", "data", "where-to-watch.json")
# NWS asks for a contactable agent and it is only polite to give one.
UA = "GoCheckMyWeather (desk@gocheckmysports.com)"
TIMEOUT = 20
STALE_HOURS = 12
WIND_FLAG_MPH = 15          # S-B5: above this the card carries a flag


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _venues():
    try:
        return (json.load(open(VENUES, encoding="utf-8")) or {}).get("venues") or {}
    except Exception:
        return {}


def _mph(s):
    """NWS writes wind as a string: "5 mph", "10 to 15 mph". Take the top of a range,
    because that is the number a flag should answer to."""
    import re as _re
    n = [int(x) for x in _re.findall(r"\d+", str(s or ""))]
    return max(n) if n else None


def _at_kickoff(periods, kickoff_utc):
    """The hourly period containing kickoff. No interpolation: NWS publishes hours and
    we report the hour, or nothing."""
    try:
        k = datetime.datetime.strptime(kickoff_utc, "%Y-%m-%dT%H:%MZ").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    for p in periods:
        try:
            a = datetime.datetime.fromisoformat(p["startTime"])
            b = datetime.datetime.fromisoformat(p["endTime"])
        except Exception:
            continue
        if a <= k < b:
            return p
    return None


def refresh():
    venues = _venues()
    if not venues:
        print("kickoff_weather: no venues.json; nothing to do")
        return None
    try:
        w2w = json.load(open(W2W, encoding="utf-8"))
    except Exception:
        print("kickoff_weather: no schedule to read; nothing to do")
        return None

    # venue lookup by home team abbreviation, via the venue name the schedule does not
    # carry. The schedule has team ids, so match venue to home team through venues.json
    # order: it was built one venue per team, in team order.
    out, grid_cache = {}, {}
    games = [g for wk in (w2w.get("weeks") or []) for g in (wk.get("games") or [])]
    for g in games:
        vid = g.get("venue_id") or ""
        v = venues.get(str(vid))
        if not v:
            continue
        key = g.get("id") or f'{g.get("away")}@{g.get("home")}'
        if v.get("indoor"):
            out[key] = {"indoors": True, "venue": v.get("name")}
            continue
        lat, lon = v.get("lat"), v.get("lon")
        if lat is None or lon is None:
            continue
        gk = f"{lat:.3f},{lon:.3f}"
        try:
            if gk not in grid_cache:
                pt = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
                grid_cache[gk] = (pt.get("properties") or {}).get("forecastHourly")
            url = grid_cache[gk]
            if not url:
                continue
            per = (_get(url).get("properties") or {}).get("periods") or []
        except Exception:
            continue
        p = _at_kickoff(per, g.get("kickoff_utc") or "")
        if not p:
            continue
        wind = _mph(p.get("windSpeed"))
        out[key] = {
            "indoors": False, "venue": v.get("name"),
            "temp_f": p.get("temperature"),
            "wind_mph": wind, "wind_dir": p.get("windDirection"),
            "windy": bool(wind and wind > WIND_FLAG_MPH),
            "precip_pct": ((p.get("probabilityOfPrecipitation") or {}).get("value")),
            "summary": p.get("shortForecast"),
            "for_hour": p.get("startTime"),
        }
    if not out:
        print("kickoff_weather: nothing resolved; committed file left alone")
        return None
    payload = {"fetched_at": datetime.datetime.now(datetime.timezone.utc)
                                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "National Weather Service, via GoCheckMyWeather",
               "games": out}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    dome = sum(1 for v in out.values() if v.get("indoors"))
    windy = sum(1 for v in out.values() if v.get("windy"))
    print(f"kickoff_weather: {len(out)} game(s), {dome} indoors, {windy} above "
          f"{WIND_FLAG_MPH} mph")
    return payload


def load():
    try:
        d = json.load(open(OUT, encoding="utf-8"))
        t = datetime.datetime.strptime(d["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600 > STALE_HOURS:
        return None
    return d


def main():
    d = load() if "--report" in sys.argv else refresh()
    if not d:
        return 0
    for k, v in list(d["games"].items())[:8]:
        if v.get("indoors"):
            print(f"  {k:14} indoors ({v.get('venue')})")
        else:
            print(f"  {k:14} {v.get('temp_f')}F wind {v.get('wind_mph')} mph"
                  f"{' FLAG' if v.get('windy') else ''}, precip {v.get('precip_pct')}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
