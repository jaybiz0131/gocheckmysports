#!/usr/bin/env python3
"""registry_canary.py: S-5.0, college team pages are permanent (J-9, option (a), ruled October 20, 2026).

Under the standing law that URLs never change, a college team page once built is built every week
after; the set only grows. The registry is data/cfb-teams-built.json. Each check names the break it
exists for and was seen red first (U-9).

  absent   a program absent from the week's forty is still built when it is in the registry: from
           the week's board when the board holds it, its stored identity and "No game this week"
           when it does not; the forty come first and are untouched
  grows    the registry never shrinks: every entry it held is kept, its filled fields unchanged,
           whatever the week's forty; a malformed entry from the published copy is refused
  fifteen  the pages dropped on October 19 are present after the build
  tree     the published registry holds the committed one; every entry has its page and its
           priority sitemap line, and no college page is outside it; the file the build leaves for
           the poller to commit holds the committed one; a program with no game says so

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

REGISTRY_REL = os.path.join("data", "cfb-teams-built.json")

# The pages dropped on October 19. J-9 (docs/JACK.md, 53d8bff) counts fifteen and names two, michigan
# and texas-a-m; no file in the repository lists the fifteen. Asserted here is every program any record
# shows main building before the S-3b.3 build and not after it: the eleven in main's inactives poller
# builds (09ae375, October 19 00:07 UTC, against afd9a1a, 23:03 UTC), the two J-9 names, and the eight
# more of the reconstruction recorded in the registry's own source lines.
DROPPED_OCT19 = [
    "arizona-state", "auburn", "california", "colorado", "florida-state", "michigan-state",
    "mississippi-state", "oklahoma", "oklahoma-state", "virginia", "wisconsin",
    "michigan", "texas-a-m",
    "cincinnati", "iowa-state", "minnesota", "rutgers", "south-carolina", "ucf", "vanderbilt",
    "washington-state",
]


def _team(school, tid, abbr, record, mascot="M", color="#123456"):
    return {"school": school, "full": f"{school} {mascot}", "name": mascot, "mascot": mascot,
            "abbr": abbr, "id": tid, "record": record, "color": color}


def _g(gid, away, home, start="2026-10-24T16:00Z"):
    return {"id": gid, "league": "CFB", "start_utc": start, "venue": "Field X (Town, ST)",
            "network": "ESPN", "state": "pre", "away": away, "home": home}


def unit():
    fails = []
    try:
        import teams
    except ImportError as e:
        return [f"registry: cannot import teams ({e})"]
    need = ("registry_union", "registry_programs", "registry_entries")
    missing = [n for n in need if not hasattr(teams, n)]
    if missing:
        return [f"registry: teams has no {', '.join(missing)}"]
    # absent: forty unranked programs with better records than Michigan fill the forty; Michigan is on
    # the board, Liberty is not
    games = [_g(f"c{i}", _team(f"Better {i}", f"b{i}", f"B{i}", "6-0"), _team(f"Good {i}", f"g{i}", f"G{i}", "5-1"))
             for i in range(20)]
    games.append(_g("m1", _team("Michigan", "130", "MICH", "4-2", "Wolverines", "#00274c"),
                    _team("Rutgers", "164", "RUTG", "2-4", "Scarlet Knights")))
    top = teams.top_programs(None, games, 40)
    if "michigan" in {p["slug"] for p in top}:
        fails.append("absent: the fixture's forty hold Michigan, so it cannot show a registry program built")
    reg = {"programs": [
        {"slug": "michigan", "school": "Michigan", "mascot": "Wolverines", "abbr": "MICH", "id": "130",
         "color": "#00274c", "since": "2026-10-19", "source": "fixture"},
        {"slug": "liberty", "school": "Liberty", "mascot": "Flames", "abbr": "", "id": "", "color": "",
         "since": "2026-10-20", "source": "fixture"},
        {"slug": "better-0", "school": "Better 0", "mascot": "M", "abbr": "B0", "id": "b0", "color": "",
         "since": "2026-10-16", "source": "fixture"}]}
    progs = teams.registry_programs(reg, top, games)
    slugs = [p["slug"] for p in progs]
    if slugs[:len(top)] != [p["slug"] for p in top]:
        fails.append("absent: the week's forty are not first and unchanged in the built set")
    if len(slugs) != len(set(slugs)):
        fails.append("absent: a program is built twice (one in the forty and the registry)")
    by = {p["slug"]: p for p in progs}
    m = by.get("michigan")
    if not m:
        fails.append("absent: Michigan is in the registry and not in the forty, and is not built")
    elif m.get("record") != "4-2" or m.get("id") != "130" or m.get("rank") or m.get("ranked"):
        fails.append(f"absent: Michigan is not drawn from the week's board (record {m.get('record')!r}, "
                     f"id {m.get('id')!r}, rank {m.get('rank')!r})")
    lb = by.get("liberty")
    if not lb:
        fails.append("absent: Liberty is in the registry and on no board, and is not built")
    elif lb.get("record") or lb.get("mascot") != "Flames" or lb.get("school") != "Liberty":
        fails.append(f"absent: Liberty, on no board this week, prints {lb.get('record')!r} as a record or "
                     f"loses its stored name ({lb.get('school')!r} {lb.get('mascot')!r})")
    for k in ("slug", "school", "mascot", "abbr", "id", "color", "record", "rank", "previous", "trend", "ranked"):
        if lb is not None and k not in lb:
            fails.append(f"absent: a registry program lacks the field {k!r} the forty carry")
            break
    # a program the registry holds by school, with no id, takes the board's id when the board holds it
    reg2 = {"programs": [{"slug": "rutgers", "school": "Rutgers", "mascot": "", "abbr": "", "id": "",
                          "color": "", "since": "2026-10-20", "source": "fixture"}]}
    rp = {p["slug"]: p for p in teams.registry_programs(reg2, top, games)}.get("rutgers") or {}
    if rp.get("id") != "164" or rp.get("mascot") != "Scarlet Knights":
        fails.append("absent: a registry program with no stored id is not matched on the board by school")

    # grows
    old = json.loads(json.dumps(reg))
    new = teams.registry_union(old, top, since="2026-10-20", source="build test")
    olds = {e["slug"]: e for e in reg["programs"]}
    news = {e["slug"]: e for e in new.get("programs") or []}
    if not set(olds) <= set(news):
        fails.append(f"grows: the union lost {sorted(set(olds) - set(news))}")
    for s, e in olds.items():
        for k, v in e.items():
            if v not in ("", None) and (news.get(s) or {}).get(k) != v:
                fails.append(f"grows: the union changed {s}'s {k} from {v!r}")
                break
    if not {p["slug"] for p in top} <= set(news):
        fails.append("grows: the week's forty are not all added to the registry")
    added = news.get("good-0") or {}
    if added.get("since") != "2026-10-20" or added.get("source") != "build test" or added.get("id") != "g0":
        fails.append(f"grows: an added program does not carry its identity, date and source: {added}")
    if [e["slug"] for e in new["programs"]] != sorted(news):
        fails.append("grows: the registry is not kept in slug order")
    if len(teams.registry_union(new, [])["programs"]) != len(new["programs"]):
        fails.append("grows: a week with no forty shrank the registry")
    if len(teams.registry_union(new, top[:3])["programs"]) != len(new["programs"]):
        fails.append("grows: a smaller forty shrank the registry")
    if teams.registry_union(old, top) != teams.registry_union(teams.registry_union(old, top), top):
        fails.append("grows: the union is not stable when run twice")
    bad = {"programs": [{"slug": "../etc", "school": "../etc"}, {"slug": "ohio", "school": "Ohio State"},
                        {"slug": "", "school": ""}, "x", {"slug": "toledo", "school": "Toledo", "id": 5}]}
    got = [e["slug"] for e in teams.registry_entries(bad)]
    if got != ["toledo"]:
        fails.append(f"grows: malformed registry entries were accepted: {got}")
    if teams.registry_entries(None) != [] or teams.registry_entries({"programs": "x"}) != []:
        fails.append("grows: an unreadable registry is not read as empty")
    return fails


def _committed(root=HERE):
    """The registry as committed at HEAD, or None."""
    r = subprocess.run(["git", "show", f"HEAD:{REGISTRY_REL}"], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def _read(tree, rel):
    try:
        return open(os.path.join(tree, rel), encoding="utf-8").read()
    except OSError:
        return None


def tree_checks(tree):
    fails = []
    import teams
    committed = _committed()
    if committed is None:
        return [f"tree: {REGISTRY_REL} is not committed"]
    want = {e["slug"] for e in teams.registry_entries(committed)}
    if not want:
        fails.append(f"tree: the committed {REGISTRY_REL} holds no program")
    pub = _read(tree, "data/cfb-teams-built.json")
    got = {e["slug"] for e in teams.registry_entries(json.loads(pub))} if pub else set()
    if not pub:
        fails.append("tree: the build published no /data/cfb-teams-built.json")
    elif not want <= got:
        fails.append(f"tree: the published registry lost {sorted(want - got)[:6]}")
    left = _read(HERE, REGISTRY_REL)
    if left is None or not want <= {e["slug"] for e in teams.registry_entries(json.loads(left))}:
        fails.append(f"tree: the build left a {REGISTRY_REL} that does not hold the committed one")
    elif pub and {e["slug"] for e in teams.registry_entries(json.loads(left))} != got:
        fails.append(f"tree: the {REGISTRY_REL} the build left is not the registry it published")
    cdir = os.path.join(tree, "teams", "cfb")
    pages = {f[:-5] for f in os.listdir(cdir) if f.endswith(".html")} if os.path.isdir(cdir) else set()
    if got - pages:
        fails.append(f"tree: {len(got - pages)} registry programs have no page: {sorted(got - pages)[:6]}")
    if pages - got:
        fails.append(f"tree: {len(pages - got)} college pages are outside the registry: {sorted(pages - got)[:6]}")
    gone = [s for s in DROPPED_OCT19 if s not in pages]
    if gone:
        fails.append(f"fifteen: pages dropped on October 19 are not built: {gone}")
    sm = _read(tree, "sitemap-priority.xml") or ""
    nosm = sorted(s for s in got if f"/teams/cfb/{s}<" not in sm)
    if nosm:
        fails.append(f"tree: {len(nosm)} registry pages are not in the priority sitemap: {nosm[:6]}")
    for s in sorted(pages):
        h = _read(tree, f"teams/cfb/{s}.html") or ""
        if 'class="tms-row' not in h and "No game this week" not in h:
            fails.append(f"tree: {s} has no schedule row and does not say No game this week")
            break
    # a program on no board this week, rendered from the build's own state
    try:
        import site_build as sb
        sb._page_reset()
        h = sb.render_college_page({"slug": "zz-absent", "school": "Zz Absent", "mascot": "Testers", "abbr": "",
                                    "id": "", "color": "", "record": "", "rank": None, "previous": None,
                                    "trend": "", "ranked": False}, [], "")
        if "No game this week" not in h or "Zz Absent Testers" not in h:
            fails.append("absent: a registry program with no game does not render No game this week under its name")
    except Exception as e:
        fails.append(f"absent: rendering a program with no game raised {type(e).__name__}: {e}")
    return fails


def registry_canary(tree=None):
    fails = unit()
    if tree:
        fails += tree_checks(tree)
    return fails


if __name__ == "__main__":
    fs = registry_canary()
    for f in fs:
        print("FAIL", f)
    print("registry canary (unit):", "PASS" if not fs else f"{len(fs)} FAIL")
    sys.exit(1 if fs else 0)
