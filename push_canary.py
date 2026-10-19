#!/usr/bin/env python3
"""push_canary.py: S-3b item 4, web push from the site.

Offline: no network, no model, no key (the key fixture below is a shape, not a key, and the real
keys are held only in the hosting environment). Each check names the break it exists for and was seen
red first (U-9).

  rule      the one-push rule from a fixture (fixtures/push_fixture.json): hourly ticks over eleven
            days send each device each of its teams' games once, at 7 PM ET the evening before by the
            Eastern calendar (across the November 1 clock change, and a 8:20 PM ET kickoff that is
            the next day in UTC), and never a second. Proved twice: by the Python twin (push_select.py)
            and, where Node is present, by the relay's own code (netlify/test/push.test.mjs, 21
            checks: the rule, a retry that still lands once, a gone device, the crypto against an
            independent reader, the 503 with no key, the subscribe route).
  absent    a build without the key (the gate's build, which clears it) has no push markup, no push
            script, no push handler in the worker and no data file, in any page; and a malformed key is
            no key
  present   with a key the team pages carry the button and the script, hidden until the browser can
            receive a push, the worker carries the handlers, the game index lists only games that
            have a page, a kickoff and a team that can be followed; no host beyond the site's own
  files     the one dependency is pinned exactly, the function directory is declared, nothing in the
            relay reads a key from a file, the 180 day expiry and the endpoint allow list exist

Called from verify_pipeline.layer1_canary(); returns failure strings.
"""

import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# A shape fixture: 0x04 then 64 bytes, base64url. It is not a key and no private half exists.
FIX_KEY = "BAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE"
ENV = "WEB_PUSH_VAPID_PUBLIC_KEY"
MARKERS = ("data-tpush", "tpush-note", "/api/push", "gcms-push-", "PushManager", "data-vapid")
NODE_MIN_CHECKS = 20


def check_rule():
    fails = []
    import push_select as ps
    fx = json.load(open(os.path.join(HERE, "fixtures", "push_fixture.json"), encoding="utf-8"))
    got = ps.simulate(fx)
    if got != sorted(fx["expected"]):
        fails.append(f"push rule (python twin): the fixture run sent {got}, expected {sorted(fx['expected'])}")
    pairs = [(a, b) for a, b, _t in got]
    if len(pairs) != len(set(pairs)) or not pairs:
        fails.append("push rule (python twin): a device was sent the same game twice, or the run sent nothing")
    # a sent mark stops a repeat even inside the window
    g = fx["games"][0]
    import datetime
    now = datetime.datetime(2026, 10, 24, 23, 0, tzinfo=datetime.timezone.utc)
    if ps.select_sends([{"id": "a", "teams": g["teams"][:1], "sent": {g["id"]: "x"}}], [g], now):
        fails.append("push rule (python twin): a game already sent to a device was selected again")
    if not ps.select_sends([{"id": "a", "teams": g["teams"][:1], "sent": {}}], [g], now):
        fails.append("push rule (python twin): the window opened at 7 PM ET selected nothing, so the check above proves nothing")
    m = ps.message_for(g, now)
    if "52°" not in m["body"] or "ET" not in m["body"] or not m["url"].startswith("/games/"):
        fails.append(f"push message: the line lost the kickoff in ET or the conditions or the page: {m}")
    node = shutil.which("node")
    if not node:
        print("::warning::push canary: node not found; the relay's JavaScript was not run, and the one-push "
              "rule was checked through its Python twin (push_select.py) only")
        return fails
    for rel in ("netlify/lib/select.mjs", "netlify/lib/tick.mjs", "netlify/lib/webpush.mjs", "netlify/lib/config.mjs",
                "netlify/lib/subscribe.mjs", "netlify/functions/push.mjs", "netlify/functions/push-send.mjs"):
        r = subprocess.run([node, "--check", os.path.join(HERE, rel)], capture_output=True, text=True)
        if r.returncode != 0:
            fails.append(f"push relay: {rel} does not parse: {r.stderr.strip().splitlines()[:1]}")
    env = {k: v for k, v in os.environ.items() if not k.startswith("WEB_PUSH_")}
    try:
        r = subprocess.run([node, os.path.join(HERE, "netlify", "test", "push.test.mjs")], capture_output=True,
                           text=True, timeout=120, env=env, cwd=HERE)
    except subprocess.TimeoutExpired:
        return fails + ["push relay (node): the test did not finish in 120 seconds"]
    lines = r.stdout.splitlines()
    n_ok = sum(1 for l in lines if l.startswith("ok   "))
    bad = [l for l in lines if l.startswith("FAIL")]
    if r.returncode != 0 or bad:
        fails.append(f"push relay (node): exit {r.returncode}, failing: {bad or r.stderr.strip().splitlines()[:2]}")
    if n_ok < NODE_MIN_CHECKS:
        fails.append(f"push relay (node): only {n_ok} check(s) ran, expected at least {NODE_MIN_CHECKS}; "
                     f"a test file that runs nothing is not a test")
    print(f"push canary: relay JavaScript run through node {subprocess.run([node, '-v'], capture_output=True, text=True).stdout.strip()}, "
          f"{n_ok} check(s) ok; python twin sent {len(got)} push(es) on the same fixture")
    return fails


def check_absent(out):
    fails = []
    import site_build as sb
    if os.environ.get(ENV):
        fails.append(f"push absent: {ENV} is set in the canary's own environment, so the keyless checks prove nothing")
    if sb.push_key() != "":
        fails.append("push absent: push_key() is not empty with no key in the environment")
    for bad in ("", "short", "A" * 87, FIX_KEY[:-4]):
        os.environ[ENV] = bad
        try:
            if sb.push_key() != "":
                fails.append(f"push absent: a malformed key ({bad[:12]!r}) was accepted as the public key")
        finally:
            os.environ.pop(ENV, None)
    if not out or not os.path.isdir(out):
        return fails + ["push absent: the gate's build is missing, so no page was checked"]
    pages = teams = 0
    seen = {}
    for root, _d, files in os.walk(out):
        for fn in files:
            if not fn.endswith((".html", ".js")):
                continue
            fp = os.path.join(root, fn)
            txt = open(fp, encoding="utf-8", errors="replace").read()
            pages += fn.endswith(".html")
            teams += "/teams/" in fp and fn.endswith(".html")
            rel = os.path.relpath(fp, out)
            for m in MARKERS + (("showNotification", "'push'") if fn == "sw.js" else ()):
                if m in txt:
                    seen.setdefault(m, []).append(rel)
    for m, where in sorted(seen.items()):
        fails.append(f"push absent: {len(where)} file(s) carry {m!r} in a build with no key, first {where[0]}")
    if teams < 2 or pages < 10:
        fails.append(f"push absent: only {pages} page(s) and {teams} team page(s) were read, so the check proves nothing")
    if not os.path.exists(os.path.join(out, "sw.js")):
        fails.append("push absent: the build wrote no sw.js, so its handlers were not checked")
    if os.path.exists(os.path.join(out, "data", "push-games.json")):
        fails.append("push absent: the build published /data/push-games.json with no key")
    return fails


def _fx_games(sb):
    import datetime
    sb._NOW_CACHE = datetime.datetime(2026, 10, 15, 13, 0, tzinfo=datetime.timezone.utc)

    def g(gid, st, kick, net, away, home, **kw):
        d = {"id": gid, "league": "NFL", "state": st, "start_utc": kick, "network": net,
             "status_short": kw.pop("status_short", ""),
             "away": {"abbr": away, "full": kw.pop("af", away + " Team")},
             "home": {"abbr": home, "full": kw.pop("hf", home + " Team")}}
        d.update(kw)
        return d
    return [g("9001", "pre", "2026-10-18T17:00Z", "CBS", "KC", "BUF", af="Kansas City Chiefs", hf="Buffalo Bills"),
            g("9002", "pre", "2026-10-18T20:20Z", "", "DAL", "PHI"),
            g("9003", "in", "2026-10-18T13:00Z", "FOX", "CHI", "GB"),
            g("9004", "post", "2026-10-15T00:15Z", "NBC", "SEA", "DEN"),
            g("9005", "pre", "2026-10-18T17:00Z", "FOX", "LON", "PAR"),
            g("9006", "pre", "2026-10-18T20:00Z", "ESPN", "MIA", "NE", status_short="TBD"),
            g("9007", "pre", "2026-10-18T20:00Z", "ESPN", "ARI", "LAR", status_short="Postponed")]


def check_present(out):
    fails = []
    import site_build as sb
    os.environ[ENV] = FIX_KEY
    was = (sb.SB_DATA, sb.CX_DATA, sb.TEAM_DATA, sb._NOW_CACHE, sb.MANIFEST if hasattr(sb, "MANIFEST") else None)
    try:
        if sb.push_key() != FIX_KEY:
            return ["push present: a well formed key was not accepted"]
        btn, note = sb.push_ui("nfl:KC", "KC")
        for want in ('data-tpush="nfl:KC"', f'data-vapid="{FIX_KEY}"', 'aria-pressed="false" hidden>'):
            if want not in btn:
                fails.append(f"push present: the team button lacks {want!r} (hidden until the browser can receive a push)")
        for want in ("tpush-note", "No account", "/api/push", "requestPermission"):
            if want not in note:
                fails.append(f"push present: the team note and script lack {want!r}")
        if "hidden" not in note.split("<script>")[0]:
            fails.append("push present: the note is not hidden until the browser can receive a push")
        if sb.push_ui("", "x") != ("", ""):
            fails.append("push present: a button was drawn for no team")
        if "showNotification" not in sb.sw_source("v", ["/a"]) or "notificationclick" not in sb.sw_source("v", ["/a"]):
            fails.append("push present: the worker lacks the push and click handlers with a key")
        # a team page and a college page from the gate build's state
        tm_abbr = next(iter(sorted(((sb.TEAM_DATA or {}).get("teams") or {}))), None)
        if tm_abbr:
            sb._page_reset()
            page = sb.render_team_page(sb.TEAM_DATA["teams"][tm_abbr], [], "")
            if f'data-tpush="nfl:{tm_abbr}"' not in page or "navigator.serviceWorker" not in page:
                fails.append(f"push present: the {tm_abbr} team page lacks its button or script with a key")
            if page.count("data-tpush=") != 1 or page.count("<button") < 2:
                fails.append(f"push present: the {tm_abbr} page has the wrong number of push buttons")
            import gamepage_canary as gp
            bad = gp.runtime_hosts(page) - gp.ALLOWED_HOSTS
            if bad:
                fails.append(f"push present: the team page reads {sorted(bad)} at runtime")
            if "VAPID_PRIVATE" in page:
                fails.append("push present: the private key's name is on a team page; only the public key reaches a page")
        else:
            fails.append("push present: the gate build holds no NFL team, so the team page was not rendered")
        if sb.CFB_PROGRAMS:
            prog = sb.CFB_PROGRAMS[0]
            sb._page_reset()
            page = sb.render_college_page(prog, [], "")
            if f'data-tpush="cfb:{prog["slug"]}"' not in page:
                fails.append("push present: a college program page lacks its button with a key")
        # the game index, from fixtures
        sb.SB_DATA = {"leagues": [{"league": "NFL", "games": _fx_games(sb)}]}
        sb.TEAM_DATA = {"teams": {a: {"name": a} for a in ("KC", "BUF", "DAL", "PHI", "CHI", "GB", "SEA", "DEN", "MIA", "NE", "ARI", "LAR")}}
        sb.CX_DATA = {"built_at": "2026-10-15T12:00:00Z", "games": {
            "9001": {"status": "forecast", "kickoff": "2026-10-18T17:00Z", "nws": {"read_at": "2026-10-15T11:00:00Z"},
                     "kickoff_hour": {"temp_f": 52.4, "pop_pct": 20, "wind_mph": 12,
                                      "wind": {"text": "12 mph"}}},
            "9002": {"status": "indoor", "words": {"line": "Indoor"}}}}
        import build_manifest as bm
        sb.MANIFEST = bm.build(sb._build_now(), None, None)
        doc = sb.push_games_doc()
        ids = [x["id"] for x in doc["games"]]
        if ids != ["9001", "9002"]:
            fails.append(f"push present: the game index lists {ids}; expected the scheduled games with a page, a kickoff "
                         f"and a followable team (9001, 9002), not the in-progress, final, TBD, postponed or "
                         f"no-team ones")
        by = {x["id"]: x for x in doc["games"]}
        a = by.get("9001") or {}
        if a.get("lead") != "Kickoff 1:00 PM ET on CBS." or a.get("cond") != "52°, wind 12 mph, rain 20%" \
                or a.get("teams") != ["nfl:KC", "nfl:BUF"] or a.get("path") != "/games/9001.html" \
                or a.get("title") != "Kansas City Chiefs at Buffalo Bills" or a.get("cond_at") != "2026-10-15T11:00:00Z" \
                or a.get("kick") != "2026-10-18T17:00:00Z":
            fails.append(f"push present: the index line for the first game is wrong: {a}")
        b = by.get("9002") or {}
        if b.get("lead") != "Kickoff 4:20 PM ET." or b.get("cond") != "Dome":
            fails.append(f"push present: the game with no network or a dome is wrong: {b}")
        for x in doc["games"]:
            for t in (x["title"], x["lead"], x["cond"]):
                if "\u2014" in t or re.search(r"\blive\b", t, re.I):
                    fails.append(f"push present: copy law, {t!r}")
    except Exception as e:
        fails.append(f"push present: raised {type(e).__name__}: {e}")
    finally:
        os.environ.pop(ENV, None)
        sb.SB_DATA, sb.CX_DATA, sb.TEAM_DATA, sb._NOW_CACHE = was[:4]
        if was[4] is not None:
            sb.MANIFEST = was[4]
    return fails


def check_files():
    fails = []
    pk = json.load(open(os.path.join(HERE, "package.json"), encoding="utf-8"))
    deps = pk.get("dependencies") or {}
    if list(deps) != ["@netlify/blobs"] or not re.fullmatch(r"\d+\.\d+\.\d+", deps.get("@netlify/blobs", "")):
        fails.append(f"push files: package.json must pin exactly one dependency, @netlify/blobs, to an exact version: {deps}")
    lock = open(os.path.join(HERE, "package-lock.json"), encoding="utf-8").read()
    if f'"node_modules/@netlify/blobs"' not in lock or f'"version": "{deps.get("@netlify/blobs")}"' not in lock:
        fails.append("push files: package-lock.json does not hold the pinned version")
    toml = open(os.path.join(HERE, "netlify.toml"), encoding="utf-8").read()
    if not re.search(r'\[functions\]\s*\n\s*directory\s*=\s*"netlify/functions"', toml):
        fails.append("push files: netlify.toml does not declare the functions directory")
    for rel in ("netlify/lib/config.mjs", "netlify/lib/select.mjs", "netlify/lib/tick.mjs", "netlify/lib/webpush.mjs",
                "netlify/lib/subscribe.mjs", "netlify/functions/push.mjs", "netlify/functions/push-send.mjs"):
        txt = open(os.path.join(HERE, rel), encoding="utf-8").read()
        if re.search(r"node:fs|require\(['\"]fs|from ['\"]fs|readFile|writeFile|dotenv|['\"]\.env", txt):
            fails.append(f"push files: {rel} touches the filesystem or a dotenv file; a key is read from the environment only")
        if "\u2014" in txt or re.search(r"\blive\b", re.sub(r"//.*|/\*.*?\*/", "", txt, flags=re.S), re.I):
            fails.append(f"push files: {rel} breaks the copy law (an em dash or the word live)")
    cfg = open(os.path.join(HERE, "netlify/lib/config.mjs"), encoding="utf-8").read()
    for name in ("WEB_PUSH_VAPID_PUBLIC_KEY", "WEB_PUSH_VAPID_PRIVATE_KEY"):
        if f"env.{name}" not in cfg:
            fails.append(f"push files: config.mjs does not read {name} from the environment")
    sub = open(os.path.join(HERE, "netlify/lib/subscribe.mjs"), encoding="utf-8").read()
    if "fcm\\.googleapis\\.com" not in sub or "MAX_TEAMS" not in sub:
        fails.append("push files: the endpoint allow list or the team cap is gone from the subscribe route")
    return fails


def push_canary(out=None):
    fails = []
    fails.extend(check_rule())
    fails.extend(check_files())
    fails.extend(check_absent(out))
    fails.extend(check_present(out))
    return fails


if __name__ == "__main__":
    f = push_canary(sys.argv[1] if len(sys.argv) > 1 else None)
    print("\n".join(f) or "push canary: ok")
    sys.exit(1 if f else 0)
