#!/usr/bin/env python3
"""
verify_pipeline.py: self-verify the GoCheckMySports pipeline. Same two-layer discipline as
the Pet recall verifier (_pipeline/verify_curated.py): an offline hard gate that blocks, and
a live notify-only check that never blocks a run.

  LAYER 1  offline canary (HARD FAIL, exit 1, blocks promotion). Proves the pipeline is wired
    and fails closed, with NO network and NO API key:
     - config.json, shill_rules.json well-formed; models carry no temperature/top_p/top_k
       (those 400 on the current model family).
     - prompts exist and carry their load-bearing guardrail tokens (editor: shill/rank;
       verifier: the three verdicts + adversarial; writer: DRAFT + not betting advice +
       human take).
     - shill canary: the deterministic belt scores a known tout headline as rejected, a
       sportsbook promo item as flagged, and a primary-source real story as clean.
     - dedupe canary: two near-identical headlines collapse into one cluster.
     - full offline replay end-to-end (aggregate->editor->verifier->writer->digest) over the
       fixture: exact cluster count, exact editor split, all three verdicts present, only
       VERIFIED+REVIEW drafted, every draft DRAFT-tagged with an empty human_take + disclaimer.
     - fail-closed canaries: a missing API key fails the LLM call closed; a REJECT/hold story
       is never published; a replay-mode approval is refused by publish.
    Any deviation -> ::error:: + exit 1.

  LAYER 2  live source check (NOTIFY-ONLY, exit 3 on content mismatch, never blocks a run).
    Fetches each configured RSS feed and asserts HTTP 200 + looks-like-a-feed + at least one
    item on two reads (a valid channel serving zero items is a dead lane that reads as
    healthy). A broken feed -> ::error:: + exit 3 (CI marks it failed / opens an issue) but
    never blocks. A network error -> ::warning:: only.

USAGE
  python3 verify_pipeline.py canary     # Layer 1 only (exit 0 pass / 1 fail)
  python3 verify_pipeline.py sources    # Layer 2 only (exit 0 pass / 3 mismatch)
  python3 verify_pipeline.py            # both; only Layer 1 affects the exit code
"""

import inspect
import glob
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common
import shill as shill_mod
import llm as llmlib

FIXTURE = os.path.join(HERE, "fixtures", "sample_feed.xml")


def gh(level, msg):
    print(f"::{level}::{msg}")


# ---- Layer 1 -----------------------------------------------------------------

def _check(cond, fails, msg):
    if not cond:
        fails.append(msg)


def _undefined_name_canary():
    """Every pipeline module must not reference a name it never binds.

    THIS EXISTS BECAUSE THE CANARY BELOW IT PASSED WHILE THE DESK WAS DOWN. On 2026-07-31 a
    scripted port added two call sites to autopilot.main() and left their `def`s behind. The
    dedupe canary was green, the replay was green, the offline gate was green, and every
    scheduled run died with `NameError: name '_rehash_of' is not defined` because the replay
    fixtures are all held by an earlier gate and never reach that branch. Two desks were down
    for two runs each before anyone read a traceback.

    A canary that exercises functions cannot see a caller that names a function which does
    not exist. Nothing dynamic is needed to catch it: the name is absent at parse time. This
    walks the AST of every module the pipeline actually runs and asserts that every loaded
    name is bound somewhere in that module, imported, or a builtin.

    Deliberately stdlib-only. `ruff check --select F821` finds the same thing and is better at
    it, but the canary is the hard gate in front of every run and must not depend on a tool
    the runner may not have installed. Scope-insensitive on purpose: it collects every
    binding anywhere in the file, so it cannot report a name that is merely out of scope. It
    catches the absent, which is the failure that took the desks down."""
    import ast
    import builtins
    fails = []
    mods = ["aggregate", "autopilot", "editor", "verifier", "researcher", "writer",
            "approver", "publish", "digest", "run", "site_build", "dedupe", "common"]
    for m in mods:
        path = os.path.join(HERE, f"{m}.py")
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
        except SyntaxError as e:
            fails.append(f"undefined-name: {m}.py does not parse ({e})")
            continue
        bound = set(dir(builtins))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                bound.add(n.id)
            elif isinstance(n, ast.arg):
                bound.add(n.arg)
            elif isinstance(n, ast.alias):
                bound.add((n.asname or n.name).split(".")[0])
            elif isinstance(n, ast.ExceptHandler) and n.name:
                bound.add(n.name)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                bound.update(n.names)
        used = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        missing = sorted(u for u in used - bound if not u.startswith("__"))
        _check(not missing, fails,
               f"undefined-name: {m}.py references {missing} which it never defines or "
               f"imports. Every scheduled run that reaches those lines dies with a "
               f"NameError, and no replay fixture has to reach them for that to be true.")
    return fails



def _one_definition_canary():
    """No pipeline module may define the same top-level name twice.

    Python takes the last definition and says nothing, so a duplicated function is invisible
    at import, at runtime, and to the undefined-name gate above, which only asks whether a
    name is bound at all. A scripted port on 2026-07-31 copied "everything from this function
    to end of file" out of one desk and pasted it into two others, carrying that desk's run()
    and main() along with it. Both desks then held two run() definitions, one referencing a
    module that does not exist on them, and every canary stayed green because the surviving
    definition happened to be the right one. It was luck, not design."""
    import ast
    fails = []
    mods = ["aggregate", "autopilot", "editor", "verifier", "researcher", "writer",
            "approver", "publish", "digest", "run", "site_build", "dedupe", "common", "llm"]
    for m in mods:
        path = os.path.join(HERE, f"{m}.py")
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
        except SyntaxError:
            continue  # the undefined-name canary already reports this
        seen, dupes = {}, []
        for node in tree.body:  # top level only; a nested helper may legitimately repeat
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in seen:
                    dupes.append(f"{node.name} (lines {seen[node.name]} and {node.lineno})")
                seen[node.name] = node.lineno
        _check(not dupes, fails,
               f"one-definition: {m}.py defines {'; '.join(dupes)} more than once at top "
               f"level. Python silently keeps the last, so half this file is dead code and "
               f"which half runs is an accident of ordering.")
    return fails

def _corpus_integrity_canary():
    """Two data defects the event matcher structurally cannot see.

    dedupe.py answers "is this the same STORY", which is the hard question and it
    answers it well. These two are not that question, which is why they slipped
    past every existing guard:

      DUPLICATE SLUGS. Two content records naming the same slug write the same
      file, and whichever builds last silently wins. The other story is gone with
      no error, no log line and no missing page to notice. Five on this desk when
      first measured, 2026-08-28.

      CIRCULAR update_of. Two records each naming the other as the story it
      updates, so neither is the origin. "Develops our earlier reporting" then
      points in a loop, and dupe_audit's canonical suggestion has no earliest
      match to anchor to.

    Reported here rather than in dedupe.py because they are corpus hygiene, not
    event similarity, and because dedupe.py is a synchronised chassis copy across
    three repos: it should not grow a second responsibility.
    """
    fails = []
    # BASELINED, and deliberately. This is a HARD GATE: adding it with a backlog
    # of known defects would stop the desk publishing on the first run, which is
    # exactly how a dated fixture took all three desks down for two days. So the
    # defects that already existed when the check was written are recorded in
    # corpus-baseline.json and reported without blocking, while anything NEW
    # fails immediately. Clearing an entry from the baseline is how the backlog
    # gets retired; the file should only ever shrink.
    baseline = set()
    _bl = os.path.join(HERE, "corpus-baseline.json")
    if os.path.exists(_bl):
        try:
            baseline = set(json.load(open(_bl, encoding="utf-8")).get("known", []))
        except Exception:
            baseline = set()

    def _report(key, msg):
        if key in baseline:
            gh("notice", "corpus (baselined, not blocking): " + msg)
        else:
            _check(False, fails, msg)

    recs = []
    for p in glob.glob(os.path.join(HERE, "site", "content", "*.json")):
        try:
            recs.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            continue
    live = [r for r in recs if r.get("slug") and not r.get("example")]

    seen = {}
    for r in live:
        seen.setdefault(r["slug"], []).append(r)
    dupes = sorted(s for s, v in seen.items() if len(v) > 1)
    for slug in dupes:
        _report("slug:" + slug,
                "corpus: %d records share slug '%s' (one silently overwrites the other)"
                % (len(seen[slug]), slug[:58]))

    upd = {}
    for r in live:
        upd.setdefault(r["slug"], r.get("update_of") or "")
    circular = sorted({tuple(sorted((s, u))) for s, u in upd.items()
                       if u and upd.get(u) == s})
    for a, b in circular:
        _report("circular:%s|%s" % (a, b),
                "corpus: circular update_of, '%s' and '%s' each update the other"
                % (a[:34], b[:34]))
    return fails


# The desk's own furniture: pages this desk writes end to end. Story bodies are not
# here on purpose, because a source may be quoted using a date form the house does not
# use and a quotation is not ours to restyle.
CHROME_PAGES = ("index.html", "scores.html", "wire.html", "news.html", "archive.html",
                "method.html", "about.html", "standards.html",
                "fantasy/index.html", "fantasy/inactives.html", "fantasy/injuries.html")
# NOT bottom-line.html. That page is PROSE the desk writes about the day's stories, in
# unclassed paragraphs, and its dates are sentences: "sentencing set for 29 September".
# A lint that rewrote those would be editing copy, which is the line destyle was already
# ruled back from once. The writer's own date order is a job at the writer, not a
# find-and-replace on a rendered page, and it is written down here so the next reader
# knows the omission is a decision and not an oversight.


def _us_date_canary():
    """US date order on the desk's own chrome. Owner ruling, 21 September 2026.

    The Board stamped itself "21 Sep 2026" and the Wire's day headers read "SUNDAY 20
    SEPTEMBER". The audience is American and reads month first, so those are "Sep 21,
    2026" and "Sunday, September 20". Both were seen live rather than in review, which
    is why this is a check and not a note.

    CHROME ONLY, and deliberately. A story's own body may quote a source who wrote a
    date the other way round, and rewriting a quotation to match house style is a thing
    this desk has already ruled against once (see destyle). What the desk controls is
    its own furniture, and that is what this reads.
    """
    import os as _os
    import re as _re
    fails = []
    pub = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "site", "publish")
    if not _os.path.isdir(pub):
        return fails
    months = ("January|February|March|April|May|June|July|August|September|October|"
              "November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec")
    rx = _re.compile(r"\b(\d{1,2})\s+(" + months + r")\b")
    tag = _re.compile(r"<[^>]+>")
    for rel in CHROME_PAGES:
        fp = _os.path.join(pub, rel)
        if not _os.path.exists(fp):
            continue
        html = open(fp, encoding="utf-8", errors="ignore").read()
        # Strip <script> and <style> wholesale: a cron line or a JS date format is not
        # reader-facing copy and would report a date nobody sees.
        html = _re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
        # A LISTING PAGE IS NOT ALL FURNITURE. The archive and the front page carry
        # story headlines and summaries, which are the writers' words and may quote a
        # source's own date form. The docstring above says chrome only and this is what
        # makes that true: story blocks and links into /articles/ come out before the
        # scan, so the check reads the desk's furniture and not the desk's journalism.
        html = _re.sub(r"(?is)<article\b.*?</article>", " ", html)
        html = _re.sub(r'(?is)<a[^>]+href="/articles/[^"]*"[^>]*>.*?</a>', " ", html)
        html = _re.sub(r'(?is)<a[^>]+href="/edition/[^"]*"[^>]*>.*?</a>', " ", html)
        text = tag.sub(" ", html)
        for m in rx.finditer(text):
            around = text[max(0, m.start() - 40):m.end() + 20].strip()
            fails.append(f"US date canary: {rel} renders \"{m.group(0)}\" in day-month "
                         f"order; the audience reads month first. Near: "
                         f"{' '.join(around.split())[:90]}")
            break
    return fails


def layer1_canary():
    fails = []
    fails.extend(_us_date_canary())
    # FIRST, because it is the cheapest and it catches the class that took two
    # desks down while every other canary here stayed green.
    fails.extend(_undefined_name_canary())
    fails.extend(_one_definition_canary())
    # PORTED FROM THE NEWS DESK 2026-08-29: catches two classes that shipped
    # on every desk and were invisible to every other check here, duplicate
    # slugs (two files silently sharing one URL) and circular or
    # self-referential update_of left behind by a retirement.
    fails.extend(_corpus_integrity_canary())
    cfg = common.load_config()

    # config + models
    for stage in ("editor", "verifier", "writer"):
        mc = cfg["models"].get(stage, {})
        _check(mc.get("model"), fails, f"config: models.{stage}.model missing")
        for bad in ("temperature", "top_p", "top_k"):
            _check(bad not in mc, fails, f"config: models.{stage} sets '{bad}' (rejected by the model API)")
    _check(cfg["publish"]["require_human_approval"] is True, fails,
           "config: publish.require_human_approval must be true (the human gate is load-bearing)")
    _check("REJECT" in cfg["publish"]["never_publish_verdict"], fails,
           "config: REJECT must be in never_publish_verdict")

    # shill rules
    rules = shill_mod.load_rules()
    _check(rules.get("tells"), fails, "shill_rules: no tells")
    for t in rules.get("tells", []):
        for f in ("id", "pattern", "weight", "reason"):
            _check(f in t, fails, f"shill_rules: tell missing '{f}': {t.get('id','?')}")

    # prompts carry their guardrails
    guards = {
        "editor.md": ["shill", "rank", "JSON"],
        "verifier.md": ["VERIFIED", "NEEDS-HUMAN-REVIEW", "REJECT", "adversarial"],
        "researcher.md": ["brief", "confidence", "bear_case", "unconfirmed", "thin"],
        "writer.md": ["DRAFT", "betting advice", "human take", "human_take", "brief",
                      "never pad", "what to watch"],
        "approver.md": ["APPROVE", "REJECT", "accuracy", "balance", "clarity", "compliance",
                        "smuggled"],
        "wrap.md": ["voice of reason", "what to watch", "never what to do", "no em dashes",
                    "todays_stories", "desk_boards"],
    }
    for name, toks in guards.items():
        try:
            text = common.load_prompt(name)
        except Exception as e:
            fails.append(f"prompt {name}: cannot read ({e})")
            continue
        low = text.lower()
        for tk in toks:
            _check(tk.lower() in low, fails, f"prompt {name}: missing guardrail token '{tk}'")

    # shill belt canary: a tout post is rejected; a sportsbook promo item is flagged
    # (but not auto-rejected); a primary-source item is clean
    tout = {"headline": "Lock of the day: guaranteed winner tonight, don't miss",
            "snippet": "promo code bonus bets, risk-free bet before the line moves",
            "source": "x", "source_tier": "unknown", "url": "http://x"}
    promo = {"headline": "New sportsbook offers promo code bonus bets for the playoffs",
             "snippet": "", "source": "dealsite", "source_tier": "aggregator", "url": "http://d"}
    real = {"headline": "NFL suspends Acme Falcons cornerback six games for wagering policy violation",
            "snippet": "", "source": "NFL", "source_tier": "primary", "url": "http://nfl"}
    shill_mod.annotate([tout, promo, real], rules)
    _check(tout["shill_rejected"] is True
           and tout["shill_score"] >= rules["thresholds"]["reject_score"], fails,
           f"shill canary: tout post not rejected (score={tout['shill_score']})")
    _check(promo["shill_score"] >= rules["thresholds"]["flag_score"], fails,
           f"shill canary: sportsbook promo item not flagged (score={promo['shill_score']})")
    _check(real["shill_rejected"] is False and real["shill_score"] == 0, fails,
           f"shill canary: primary-source item wrongly flagged (score={real['shill_score']})")

    # dedupe canary: two near-identical headlines collapse
    import aggregate
    dup = [
        {"headline": "NBA suspends Acme Rockets guard ten games over wagering violation",
         "source": "A", "source_tier": "primary", "url": "u1", "timestamp": "", "snippet": ""},
        {"headline": "NBA suspends Acme Rockets guard ten games over wagering violation, team plans appeal",
         "source": "B", "source_tier": "major", "url": "u2", "timestamp": "", "snippet": ""},
        {"headline": "Yankees ace throws first no-hitter of the season",
         "source": "C", "source_tier": "major", "url": "u3", "timestamp": "", "snippet": ""},
    ]
    clusters = aggregate.dedupe(dup, cfg)
    _check(len(clusters) == 2, fails, f"dedupe canary: expected 2 clusters, got {len(clusters)}")

    # S-L1 STANDINGS: A TABLE OF ZEROS IS NOT A STANDING. The upstream endpoint answers
    # for the season it thinks is current, and in September that is the 2026-27 NBA and
    # NHL seasons: thirty teams at 0-0. Rendering that looks like a result and breaks the
    # desk's oldest law. standings._played is the guard; this proves it both ways, so a
    # refactor that "simplifies" it fails here rather than on the page.
    import standings as _st
    def _ent(w, l, t="0"):
        return {"stats": [{"name": "wins", "displayValue": w},
                          {"name": "losses", "displayValue": l},
                          {"name": "ties", "displayValue": t}],
                "team": {"displayName": "Acme Rockets", "abbreviation": "ACM"}}
    _check(not _st._played(_ent("0", "0")), fails,
           "standings canary: a 0-0 row was treated as a played standing")
    _check(_st._played(_ent("1", "0")), fails,
           "standings canary: a 1-0 row was not treated as played")
    _check(_st._played(_ent("0", "1")), fails,
           "standings canary: an 0-1 row was not treated as played")
    _check(not _st._played({"stats": [], "team": {}}), fails,
           "standings canary: a row with no stats was treated as played")
    # and the committed file must never carry a group in which nobody has played
    _stf = _st.load()
    if _stf:
        _bad = [f'{lg["league"]} {g["name"]}'
                for lg in (_stf.get("leagues") or []) for g in lg["groups"]
                if not any(str(r.get("wins") or "0") != "0" or str(r.get("losses") or "0") != "0"
                           or str(r.get("ties") or "0") != "0" for r in g["rows"])]
        _check(not _bad, fails,
               f"standings canary: group(s) with no games played were written: {_bad[:3]}")

    # S-L2 TEAM PAGES: THE KEY FACT IS NOT THE SUBJECT. The first cut matched a team's
    # full name anywhere in a story's summary fields and put a 49ers story on the Titans
    # page, because the key fact named the Titans as the opponent. A page about a team
    # takes the claim from the headline or the dek. This is the same family as the
    # nickname rule below it and the tag-integrity case under that: a name appearing
    # somewhere in a story is not a statement about what the story is about.
    import site_build as _sb
    _sf = {"slug": "shanahan-preseason", "title": "Shanahan to coach preseason opener",
           "dek": "San Francisco 49ers head coach Kyle Shanahan intends to coach the "
                  "team's preseason opener.",
           "key_fact": "Shanahan intends to coach the 49ers' preseason opener Thursday "
                       "against the Tennessee Titans.",
           "published_utc": "2026-08-01T00:00:00Z"}
    _real = {"slug": "titans-sign", "title": "Tennessee Titans sign veteran guard",
             "dek": "The move fills the interior line.",
             "published_utc": "2026-08-02T00:00:00Z"}
    _sb._page_reset()
    _got = [i["slug"] for i in _sb._team_stories("Tennessee Titans", "Titans",
                                                 [_sf, _real])]
    _check("shanahan-preseason" not in _got, fails,
           "team-page canary: a story matched on a team named only in its key fact")
    _check("titans-sign" in _got, fails,
           "team-page canary: a story about the team was not matched")
    # and the nickname rule the game page learned: a nickname counts in a headline only
    _nick = {"slug": "tv-ratings", "title": "Sunday night ratings climb",
             "dek": "The broadcast drew 25.7M viewers, with the Bills game leading.",
             "published_utc": "2026-08-03T00:00:00Z"}
    _sb._page_reset()
    _check("tv-ratings" not in [i["slug"] for i in
                                _sb._team_stories("", "Bills", [_nick])], fails,
           "team-page canary: a nickname in a dek was treated as the subject")

    # B-1: THE ORDERING LAW. One function decides it for the band, the scoreboard and
    # the strip: live by urgency, then anything kicking off inside the hour, then
    # today's finals, then the rest of upcoming, then older finals, with a delayed game
    # at the end of the bucket it came from.
    import datetime as _dtb
    _ETb = _sb._ET

    def _gb(lg, a, h, kick_et, st, sa=None, sh=None, per=None, short=""):
        _k = _dtb.datetime.fromisoformat(kick_et).replace(tzinfo=_ETb) \
                  .astimezone(_dtb.timezone.utc)
        return {"league": lg, "id": a + h, "state": st, "period": per,
                "status_short": short,
                "start_utc": _k.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "away": {"abbr": a, "score": sa}, "home": {"abbr": h, "score": sh}}

    def _ordb(games, when):
        _n = _dtb.datetime.fromisoformat(when).replace(tzinfo=_ETb) \
                  .astimezone(_dtb.timezone.utc)
        return [x["away"]["abbr"] for x in
                sorted(games, key=lambda q: _sb._sb_sort_key_in_league(q, _n))]

    # Sunday 4:30: the slate live, one game kicking at 4:25 already gone, a final from
    # the morning, and tonight's game hours away.
    _sun = [_gb("NFL", "BLOW", "OUT", "2026-09-20T13:00", "in", "38", "3", 4),
            _gb("NFL", "CLOSE", "GAME", "2026-09-20T13:00", "in", "20", "17", 4),
            _gb("NFL", "TIED", "LATE", "2026-09-20T13:00", "in", "21", "21", 4),
            _gb("NFL", "SOON", "KICK", "2026-09-20T17:20", "pre"),
            _gb("NFL", "MORN", "FINAL", "2026-09-20T09:30", "post", "17", "14"),
            _gb("NFL", "NIGHT", "GAME", "2026-09-20T20:20", "pre")]
    _o = _ordb(_sun, "2026-09-20T16:30")
    _check(_o[0] == "TIED", fails,
           f"B-1 canary: the closest live game did not lead: {_o}")
    _check(_o.index("BLOW") > _o.index("CLOSE"), fails,
           f"B-1 canary: a blowout outranked a one-score game: {_o}")
    _check(_o.index("SOON") < _o.index("MORN"), fails,
           f"B-1 canary: a game kicking inside the hour ranked below a final: {_o}")
    _check(_o.index("MORN") < _o.index("NIGHT"), fails,
           f"B-1 canary: today's final ranked below a fixture hours away: {_o}")

    # Sunday 9 AM: nothing live, last night's final still holds above today's slate.
    _morn = [_gb("NFL", "LAST", "NIGHT", "2026-09-19T20:15", "post", "24", "21"),
             _gb("NFL", "ONE", "PM", "2026-09-20T13:00", "pre")]
    _check(_ordb(_morn, "2026-09-20T09:00")[0] == "LAST", fails,
           "B-1 canary: on Sunday morning last night's final did not lead")
    # and by 12:30 the 1 PM game is inside the hour and takes it
    _check(_ordb(_morn, "2026-09-20T12:30")[0] == "ONE", fails,
           "B-1 canary: at 12:30 the 1 PM game did not take the lead from the final")

    # A delayed game sits at the end of the live bucket, not among the games that are on.
    _dly = [_gb("NFL", "RAIN", "DELAY", "2026-09-20T13:00", "in", "0", "0", 1,
                "Delayed"),
            _gb("NFL", "PLAY", "ING", "2026-09-20T13:00", "in", "10", "7", 2)]
    _check(_ordb(_dly, "2026-09-20T14:00")[0] == "PLAY", fails,
           "B-1 canary: a delayed game ranked above a game in progress")

    # Thursday 7:30, and the line between the two rules. WITHIN a tab, live beats
    # upcoming, so live baseball leads the baseball board; it is the MARQUEE that an
    # imminent marquee-league game takes, which is M-20 and lives in the picker, not in
    # this sort. Asserting the sort here would have been asserting the wrong rule.
    _thu = [_gb("MLB", "LIVE", "BALL", "2026-09-17T19:10", "in", "2", "1", 5),
            _gb("NFL", "DET", "BUF", "2026-09-17T20:15", "pre")]
    _check(_ordb(_thu, "2026-09-17T19:30")[0] == "LIVE", fails,
           "B-1 canary: within a tab a live game did not outrank an upcoming one")
    _mq_thu = _sb._sb_marquee_pick(
        _thu, _dtb.datetime.fromisoformat("2026-09-17T19:30").replace(tzinfo=_ETb)
                   .astimezone(_dtb.timezone.utc))
    _check(_mq_thu and _mq_thu["away"]["abbr"] == "DET", fails,
           "B-1 canary: the marquee did not go to the imminent NFL game (M-20)")

    # netlify_ignore decides whether a deploy runs AT ALL, and it had no test on either
    # desk, though its own docstring says "Pure, so the test below is the whole proof".
    # What it got wrong was the case with no test to catch it: an empty diff read as
    # "nothing to do", when an empty diff means a scheduled or hook build and this
    # desk's board refetches at build time. A-1's hooks were being declined here.
    import netlify_ignore as _ni
    import datetime as _dw
    _sk, _wy = _ni.decide([])
    _check(_sk is False, fails,
           f"netlify ignore canary: a build with no changed files was SKIPPED, which "
           f"is every scheduled refresh and every A-1 hook ping: {_wy}")
    _check(_ni.decide(None)[0] is False, fails,
           "netlify ignore canary: a build that cannot be diffed was skipped; every "
           "unclear case must resolve to building")
    _check(_ni.decide(["site_build.py"])[0] is False, fails,
           "netlify ignore canary: a change to the generator did not build")
    _q = _dw.datetime(2026, 9, 22, 8, 0, tzinfo=_dw.timezone.utc)
    _check(_ni.in_posting_window(_q) is False, fails,
           "netlify ignore canary: the quiet-hours fixture is inside a posting window, "
           "so the checks below prove nothing")
    _check(_ni.decide(["site/data/inactives/x.json"], _q)[0] is True, fails,
           "netlify ignore canary: an inactives snapshot outside every posting window "
           "now builds, so the fix just switched the file off")
    _check(_ni.decide(["ledger.json"], _q)[0] is True, fails,
           "netlify ignore canary: an ops-ledger row now builds")
    # U-11 (24 September 2026): a commit that changes nothing in the published tree does
    # not build the site. Two handoff commits on 22 September each spent a production
    # deploy on a file that changes no pixel.
    for _d in ["HANDOFF.md", "docs/HANDOFF.md", "README.md", "netlify_ignore.py",
               "shots/x.png", "docs/notes/a.md"]:
        _check(_ni.decide([_d], _q)[0] is True, fails,
               f"netlify ignore canary (U-11): {_d} built the site, and it cannot change "
               f"a pixel of it")
    _check(_ni.decide(["HANDOFF.md", "docs/a.md"], _q)[0] is True, fails,
           "netlify ignore canary (U-11): a commit of nothing but documents built")
    # AND THE OTHER HALF, which is the half that costs a reader if it is wrong: one real
    # file among the documents must still build.
    _check(_ni.decide(["HANDOFF.md", "site_build.py"], _q)[0] is False, fails,
           "netlify ignore canary (U-11): the generator changed and the build was SKIPPED "
           "because a handoff file was in the same commit")
    _check(_ni.decide(["site_build.py"], _q)[0] is False, fails,
           "netlify ignore canary (U-11): a generator change was skipped")
    _check(_ni.decide(["site/publish/index.html"], _q)[0] is False, fails,
           "netlify ignore canary (U-11): a published page changed and did not build")
    _check(_ni.decide(["site/data/scoreboard.json"], _q)[0] is False, fails,
           "netlify ignore canary (U-11): board data changed and did not build")
    _check(_ni.is_doc("site/data/x.md") is False, fails,
           "netlify ignore canary (U-11): a markdown file INSIDE the published tree was "
           "treated as a document; it can be served")

    # U-11's other half: the build stamp. Every page carries the commit that built it and
    # /stamp.txt carries the same one, so a live read can name the deploy it is reading.
    # Without this, on 24 September, a documents-only push could not be shown NOT to have
    # rebuilt the site: Netlify posts no status to GitHub, so a skipped build and a paused
    # site read identically.
    import live_read as _lr
    _sbm = _sb.BUILD_COMMIT
    _check(_sbm and _sbm != "unknown", fails,
           f"build stamp canary: the build cannot name its own commit ({_sbm!r}); every "
           f"live read would then assert against 'unknown'")
    _stamp_f = os.path.join(_sb.PUBLISH, "stamp.txt")
    if os.path.exists(_stamp_f):
        _stxt = open(_stamp_f, encoding="utf-8").read()
        # WHAT THIS CHECKS, and what it deliberately does not (fixed 26 September 2026). The
        # first version compared the built pages against BUILD_COMMIT resolved NOW, i.e. the
        # current HEAD. That turned the hard gate red on both desks the moment HEAD moved
        # without a rebuild, which is most of any working session, and it conflated a stale
        # local build with the defect the canary is for. The defect is DRIFT BETWEEN THE TWO
        # WRITERS: the meta tag and /stamp.txt must name the same commit as each other. Whether
        # that commit is the tip is a question about a DEPLOY, and live_read.py answers it
        # against the deployed page, which is where U-10 wants it asked.
        _m_stamp = _re_stamp = None
        import re as _re_s
        _m_stamp = _re_s.search(r"commit ([0-9a-fA-F]{7,40}|unknown)", _stxt)
        _check(_m_stamp is not None, fails,
               "build stamp canary: /stamp.txt carries no commit line")
        _built = _m_stamp.group(1) if _m_stamp else ""
        _check(_built != "unknown", fails,
               "build stamp canary: /stamp.txt says the build could not name its commit")
        if _built and _built != _sbm:
            print(f"build stamp: the built tree is from {_built[:12]}, HEAD is {_sbm[:12]}; "
                  f"a stale local build, not a fault. Netlify always builds fresh, and a live "
                  f"read asserts the deploy (U-10).")
        _pages = [f for f in ["index.html", "scores.html", "about.html"]
                  if os.path.exists(os.path.join(_sb.PUBLISH, f))]
        _check(len(_pages) >= 2, fails,
               "build stamp canary: fewer than two built pages to check, so the next "
               "checks prove nothing")
        for _pg in _pages:
            _ph = open(os.path.join(_sb.PUBLISH, _pg), encoding="utf-8").read()
            _mt = re.search(r'<meta name="build-commit" content="([^"]*)"', _ph)
            _check(_mt is not None, fails,
                   f"build stamp canary: {_pg} carries no build-commit meta tag")
            if _mt:
                _check(_mt.group(1) == _built, fails,
                       f"build stamp canary: {_pg}'s stamp {_mt.group(1)[:12]} and /stamp.txt's "
                       f"{_built[:12]} name different commits; the two writers drifted")
        # THE ASSERTION ITSELF must reject a stale stamp, which is the whole point: a live
        # read of the previous deploy is the failure mode, and it looks exactly like a
        # successful read.
        _check(_lr.META.search('<meta name="build-commit" content="0123456789abcdef">')
               is not None, fails,
               "build stamp canary: live_read cannot find a stamp it is given")
        _check(_lr.META.search('<meta name="build-commit" content="">') is None, fails,
               "build stamp canary: live_read accepts an empty stamp as a commit")
    # AN INACTIVES SNAPSHOT NEVER BUILDS, in a window or out of one. This asserted the
    # opposite until 21 September, when Netlify paused every site on the team over
    # 1,188 deploys in a period and that rule was found to be the largest single source
    # of them. The board is still the product inside a window; it now reaches the page
    # from the committed JSON on the client instead of from a deploy.
    _iw = _dw.datetime(2026, 9, 20, 18, 0, tzinfo=_dw.timezone.utc)
    _check(_ni.in_posting_window(_iw) is True, fails,
           "netlify ignore canary: the Sunday-slate fixture is not in a posting window, "
           "so the check below proves nothing")
    _check(_ni.decide(["site/data/inactives/x.json"], _iw)[0] is True, fails,
           "netlify ignore canary: an inactives snapshot inside a posting window still "
           "builds the site; the poller pushes every 15 minutes and that is 1,188 "
           "deploys a period")
    # And the page must be able to refresh itself, or the line above is just staleness.
    _iap = os.path.join(_sb.PUBLISH, "fantasy", "inactives.html")
    if os.path.exists(_iap):
        _iah = open(_iap, encoding="utf-8", errors="ignore").read()
        _check("data-ia-board" in _iah and "raw.githubusercontent" in _iah, fails,
               "netlify ignore canary: the inactives board no longer builds on a "
               "snapshot and cannot fetch one either, so it would simply go stale")
        # THE FILE IS NAMED BY THE DAY OF THE POLL, NOT THE DAY OF THE BUILD. The poller
        # names its file by the UTC date of the poll and the morning build runs at
        # 09:40Z, which is still the previous day in UTC, so a page built on a Sunday
        # morning asked for SATURDAY's file all morning and the 11:30 lists never
        # appeared until the kickoff build. That is the one case this whole change
        # exists to cover, so the order is checked and not just the presence.
        _check("toISOString().slice(0, 10)" in _iah, fails,
               "S-budget canary: the board does not try today's UTC date, so a page "
               "built before 00:00Z asks for yesterday's snapshot all day")
        _i_now = _iah.find("toISOString().slice(0, 10)")
        _i_built = _iah.find("out.indexOf(built)")
        _check(0 < _i_now < _i_built, fails,
               "S-budget canary: the build's own day is tried before today's, which is "
               "the bug with the order reversed")
        _check("data-ia-day=" in _iah, fails,
               "S-budget canary: the fallback day is not on the page, so a Sunday night "
               "reader, already on Monday in UTC, loses the Sunday night list")
        # A LATE LIST SAYS WHICH GAME. The answer comes from the page's own list of
        # games, matched on the team id, so the build still owns it. Exactly one match
        # names the opponent; none or more than one names nothing, because a wrong
        # opponent on an inactives list is worse than no opponent.
        _check('class="wpw-g"' in _iah and "data-aid=" in _iah, fails,
               "S-budget canary: the who-plays-when panel carries no game data, so a "
               "list painted after the build cannot say which game it belongs to")
        _check("hits.length === 1" in _iah, fails,
               "S-budget canary: the late block names a game without requiring exactly "
               "one match, so an ambiguous team gets an opponent picked for it")

    # N-9: US SPELLING IN THE DESK'S OWN PROSE, AND NEVER IN A QUOTATION.
    #
    # The desk writes for an American audience and its own sentences carried programme,
    # licence, travelling, defence and cancelled. The fixture is those five words.
    _fx9 = "The programme was cancelled while travelling; their defence had a licence."
    _got9 = _sb.us_spelling(_fx9)
    for _w in ("programme", "cancelled", "travelling", "defence", "licence"):
        _check(_w not in _got9, fails,
               f"N-9 canary: {_w!r} survived the US-spelling pass: {_got9!r}")
    # A QUOTATION IS NOT THE DESK'S TO RESTYLE. This is the line destyle was ruled back
    # from once; house style is the desk's own voice.
    _q9 = 'He said \u201cthe programme was cancelled\u201d and left.'
    _check(_sb.us_spelling(_q9) == _q9, fails,
           f"N-9 canary: a quotation was restyled, which changes what a named person is "
           f"quoted as saying: {_sb.us_spelling(_q9)!r}")
    # And the mixed case: desk prose either side of a quotation.
    _m9 = 'Their defence held. \u201cOur defence was superb,\u201d he said.'
    _o9 = _sb.us_spelling(_m9)
    _check(_o9.startswith("Their defense held."), fails,
           f"N-9 canary: prose before a quotation was not corrected: {_o9!r}")
    _check("\u201cOur defence was superb,\u201d" in _o9, fails,
           f"N-9 canary: the quotation was corrected: {_o9!r}")

    # The desk's own chrome carries neither the doubled word nor the British spelling.
    for _pg9 in ("about.html", "method.html", "standards.html"):
        _fp9 = os.path.join(_sb.PUBLISH, _pg9)
        if not os.path.exists(_fp9):
            continue
        _t9 = re.sub(r"<[^>]+>", " ",
                     open(_fp9, encoding="utf-8", errors="ignore").read())
        _check(not re.search(r"\b(the|a|of|and)\s+\1\b", _t9, re.I), fails,
               f"N-9 canary: {_pg9} repeats a word")
        _check(not re.search(r"\blabelled\b", _t9, re.I), fails,
               f"N-9 canary: {_pg9} still says 'labelled'")

    # N-8: a column that is blank on every row is broken or should not exist.
    import glob as _g9
    _tp = sorted(_g9.glob(os.path.join(_sb.PUBLISH, "teams", "*.html")))
    if _tp:
        _th = open(_tp[0], encoding="utf-8", errors="ignore").read()
        # EVERY UNPLAYED FIXTURE SAYS SOMETHING. Checking that the page contains a
        # carrier ANYWHERE passes on a table with one filled row and sixteen blank
        # ones, which is the bug with one exception. Each future row carries either a
        # named carrier or the reason there is not one yet.
        _future = re.findall(r'<td class="tm-r">(?!.*tm-res)(.*?)</td>\s*'
                             r'<td class="tm-n">(.*?)</td>', _th, re.S)
        # A BYE IS NOT A FIXTURE. It has no opponent and no broadcast, and its empty
        # cell is the correct answer rather than a missing one.
        _blank = [t for r, t in _future
                  if "tm-time" in r and ">Bye<" not in r and not t.strip()]
        _check(not _blank, fails,
               f"N-8 canary: {len(_blank)} fixture row(s) have an empty TV cell, which "
               f"reads as broken rather than as pending")
        _check("tm-full" in _th and "tm-abbr" in _th, fails,
               "N-8 canary: the schedule names the opponent only one way; the full name "
               "belongs at desktop and the abbreviation under 600px")

    # N-4, N-5, N-6: three small things, each of which was telling a reader something
    # untrue about the page.
    _css_p = os.path.join(_sb.ASSETS, "site.css")
    if os.path.exists(_css_p):
        _cs = open(_css_p, encoding="utf-8").read()
        _i = _cs.find(".tk-g3{")
        _check(_i >= 0 and "align-items:start" in _cs[_i:_i + 220], fails,
               "N-4 canary: the card grid stretches every card in a row to the tallest, "
               "so one card with a story leaves its neighbours with an empty lower half")

    # N-5: THURSDAY, SUNDAY AND MONDAY NIGHT ARE THE LEAGUE'S STANDARD WINDOWS. Flagging
    # them as unusual put the tag on three of the four most ordinary slots in the
    # schedule, which is the same as putting it on none.
    for _w in ("Thursday night", "Sunday night", "Monday night", "Sunday afternoon"):
        _check(not _sb._ODD_WINDOW.search(_w), fails,
               f"N-5 canary: {_w!r} is flagged as an unusual window; it is the league's "
               f"standard grid and has been for decades")
    for _w in ("Saturday", "Friday night", "Thanksgiving"):
        _check(bool(_sb._ODD_WINDOW.search(_w)), fails,
               f"N-5 canary: {_w!r} is not flagged, so the tag now marks nothing at all")

    # N-6: the link says what it is and rides with the tabs.
    # CHECKED ON THE BUILT PAGE, not by calling the function. _week_link() returns ""
    # when the week data is not loaded, which it is not in this process, so guarding on
    # its truthiness skipped the whole check and the break stayed green.
    for _pg6 in ("index.html", "scores.html"):
        _fp6 = os.path.join(_sb.PUBLISH, _pg6)
        if not os.path.exists(_fp6):
            continue
        _h6a = open(_fp6, encoding="utf-8", errors="ignore").read()
        _m6 = re.search(r'class="wk-link"[^>]*>([^<]+)', _h6a)
        if not _m6:
            continue
        _check("schedule" in _m6.group(1), fails,
               f"N-6 canary: on {_pg6} the week link reads as a sentence fragment: "
               f"{_m6.group(1)[:50]!r}")
    for _pg in ("index.html", "scores.html"):
        _fp = os.path.join(_sb.PUBLISH, _pg)
        if os.path.exists(_fp) and "wk-link" in open(_fp, encoding="utf-8",
                                                     errors="ignore").read():
            _h6 = open(_fp, encoding="utf-8", errors="ignore").read()
            _before = _h6[:_h6.find('class="wk-link"')]
            _check("sb-tabs" in _before[-900:] or "sb-tabrow" in _before[-900:], fails,
                   f"N-6 canary: on {_pg} the week link is not with the league tabs; it "
                   f"is a link about WHICH GAMES, not about what each card shows")

    # TWO NITS FROM THE 22 SEPTEMBER READ.
    #
    # A POSTPONED GAME HAS NO SCORE. The feed sends 0 and 0 and marks it Postponed, and
    # the card printed both zeros under "MLB / Final": a nil-nil result for a game that
    # was never played, which is the fabricated-number rule in the score slot.
    _pp = {"league": "MLB", "id": "PP", "state": "post", "status_short": "Postponed",
           "start_utc": "2026-09-22T23:05:00Z", "network": "ESPN Unlmtd",
           "away": {"abbr": "TOR", "full": "Toronto Blue Jays", "score": "0"},
           "home": {"abbr": "BAL", "full": "Baltimore Orioles", "score": "0"}}
    _ppc = _sb._tk_card(_pp, {}, items=[])
    _slots = re.findall(r'class="tk-sc">([^<]*)</span>', _ppc)
    _check(_slots and not any(x.strip() for x in _slots), fails,
           f"N-nit canary: a postponed game printed digits in its score slots: {_slots}")
    _check("Postponed" in _sb._tk_kicker(_pp), fails,
           f"N-nit canary: a postponed game is labelled "
           f"{re.sub(r'<[^>]+>', '', _sb._tk_kicker(_pp))!r}; it was never played")
    _check("Final" not in _sb._tk_kicker(_pp), fails,
           "N-nit canary: a postponed game still reads as a final")
    # A real final is untouched.
    _fin = dict(_pp, status_short="Final")
    _fin["away"] = dict(_pp["away"], score="4")
    _fin["home"] = dict(_pp["home"], score="2")
    _fs = re.findall(r'class="tk-sc">([^<]*)</span>', _sb._tk_card(_fin, {}, items=[]))
    _check([x for x in _fs if x.strip()], fails,
           "N-nit canary: a real final lost its score, so the postponed rule is eating "
           "every result")

    # THE FEED'S ABBREVIATION IS NOT THE NETWORK'S NAME. Anything the desk has not seen
    # prints as the feed gives it, which is why this checks the mapped one and not the
    # size of the map.
    _check(_sb.network_name("ESPN Unlmtd") == "ESPN Unlimited", fails,
           "N-nit canary: the feed's shorthand reaches the card unmapped")
    _check(_sb.network_name("Some New Channel") == "Some New Channel", fails,
           "N-nit canary: an unmapped network is not printed as the feed gives it")
    _check("ESPN Unlmtd" not in _ppc, fails,
           "N-nit canary: the card prints the feed's shorthand")

    # N-1: ONE NAME FOR A TEAM, EVERYWHERE THE SITE NAMES ONE.
    #
    # Seven surfaces, six spellings, one team. The pro cards printed the location alone,
    # so "Los Angeles 14" sat over "Los Angeles 26" in one column on a Sunday and
    # neither line said which Los Angeles. The standings were the only surface that had
    # it right, so the whole site prints what they print.
    _fx = [
        ({"full": "New York Giants", "abbr": "NYG"}, "New York Giants"),
        ({"full": "New York Jets", "abbr": "NYJ"}, "New York Jets"),
        ({"full": "Los Angeles Rams", "abbr": "LAR"}, "Los Angeles Rams"),
        ({"full": "Los Angeles Chargers", "abbr": "LAC"}, "Los Angeles Chargers"),
        ({"full": "Miami Dolphins", "abbr": "MIA"}, "Miami Dolphins"),
        ({"full": "Miami Hurricanes", "abbr": "MIA"}, "Miami Hurricanes"),
        ({"full": "Athletics", "abbr": "ATH"}, "Athletics"),
        ({"full": "AFC Bournemouth", "abbr": "BOU"}, "AFC Bournemouth"),
        ({"full": "Central Michigan Chippewas", "abbr": "CMU"},
         "Central Michigan Chippewas"),
    ]
    for _t, _want in _fx:
        _got = _sb._team_label({"league": "NFL"}, _t)
        _check(_got == _want, fails,
               f"N-1 canary: the label for {_t['abbr']} is {_got!r}, not {_want!r}")
    # The two Los Angeles teams and the two Miamis must not collide, which is the whole
    # reason the location alone was not a name.
    _labels = [_sb._team_label({"league": "NFL"}, t) for t, _ in _fx]
    _check(len(set(_labels)) == len(_labels), fails,
           "N-1 canary: two teams in the fixture share a label")
    # A row with no displayName still gets a name, and the mascot is inside it.
    _check(_sb._team_label({"league": "CFB"},
                           {"school": "Miami", "mascot": "Hurricanes", "abbr": "MIA"})
           == "Miami Hurricanes", fails,
           "N-1 canary: a feed row without displayName lost its mascot")
    # THE MASCOT TAIL IS GONE, because the name carries it.
    _check(_sb._team_mascot({"league": "CFB"},
                            {"mascot": "Hurricanes", "school": "Miami"}) == "", fails,
           "N-1 canary: the compact card still prints a mascot beside a name that "
           "already contains it")
    # Long names are marked for the stylesheet rather than truncated.
    _check(_sb._tk_long({"league": "CFB"}, {"full": "Central Michigan Chippewas"}), fails,
           "N-1 canary: a 26-character name is not marked long")
    _check(not _sb._tk_long({"league": "NFL"}, {"full": "Miami Dolphins"}), fails,
           "N-1 canary: a short name is marked long, so every name steps down to fit "
           "the longest one")
    # AND THE BUILT SITE CARRIES NO BARE CITY as a team-name element.
    import re as _re_n1
    _bare = 0
    for _root, _d, _fs in os.walk(_sb.PUBLISH):
        for _f in _fs:
            if not _f.endswith(".html"):
                continue
            _h = open(os.path.join(_root, _f), encoding="utf-8",
                      errors="ignore").read()
            _bare += len(_re_n1.findall(r">\s*(?:New York|Los Angeles)\s*<", _h))
    _check(_bare == 0, fails,
           f"N-1 canary: {_bare} element(s) on the built site are a bare city, which "
           f"names neither of the two teams that share it")

    # N-2: TODAY IS A DATE, NOT EVERY CARD ON THE PAGE.
    #
    # The band held 31 cards on a Monday and said "31 games today" over an All tab the
    # build had written as 14, which was right: a Monday has one NFL game and the rest
    # of those cards are next Saturday's college slate. The header and the tab
    # contradicted each other on one screen. Ground truth from the committed snapshot
    # for 21 September is 14: NFL 1, MLB 3, NHL 8, WNBA 2.
    #
    # The browser half was read live; what a canary can hold is the SHAPE of the client
    # rule, because every part of this bug was a line of that script.
    _sbj = _sb.SB_LIVE_JS
    _check("etDay(" in _sbj and "toLocaleDateString('en-CA'" in _sbj, fails,
           "N-2 canary: the recount has no Eastern date test, so it counts every card "
           "on the page as today")
    _check("(st === 'in') || (g.kick && etDay(g.kick) === now)" in _sbj, fails,
           "N-2 canary: the definition of today is not kickoff-on-today's-ET-date or "
           "in play, which is the only definition the header, the tabs and Next share")
    # The tab label is written from b.today and never from b.total: the total is every
    # card in that league on the page, which is what made the tabs disagree with the
    # header. Asserting both names appear was the bug restated, not tested.
    _tabblk = _sbj.split(".tk-tab'")[1] if ".tk-tab'" in _sbj else _sbj
    _tabtext = _tabblk[:_tabblk.find("var nx")] if "var nx" in _tabblk else _tabblk
    _check("b.today" in _tabtext, fails,
           "N-2 canary: the tab label is not written from the count of games today")
    _check("b.total" not in _tabtext, fails,
           "N-2 canary: a tab label still uses the league's total card count, which "
           "counts next Saturday's slate as today")
    _check(".toLowerCase() === 'all'" in _sbj, fails,
           "N-2 canary: the All tab is matched case-sensitively; the attribute is "
           "written \"All\" and a CSS attribute selector compares values exactly, so "
           "the tab silently kept the build's text and disagreed with the header")
    _check("function seed()" in _sbj and _sbj.count("seed();") >= 2, fails,
           "N-2 canary: the slate is seeded once at parse, so cards below the band do "
           "not exist yet and the header counts a fraction of the page")

    # N-3: THE STANDALONE PAGES TAKE THE PAGE'S INK, NOT THE BAND'S.
    #
    # The week pages and the Wire shipped with the dark scoreboard band's palette
    # hardcoded (#EBE9E3 for names, #A6ABB4 for stamps, white-alpha for rules) on two
    # pages that render on the cream page ground. In light mode every row, every week
    # number and every Wire entry was white on cream and could not be read at all. They
    # read perfectly in dark mode, which is the only mode they were checked in, and the
    # person who checked them was me.
    #
    # A colour is a token or it is a bug on one of the two schemes, and a grep is the
    # only form of this check that runs without a browser.
    import re as _re_n3
    _css = os.path.join(_sb.ASSETS, "site.css")
    if os.path.exists(_css):
        _c = open(_css, encoding="utf-8").read()
        _bad = []
        for _m in _re_n3.finditer(r"([^{}]*)\{([^{}]*)\}", _c):
            _sel = _m.group(1).strip()
            if not (_sel.startswith(".wr-") or _sel.startswith(".wk-")):
                continue
            if _re_n3.search(r"(?:^|;)\s*(?:color|background|background-color|"
                             r"border-color)\s*:\s*(?:#[0-9A-Fa-f]{3,6}|"
                             r"rgba?\(255,\s*255,\s*255)", _m.group(2)):
                _bad.append(_sel[:40])
        _check(not _bad, fails,
               f"N-3 canary: {len(_bad)} rule(s) on the standalone week and Wire pages "
               f"set a literal colour instead of a token, which is the dark band's "
               f"palette on a cream page: {_bad[:3]}")
        _check(".wk-page" in _c and ".wr-page" in _c, fails,
               "N-3 canary: the week and Wire pages have no side padding rule, so their "
               "text sits on the screen edge at 375")

    # E-2: THE WIRE. A log of what happened, newest first. Nothing is written for it,
    # so what has to hold is that it reports only what is real and in the right order.
    import datetime as _dw
    _noww = _sb._build_now()

    def _ago(h):
        return (_noww - _dw.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")

    _wi = [{"slug": "fresh", "title": "A story from this morning", "verdict": "VERIFIED",
            "published_utc": _ago(3)},
           {"slug": "stale", "title": "A story from last week", "verdict": "VERIFIED",
            "published_utc": _ago(200)},
           {"slug": "gone", "title": "A retired story", "verdict": "VERIFIED",
            "published_utc": _ago(2), "superseded_by": "fresh"},
           {"slug": "ex", "title": "An example", "example": True,
            "published_utc": _ago(1)}]
    _sbsave = _sb.SB_DATA
    _sb.SB_DATA = {"leagues": [{"league": "NFL", "games": [
        {"id": "G1", "state": "post", "league": "NFL", "start_utc": _ago(6),
         "away": {"abbr": "DET", "score": "31"}, "home": {"abbr": "BUF", "score": "41"}},
        {"id": "G2", "state": "post", "league": "NFL", "start_utc": _ago(300),
         "away": {"abbr": "OLD", "score": "1"}, "home": {"abbr": "OLD2", "score": "2"}},
        {"id": "G3", "state": "in", "league": "NFL", "start_utc": _ago(1),
         "away": {"abbr": "LIV", "score": "7"}, "home": {"abbr": "LIV2", "score": "3"}},
        {"id": "G4", "state": "post", "league": "NFL", "start_utc": _ago(5),
         "away": {"abbr": "NOS", "score": None}, "home": {"abbr": "NOS2"}}]}]}
    try:
        _rows = _sb._wire_rows(_wi, _noww)
        _txt = [r["text"] for r in _rows]
        _check("A story from this morning" in _txt, fails,
               f"E-2 canary: this morning's story is not on the wire: {_txt}")
        _check("A story from last week" not in _txt, fails,
               "E-2 canary: a story from last week is on a 48-hour wire")
        _check("A retired story" not in _txt, fails,
               "E-2 canary: a superseded story is on the wire, where it is unreachable "
               "everywhere else on the site")
        _check("An example" not in _txt, fails,
               "E-2 canary: an example story is on the wire as if it were real")
        _check("DET 31, BUF 41" in _txt, fails,
               f"E-2 canary: a final from six hours ago is not on the wire: {_txt}")
        _check(not any("OLD" in x for x in _txt), fails,
               "E-2 canary: a final from twelve days ago is on a 48-hour wire")
        _check(not any("LIV" in x for x in _txt), fails,
               "E-2 canary: a game still in play is on the wire as a final")
        _check(not any("NOS" in x for x in _txt), fails,
               "E-2 canary: a final with no score on it reached the wire, which is the "
               "fabricated-number rule with a timestamp on it")
        _check(_rows == sorted(_rows, key=lambda r: r["t"], reverse=True), fails,
               "E-2 canary: the wire is not newest first")
        _check(len(_txt) == len(set(_txt)), fails,
               f"E-2 canary: the wire repeats itself: {_txt}")
        # The filter names its kinds in real English, and offers nothing when there is
        # only one kind on the page to filter.
        _f = _sb._wire_filter(_rows)
        _check("Stories" in _f and "Storys" not in _f, fails,
               f"E-2 canary: the wire filter's plural is built by adding an s: {_f}")
        _check(" hidden" in _f, fails,
               "E-2 canary: the wire filter ships visible, so a reader with no script "
               "gets buttons that do nothing")
        _one = [r for r in _rows if r["kind"] == "Final"]
        _check(_sb._wire_filter(_one) == "", fails,
               "E-2 canary: a wire with one kind on it still drew a filter")
    finally:
        _sb.SB_DATA = _sbsave

    # E-1: THE LEAD RULE GAINS THE DAY. The weekday table it used is a calendar kept by
    # hand: it gives the NFL 4.5 on a Sunday in June and college football 3.5 every
    # Saturday including the ones in March. The board says what is actually being played.
    import datetime as _de
    _sb._DAY_SLATE = None
    _nowe = _sb._build_now()
    _tdy = _nowe.astimezone(_sb._ET)

    def _ge(dd, state="pre", hours=0):
        _k = (_tdy + _de.timedelta(days=dd, hours=hours))
        return {"state": state,
                "start_utc": _k.astimezone(_de.timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ")}

    # The shape the board actually returns on a Monday morning: the NFL board carries
    # the whole week, and the college board carries NEXT weekend.
    _sb.SB_DATA = {"leagues": [
        {"league": "NFL", "games": [_ge(0, "post", -12), _ge(0, "post", -12), _ge(0)]},
        {"league": "CFB", "games": [_ge(5), _ge(5), _ge(5), _ge(5), _ge(5)]}]}
    _sb._DAY_SLATE = None
    _sl = _sb._day_slate(_nowe)
    _check("CFB" not in _sl, fails,
           f"E-1 canary: college games five days away counted as today's slate, which "
           f"would make Saturday's football the story on a Monday: {_sl}")
    _check(_sl.get("NFL", (0, 0))[0] == 3, fails,
           f"E-1 canary: last night's finals and tonight's game are not today's slate: "
           f"{_sl}")
    # A league with nothing on today cannot be lifted above its base by the calendar.
    # TESTED ON A SATURDAY, because that is the only day the calendar lifts college
    # football at all: asked on a Monday this passes with the cut deleted, since the
    # table was not lifting anything to begin with.
    _satd = _tdy + _de.timedelta(days=(5 - _tdy.weekday()) % 7 or 7)
    _satu = _satd.astimezone(_de.timezone.utc)
    _check(_satd.weekday() == 5, fails, "E-1 canary: the Saturday fixture is not a "
                                        "Saturday")
    _check(_sb.LEAGUE_WEIGHT["CFB"][1].get(5) == 3.5, fails,
           "E-1 canary: the table no longer lifts college football on a Saturday, so "
           "the check below proves nothing")
    _sb.SB_DATA = {"leagues": [{"league": "NFL", "games": [
        {"state": "pre", "start_utc": _satu.strftime("%Y-%m-%dT%H:%M:%SZ")}]}]}
    _sb._DAY_SLATE = None
    _wc = _sb._league_weight("CFB", _satu)
    _check(_wc <= _sb.LEAGUE_WEIGHT["CFB"][0] + 1e-9, fails,
           f"E-1 canary: on a Saturday with no college game on the board, college "
           f"football kept its calendar lift: {_wc}")
    _sb._DAY_SLATE = None
    # And the board being unavailable leaves the table exactly as it was.
    _sb.SB_DATA = None
    _sb._DAY_SLATE = None
    _sat = _tdy.replace(year=2026, month=9, day=26)   # a Saturday
    _check(_sb._league_weight("CFB", _sat.astimezone(_de.timezone.utc)) == 3.5, fails,
           "E-1 canary: with no board the weekday table no longer stands alone, so a "
           "failed fetch changes the front page's judgement")
    _sb._DAY_SLATE = None

    # THE LIFT SATURATES. A fifteen-game Sunday is not twice the day a seven-game one
    # is, and without a ceiling the league with the biggest slate leads every time
    # regardless of what is on it: a forty-game midweek baseball card would outweigh a
    # conference championship.
    def _slate_w(league, count):
        _sb.SB_DATA = {"leagues": [{"league": league, "games": [
            _ge(0, "post", -2) for _ in range(count)]}]}
        _sb._DAY_SLATE = None
        return _sb._league_weight(league, _nowe)

    _w8, _w40 = _slate_w("MLB", 8), _slate_w("MLB", 40)
    _check(abs(_w40 - _w8) < 1e-9, fails,
           f"E-1 canary: the slate lift does not saturate, so the biggest card of the "
           f"day always leads: 8 games gave {_w8:.2f} and 40 gave {_w40:.2f}")
    _check(_slate_w("MLB", 2) < _w8, fails,
           "E-1 canary: the lift is flat below the ceiling too, so the size of the "
           "day's slate no longer counts for anything")
    _sb.SB_DATA = None
    _sb._DAY_SLATE = None

    # THE DESK'S TAGS AND THE TABLE'S KEYS. The desk writes "college"; the table says
    # "CFB". Unconnected, a correctly tagged college story fell through to whatever
    # other league tag was on it.
    _check(_sb.TAG_LEAGUE.get("college") == "CFB", fails,
           "E-1 canary: the desk's own college tag does not map to a league")
    # Tags are DERIVED from the text here, not read from a field, so the fixture is
    # text. Before the alias table this resolved to nothing at all: the tag the desk
    # writes was not a key the weight table knew, so the league fell through and the
    # story was weighted as if it belonged to no sport.
    _st = {"title": "college football realignment bill advances in the Senate",
           "dek": "", "key_fact": "", "body": []}
    _check("college-football" in _sb.tags_for(_st), fails,
           f"E-1 canary: the fixture no longer produces a college tag, so the check "
           f"below proves nothing: {_sb.tags_for(_st)}")
    _check(_sb._story_league(_st) == "CFB", fails,
           f"E-1 canary: a story whose league tag is the desk's own college spelling "
           f"resolved to {_sb._story_league(_st)!r} instead of CFB")

    # THE ONE-WORD FLOOR. The college vocabulary has 639 schools in it and some are
    # ordinary first names.
    # THE VOCABULARY IS SET HERE, not read from the schedule file. Guarding this on
    # TEAM_DATA being loaded meant the canary never ran it at all: the build loads that
    # file and the canary does not, so the whole block was skipped in silence and
    # deleting the floor left the canary green.
    _vsave = _sb._TEAM_VOCAB
    _sb._TEAM_VOCAB = {"NFL": {"San Francisco 49ers", "Buffalo Bills"},
                       "CFB": {"Taylor", "Ohio State", "Texas A&M", "Miami"}}
    try:
        _fake = {"title": "FBI case against fake 49ers player expands",
                 "dek": "women defrauded by Daejon Love and Taylor Chan in a scam"}
        _check(_sb._league_from_teams(_fake) == "", fails,
               "E-1 canary: a single one-word school name decided a story's league, so "
               "a romance scam is filed as college football because a suspect is "
               "called Taylor and there is a Taylor University")
        _real = {"title": "Jeremiah Smith becomes Ohio State's receiving leader",
                 "dek": ""}
        _check(_sb._league_from_teams(_real) == "CFB", fails,
               "E-1 canary: a multi-word school name no longer decides, so the floor "
               "above is just switching the check off")
        _two = {"title": "Miami and Taylor agree to a series", "dek": ""}
        _check(_sb._league_from_teams(_two) == "CFB", fails,
               "E-1 canary: two one-word school names together did not corroborate "
               "each other, which is the other half of the floor")
    finally:
        _sb._TEAM_VOCAB = _vsave

    # C-5: THE SHARE CARD carries the line, under the same law as the page. A card is a
    # PNG: the gate greps written files and cannot read one, and no reader can check it
    # against anything. So the decision is a function and this tests the function.
    # THIS CANARY RUNS WITH NOTHING INSTALLED. It is stdlib-only by design and the
    # workflow pip-installs nothing, so any module it imports must be importable with a
    # bare Python. share_cards imported PIL at module level, this line imported
    # share_cards, and the entire hard gate died on CI with ModuleNotFoundError while
    # passing here, because Pillow is installed on this machine. A check that only runs
    # where the author sits is not a gate.
    import re as _re_pil
    _sc_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "share_cards.py"), encoding="utf-8").read()
    _top_pil = [ln for ln in _sc_src.splitlines()
                if _re_pil.match(r"^(from PIL|import PIL)", ln)]
    _check(not _top_pil, fails,
           f"C-5 canary: share_cards imports PIL at module level ({_top_pil[:1]}), so "
           f"this canary cannot import it on CI, where nothing is installed. Import it "
           f"inside the functions that draw.")
    import share_cards as _scm
    _check(_scm.line_text({"line": {"provider": "DraftKings", "detail": "KC -6.5",
                                    "total": 47.5}})
           == ("KC -6.5  \u00b7  O/U 47.5", "DraftKings via ESPN"), fails,
           "C-5 canary: the card's line and its attribution are not produced together")
    for _bad, _why in (
            ({"line": {"detail": "KC -6.5", "total": 47.5}}, "a spread with no provider"),
            ({"line": {}, "ruling": "KC covered"}, "a cover ruling with no provider"),
            ({"line": {"provider": "DraftKings"}}, "a provider with no number")):
        _check(_scm.line_text(_bad) == ("", ""), fails,
               f"C-5 canary: the share card would paint {_why}: "
               f"{_scm.line_text(_bad)}")
    # The ruling on the card comes from the same function as the ruling on the page.
    _sb.LINES_DATA = None
    _gsc = {"id": "SC", "state": "post", "league": "NFL",
            "away": {"abbr": "IND", "score": "10"}, "home": {"abbr": "KC", "score": "24"},
            "line": {"provider": "DraftKings", "detail": "KC -6.5", "total": 47.5}}
    _txt = _sb._ruling_text(_gsc)
    _check("KC covered" in _txt and "Under 47.5" in _txt, fails,
           f"C-5 canary: the card's ruling text does not match the page's: {_txt!r}")
    _check("<" not in _txt and "&" not in _txt, fails,
           f"C-5 canary: markup reached the card's text: {_txt!r}")
    _check("via ESPN" not in _txt, fails,
           "C-5 canary: the attribution is inside the ruling text, so the card would "
           "draw it twice")

    # C-4: THE PINS PANEL. The behaviour is in the browser and was proved there; what
    # this checks is the contract the build is responsible for, which is that a reader
    # with no pins and no script is shown nothing at all rather than an empty box
    # promising teams they have not chosen.
    _mp = _sb.pins_panel()
    _check(" hidden" in _mp, fails,
           "C-4 canary: the my-teams panel does not ship hidden, so every reader who "
           "has pinned nothing gets an empty box")
    _check("mine-l" in _mp and "<li" not in _mp, fails,
           "C-4 canary: the panel ships with rows baked in; the pins are on the device "
           "and the build has never heard of them")
    _check('aria-labelledby="mine-h"' in _mp and 'id="mine-h"' in _mp, fails,
           "C-4 canary: the panel is a region with no accessible name")
    # It must be on a page that also carries the script and the name index, or it can
    # never fill: the panel prints abbreviations and the index is what turns them into
    # names.
    _sp = os.path.join(_sb.PUBLISH, "scores.html")
    if os.path.exists(_sp):
        _sh = open(_sp, encoding="utf-8", errors="ignore").read()
        # NOT "data-mine": the script contains querySelectorAll('[data-mine]'), so that
        # string is on the page whether the panel is or not and the check could never
        # fail. Removing the panel entirely left it green. The heading id belongs to the
        # panel and to nothing else.
        _check('id="mine-h"' in _sh, fails,
               "C-4 canary: /scores carries no my-teams panel")
        _check("gcms_teams" in _sh, fails,
               "C-4 canary: the page with the panel does not carry the pin script")
        _check("data-tabbr" in _sh and "data-tname" in _sh, fails,
               "C-4 canary: the page with the panel carries no team-name index, so "
               "every row would read as a bare abbreviation")

    # C-3: THE WIN PROBABILITY. The desk publishes no forecast of its own, so this can
    # exist only the way the line does: one named model's reading, carried as a fact
    # about what that model said.
    _sb.LIVE_WP = {"WP1": 0.68, "WP2": 0.32, "WP3": 1.0}

    def _gwp(gid, state):
        return {"league": "NFL", "id": gid, "state": state, "status_short": "2nd",
                "start_utc": "2026-09-20T17:00:00Z",
                "away": {"abbr": "IND"}, "home": {"abbr": "KC"}}

    _w1 = _sb._tk_winprob(_gwp("WP1", "in"))
    _check("KC 68% to win" in _w1, fails,
           f"C-3 canary: the home side's 0.68 did not read as KC 68%: {_w1!r}")
    _check('data-wp-model="ESPN"' in _w1 and "ESPN" in _w1, fails,
           "C-3 canary: a win probability was shown with no model named, which makes it "
           "this desk's forecast")
    # THE SIDE MUST BE NAMED, AND IT MUST BE THE RIGHT ONE. 0.32 for the home team is
    # 68% for the away team, and a card that prints the home abbreviation beside 68 has
    # said the opposite of what the model said.
    _w2 = _sb._tk_winprob(_gwp("WP2", "in"))
    _check("IND 68% to win" in _w2, fails,
           f"C-3 canary: a home probability of 0.32 was not stated as the away side's "
           f"68%: {_w2!r}")
    _check("KC" not in _w2.split("wp-v")[1][:40] if "wp-v" in _w2 else False, fails,
           f"C-3 canary: the wrong team is named beside the number: {_w2!r}")
    # NEVER ON A FINAL: the track ends with the game, so every finished game reads 100%.
    _check(_sb._tk_winprob(_gwp("WP3", "post")) == "", fails,
           "C-3 canary: a finished game showed a win probability, which is always 100% "
           "for the winner and restates the score as a percentage")
    _check(_sb._tk_winprob(_gwp("WP1", "pre")) == "", fails,
           "C-3 canary: a game that has not kicked off showed a win probability")
    _check(_sb._tk_winprob(_gwp("NONE", "in")) == "", fails,
           "C-3 canary: a game with no model reading drew an empty probability row")
    _sb.LIVE_WP = {}

    # C-2: THE LINESCORE AND THE LEADERS. The card said 41-31 and nothing about the four
    # quarters that produced it, and on every league but the NFL it named nobody at all,
    # because the desk computes fantasy points for the NFL and nowhere else.
    def _gls(state, pa, ph, sa="31", sh="41"):
        return {"league": "NFL", "id": "LS", "state": state, "status_short": "Final",
                "start_utc": "2026-09-20T17:00:00Z",
                "away": {"abbr": "DET", "score": sa, "periods": pa},
                "home": {"abbr": "BUF", "score": sh, "periods": ph}}

    _full = _sb._tk_linescore(_gls("post", ["0", "10", "7", "14"],
                                   ["14", "13", "7", "7"]))
    _check("<table" in _full, fails,
           "C-2 canary: a final with both linescores drew no table")
    _check(_full.count("<td") == 10, fails,
           f"C-2 canary: the table is not two rows of four periods and a total: "
           f"{_full.count('<td')} cells")
    _check(">31<" in _full and ">41<" in _full, fails,
           "C-2 canary: the total column does not carry the score the card already shows")
    # AND IT MUST BE THE SCORE, NOT A SUM OF THE ROW. The fixture above has periods that
    # add up to exactly the score, so a total computed by adding the cells passes it and
    # the test proves nothing. This one does not add up: the feed has dropped a period,
    # which is the case that actually occurs, and the row must still total what the
    # scoreboard says rather than what the visible cells happen to make.
    _gap = _sb._tk_linescore(_gls("post", ["0", "10"], ["14", "13"], sa="31", sh="41"))
    _check(">31<" in _gap and ">41<" in _gap, fails,
           f"C-2 canary: with a period missing the total was computed from the cells "
           f"(10 and 27) instead of read from the score (31 and 41): {_gap!r}")
    _check(">10<" in _gap and ">27<" not in _gap, fails,
           f"C-2 canary: the linescore invented a total: {_gap!r}")
    # A HALF-FILLED LINESCORE IS A TABLE WITH A HOLE IN IT.
    _check(_sb._tk_linescore(_gls("post", ["0", "10", "7", "14"], [])) == "", fails,
           "C-2 canary: a game with periods on one side only still drew a table")
    _check(_sb._tk_linescore(_gls("post", ["0", "10"], ["14", "13", "7", "7"])) == "",
           fails,
           "C-2 canary: a game whose two sides disagree on how many periods have been "
           "played still drew a table, so one row is short and the columns lie")
    _check(_sb._tk_linescore(_gls("pre", ["0"], ["0"])) == "", fails,
           "C-2 canary: a game that has not started drew a linescore")

    # The feed's leaders stand in only where the desk computes none, and a composite
    # rating prints no label: "B. Bichette RAT" over a line that already says
    # "1-4, HR, RBI, R, K" is a label that is worse than no label.
    _sb.LIVE_POINTS = {}
    _gld = {"league": "MLB", "id": "LD", "state": "in", "status_short": "Top 6th",
            "start_utc": "2026-09-20T17:00:00Z",
            "away": {"abbr": "TOR"}, "home": {"abbr": "NYY"},
            "leaders": [{"cat": "", "name": "B. Bichette",
                         "line": "1-4, HR, RBI, R, K", "team": "21"},
                        {"cat": "PASS", "name": "J. Goff",
                         "line": "26/38, 327 YDS", "team": "8"}]}
    _lr = _sb._tk_leaders(_gld)
    _check(_lr and _lr[0][0] == "B. Bichette", fails,
           f"C-2 canary: an unlabelled leader gained a label: {_lr and _lr[0]}")
    _check(len(_lr) == 2 and _lr[1][0] == "J. Goff PASS", fails,
           f"C-2 canary: a labelled leader lost its label: {_lr}")
    _check(_sb._tk_leaders(dict(_gld, state="pre")) == [], fails,
           "C-2 canary: a game that has not started named leaders")
    _check(_sb._tk_leaders(dict(_gld, leaders=[])) == [], fails,
           "C-2 canary: a game the feed names nobody for drew an empty leader block "
           "rather than none, which reads as nothing having happened")

    # B-4: THE WEEK, rebuilt from the 32 team schedules because the scoreboard feed is
    # today and only today. Every game is in the file TWICE, once from each side, so the
    # two things that can go wrong are a doubled slate and a flipped fixture, and a
    # flipped fixture is the worse one: it is silent, it reads perfectly well, and it
    # says a team played away when it played at home.
    _sch = {"teams": {
        "KC": {"short": "Chiefs", "events": [
            {"id": "g1", "week": 4, "home": True, "opp": "DEN", "state": "post",
             "date": "2026-09-28T00:20Z", "score": 31, "opp_score": 10,
             "network": "NBC", "time_set": True},
            {"id": "g2", "week": 5, "home": False, "opp": "BUF", "state": "pre",
             "date": "2026-10-05T05:00Z", "time_set": False}]},
        "DEN": {"short": "Broncos", "events": [
            {"id": "g1", "week": 4, "home": False, "opp": "KC", "state": "post",
             "date": "2026-09-28T00:20Z", "score": 10, "opp_score": 31}]},
        "BUF": {"short": "Bills", "events": [
            {"id": "g2", "week": 5, "home": True, "opp": "KC", "state": "pre",
             "date": "2026-10-05T05:00Z", "time_set": False}]}}}
    _w4 = _sb._sched_week(_sch, 4)
    _check(len(_w4) == 1, fails,
           f"B-4 canary: a game in both teams' files produced {len(_w4)} fixtures")
    _check(_w4 and _w4[0]["home"] == "KC" and _w4[0]["away"] == "DEN", fails,
           f"B-4 canary: the fixture is the wrong way round: "
           f"{_w4 and _w4[0].get('away')} at {_w4 and _w4[0].get('home')}")
    _check(_w4 and _w4[0]["home_score"] == 31 and _w4[0]["away_score"] == 10, fails,
           f"B-4 canary: the scores went to the wrong sides: {_w4 and _w4[0]}")
    _w5 = _sb._sched_week(_sch, 5)
    _check(_w5 and _w5[0]["home"] == "BUF" and _w5[0]["away"] == "KC", fails,
           "B-4 canary: a fixture seen only from the away side lost which team is home")
    _check(_w5 and _w5[0]["home_score"] is None
           and _w5[0]["away_score"] is None, fails,
           f"B-4 canary: an unplayed game carries a score: {_w5 and _w5[0]}")
    _names = {"KC": "Chiefs", "DEN": "Broncos", "BUF": "Bills"}
    _r4 = _sb._week_row(_w4[0], _names)
    _check(">31<" in _r4 and ">10<" in _r4, fails,
           "B-4 canary: the played fixture did not print its result")
    _r5 = _sb._week_row(_w5[0], _names)
    _check("0" not in _r5.replace("2026", "").replace("05", ""), fails,
           f"B-4 canary: an unplayed fixture printed a zero: {_r5!r}")
    # timeValid false means the league has not set the clock, only the date.
    _check("PM ET" not in _r5 and "AM ET" not in _r5, fails,
           f"B-4 canary: a kickoff the league has not set printed a precise time: {_r5!r}")
    _check("PM ET" in _r4, fails,
           "B-4 canary: a kickoff the league HAS set printed no time, so the check "
           "above passes for the wrong reason")
    _sel = _sb.week_selector(3, 2)
    _check(_sel.count('aria-current="page"') == 1, fails,
           "B-4 canary: the week being read is not marked for a screen reader")
    _check('wk-b on' in _sel and 'wk-b now' in _sel, fails,
           "B-4 canary: the week being read and the week the season is in are not "
           "distinguished, so a reader in week 6 in November cannot tell them apart")

    # B-3: THE LENS. A tab chooses which games are on the board; a lens chooses which
    # facts each card shows. The whole mechanism is one attribute per part, so what has
    # to hold is the CONTRACT: the parts that belong to a lens declare it, and the parts
    # that belong to every lens declare nothing, because a part that wrongly declares one
    # disappears under the other three and the page still builds and still looks right on
    # the lens it was written for.
    _lc = _sb.lens_control()
    _check(" hidden" in _lc, fails,
           "B-3 canary: the lens control does not ship hidden, so a reader with no "
           "JavaScript is shown four buttons that do nothing")
    _check(_lc.count("<button") == 4, fails,
           f"B-3 canary: the control does not carry four lenses: {_lc.count('<button')}")
    _check(_lc.count('aria-pressed="true"') == 1, fails,
           "B-3 canary: the control does not have exactly one lens pressed")
    _check(">Lines<" in _lc and ">Bets<" not in _lc, fails,
           "B-3 canary: the lens is named for an activity the desk does not do. The "
           "desk shows a line as a fact and makes no bet.")

    _gl = _gb("NFL", "IND", "KC", "2026-09-27T20:20", "pre")
    _gl["network"] = "NBC"
    _gl["line"] = {"provider": "DraftKings", "detail": "KC -6.5", "total": 47.5}
    _gl["away"]["id"], _gl["home"]["id"] = "11", "12"
    _gl["away"]["name"], _gl["home"]["name"] = "Colts", "Chiefs"
    # A nameless team must cost one line and never the build: "".split()[-1] raises.
    _gn = dict(_gl, id="NONAME")
    _gn["away"] = dict(_gl["away"], name="")
    _sb._tk_card(_gn, {}, desig={"chiefs": {"out": 2}}, items=[])
    _cardl = _sb._tk_card(_gl, {}, items=[])
    # NOT the countdown. Owner's ruling of 21 September: it ticks on the marquee only,
    # so a band card no longer has one and this loop would be asserting that a thing
    # which must not be there declares a lens. The marquee's own countdown is checked
    # below instead, which is where it now lives.
    for _part, _lens in (('class="tk-line"', "lines"),
                         ('class="tk-chip"', "watch")):
        _i = _cardl.find(_part)
        _check(_i >= 0 and f'data-lens-only="{_lens}"' in _cardl[_i - 60:_i + 120], fails,
               f"B-3 canary: {_part} does not declare the {_lens} lens, so it vanishes "
               f"under every lens including its own")
    # The score, the teams and the desk's own story belong to EVERY lens. A declaration
    # on any of them would empty the card.
    # THE COUNTDOWN IS THE MARQUEE'S AND NOWHERE ELSE. Twelve counters on a phone is
    # noise on the page and a minute of work every minute for the poll, on the battery.
    _check('data-countdown' not in _cardl, fails,
           "B-3 canary: a band card carries a ticking countdown; the ruling of 21 "
           "September puts it on the marquee only and a row states its kickoff in "
           "Eastern without moving")
    _check("data-countdown" in _sb._tk_countdown(_gl, marquee=True), fails,
           "B-3 canary: the marquee lost its countdown, so no game counts down at all")
    _check(_sb._tk_countdown(_gl) == "", fails,
           "B-3 canary: the card countdown is not switched off at the source")

    _mu = _cardl.find('class="tk-mu"')
    _check(_mu >= 0 and 'data-lens-only' not in _cardl[_mu:_mu + 90], fails,
           "B-3 canary: the matchup declared a lens, so three of the four lenses would "
           "show a card with no teams and no score on it")

    # D-2: A FORECAST IS ONLY A FORECAST WHILE IT IS IN THE FUTURE. Checkpoint 4 read
    # "Sunday's lists post about 6:50 PM ET" at 9:20 PM on Sunday, beside the page's own
    # count of 29 lists already posted, because the summary forecast from the earliest
    # game still without a list whether or not that game had kicked off hours earlier.
    # Checkpoint 3 found the same shape on the 4:05 and 4:25 cards. Third sighting.
    import datetime as _d2
    _n2 = _sb._build_now()

    def _g2(hours):
        _k = _n2 + _d2.timedelta(hours=hours)
        return {"id": f"g{hours}", "away_id": "1", "home_id": "2",
                "kickoff_utc": _k.strftime("%Y-%m-%dT%H:%M:%SZ")}

    # One game three hours gone with no list, one kicking the evening after next. The
    # gap is 30 hours and not 21 deliberately: at 21 the forecast time and the passed
    # game's time are the same clock reading a day apart, so a test that quoted one
    # would silently accept the other.
    _sum = _sb._ia_week_summary({"teams": []}, [_g2(-3), _g2(30)])
    _check("no list yet for 2 teams" in _sum, fails,
           f"D-2 canary: a game three hours past kickoff with no list was not reported "
           f"as one the desk is holding nothing for, counted per team: {_sum!r}")
    _check(_sum.count("post about") == 1, fails,
           f"D-2 canary: the summary forecast more than one posting time: {_sum!r}")
    _fc = _n2 + _d2.timedelta(hours=30) - _d2.timedelta(minutes=90)
    _check(_sb._et_clock(_fc) in _sum, fails,
           f"D-2 canary: the forecast did not come from the game still ahead: {_sum!r}")
    # and the past game's own time must not be the one quoted.
    _past = _sb._et_clock(_n2 - _d2.timedelta(hours=3) - _d2.timedelta(minutes=90))
    _check(_past not in _sum, fails,
           f"D-2 canary: the summary forecast a posting time that has already passed "
           f"({_past}): {_sum!r}")
    # with nothing waiting at all, neither sentence appears.
    _clean = _sb._ia_week_summary(
        {"teams": [{"id": "1", "count": 5, "first_seen": "2026-09-20",
                    "by_day": {}}]}, [])
    _check("post about" not in _clean and "no list yet" not in _clean, fails,
           f"D-2 canary: a week with nothing waiting still forecast something: {_clean!r}")

    # C-1: THE LINE AT OPEN. ESPN carries its odds object only while a game is still
    # scheduled and drops it at kickoff: measured on the Sunday night slate, 0 of 61
    # finals and 0 of 6 live games carried one. So the open line is whatever the last
    # build logged before kickoff, the cover ruling on a final has no other source, and
    # a logger that quietly forgets the open reading takes both clauses of the law with
    # it while every page still builds clean.
    import lines as _ln
    import tempfile as _tf, os as _lo
    _lsave = _ln.OUT
    _ln.OUT = _lo.path.join(tempfile_dir := _tf.mkdtemp(), "lines.json")
    try:
        def _lg(detail, total, kick="2026-09-27T17:00:00Z"):
            return [{"id": "L1", "start_utc": kick,
                     "line": {"provider": "DraftKings", "detail": detail,
                              "spread": -6.5, "total": total}}]
        _d1 = _ln.log(_lg("KC -6", 46.5))
        _d2 = _ln.log(_lg("KC -6.5", 47.5))
        _r = _ln.for_game(_d2, "L1")
        _check(_r and (_r["open"] or {}).get("detail") == "KC -6", fails,
             f"C-1 canary: the open line was overwritten by a later reading: "
             f"{(_r or {}).get('open')}")
        _check(_r and (_r["now"] or {}).get("detail") == "KC -6.5", fails,
             "C-1 canary: the latest reading was not kept")
        _check(_r and int(_r.get("moves") or 0) == 1, fails,
             f"C-1 canary: the move was not counted: {(_r or {}).get('moves')}")

        # An expired game leaves the file; a live one does not go with it.
        _old = _ln.log([{"id": "OLD", "start_utc": "2020-01-01T00:00:00Z",
                         "line": {"provider": "DraftKings", "detail": "X -1"}}])
        _check("OLD" not in (_old.get("games") or {}), fails,
             "C-1 canary: a game months past its kickoff stayed in the file")
        _check("L1" in (_old.get("games") or {}), fails,
             "C-1 canary: the expiry sweep took a live game with it")

        # THE RULING. Arithmetic on two numbers, stated only about a named provider's
        # line, and a tie on either number is a push.
        _sb.LINES_DATA = _d2

        def _fin(sa, sh, total=47.5, detail="KC -6.5"):
            return {"id": "L1", "state": "post", "league": "NFL",
                    "away": {"abbr": "IND", "score": str(sa), "id": "11"},
                    "home": {"abbr": "KC", "score": str(sh), "id": "12"},
                    "line": {"provider": "DraftKings", "detail": detail,
                             "total": total}}
        _cov = _sb._tk_ruling(_fin(10, 24))      # KC by 14, over 6.5, 34 under 47.5
        _check("KC covered" in _cov, fails,
             f"C-1 canary: a 14-point win by a 6.5-point favourite did not cover: {_cov}")
        _check("Under 47.5" in _cov, fails,
             f"C-1 canary: 34 points did not read as under 47.5: {_cov}")
        _no = _sb._tk_ruling(_fin(21, 24))       # KC by 3, under 6.5, 45 under
        _check("KC did not cover" in _no, fails,
             f"C-1 canary: a 3-point win by a 6.5-point favourite covered: {_no}")
        _psh = _sb._tk_ruling(_fin(20, 26, 46, "KC -6"))   # exactly 6, exactly 46
        _check("KC pushed" in _psh and "Pushed 46" in _psh, fails,
             f"C-1 canary: an exact spread and an exact total were not pushes: {_psh}")
        _ovr = _sb._tk_ruling(_fin(31, 24, 47.5))
        _check("Over 47.5" in _ovr, fails,
             f"C-1 canary: 55 points did not read as over 47.5: {_ovr}")
        # The favourite comes from the detail string, never from the spread's sign: the
        # away side favoured must rule on the away side's margin.
        _awy = _sb._tk_ruling(_fin(30, 10, 47.5, "IND -6.5"))
        _check("IND covered" in _awy, fails,
             f"C-1 canary: an away favourite was ruled on the home team's margin: {_awy}")
        # No provider, no ruling, WHATEVER THE NUMBERS SAY. The first cut of this test
        # stripped the provider and the numbers together, so the ruling came back empty
        # because there was nothing to rule on, and the test passed with the attribution
        # guard deleted. The fixture keeps every number and removes only the name.
        _bare = dict(_fin(10, 24))
        _bare["line"] = {"detail": "KC -6.5", "total": 47.5}
        _sb.LINES_DATA = {"games": {}}
        _check(_sb._tk_ruling(_bare) == "", fails,
             "C-1 canary: a cover was ruled with no provider named")
        # and the same line WITH a name does rule, so the test above is about the name
        # and not about the fixture being unrulable.
        _named = dict(_bare)
        _named["line"] = dict(_bare["line"], provider="DraftKings")
        _check("KC covered" in _sb._tk_ruling(_named), fails,
             "C-1 canary: the attribution fixture cannot be ruled even when named, so "
             "the guard above proves nothing")
    finally:
        _ln.OUT = _lsave
        _sb.LINES_DATA = None

    # SC-3 (M-20, M-21): THE MARQUEE. Four shapes, on one fixture slate, because the
    # rule is about WHEN it is asked, not about what is on the board. On 17 Sep the
    # front page put a 0-0 Mets game in the marquee eight minutes before the only NFL
    # game of the night, and by 9 the next morning it had replaced the Bills result with
    # a 3 PM soccer fixture.
    import datetime as _dt3
    _ET3 = _sb._ET

    def _g3(league, away, home, kick_et, state, sa=None, sh=None):
        _k = _dt3.datetime.fromisoformat(kick_et).replace(tzinfo=_ET3) \
                 .astimezone(_dt3.timezone.utc)
        return {"league": league, "id": f"{away}{home}{kick_et}", "state": state,
                "start_utc": _k.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "away": {"abbr": away, "name": away, "score": sa},
                "home": {"abbr": home, "name": home, "score": sh}}

    def _at3(s):
        return _dt3.datetime.fromisoformat(s).replace(tzinfo=_ET3) \
                   .astimezone(_dt3.timezone.utc)

    def _mq3(games, when):
        m = _sb._sb_marquee_pick(games, _at3(when))
        return f"{m['away']['abbr']} at {m['home']['abbr']}" if m else None

    # Thursday night: the NFL game at 8:15, live MLB and WNBA alongside, and Sunday's
    # NFL slate already on the board.
    _thu = [_g3("NFL", "DET", "BUF", "2026-09-17T20:15", "pre"),
            _g3("MLB", "CHC", "CIN", "2026-09-17T19:10", "in", "2", "1"),
            _g3("WNBA", "CON", "ATL", "2026-09-17T19:30", "in", "70", "69"),
            _g3("NFL", "CAR", "ATL", "2026-09-20T13:00", "pre"),
            _g3("Soccer", "CHE", "BRE", "2026-09-18T15:00", "pre")]
    _check(_mq3(_thu, "2026-09-17T19:30") == "DET at BUF", fails,
           f"SC-3 canary: 45 minutes before kickoff the marquee was "
           f"{_mq3(_thu, '2026-09-17T19:30')}, not the NFL game")
    # the exact build that got it wrong: the 8:06 PM inactives snapshot
    _check(_mq3(_thu, "2026-09-17T20:06") == "DET at BUF", fails,
           f"SC-3 canary: the last snapshot before kickoff chose "
           f"{_mq3(_thu, '2026-09-17T20:06')}")
    # and two hours out it is NOT yet imminent, so a live game of another league leads
    _check(_mq3(_thu, "2026-09-17T18:00") != "DET at BUF", fails,
           "SC-3 canary: an NFL game two hours out took the marquee from a live game")

    _live = [dict(g) for g in _thu]
    _live[0].update(state="in", away={"abbr": "DET", "name": "DET", "score": "10"},
                    home={"abbr": "BUF", "name": "BUF", "score": "14"})
    _check(_mq3(_live, "2026-09-17T21:00") == "DET at BUF", fails,
           f"SC-3 canary: a live NFL game lost the marquee to "
           f"{_mq3(_live, '2026-09-17T21:00')}")

    # By Friday morning last night's games are all final: a Thursday 7:10 PM baseball
    # game is not still live at 9 AM, and a fixture that says so is testing a board that
    # cannot happen.
    _fin = [dict(g) for g in _thu]
    _fin[0].update(state="post", away={"abbr": "DET", "name": "DET", "score": "31"},
                   home={"abbr": "BUF", "name": "BUF", "score": "41"})
    _fin[1].update(state="post")
    _fin[2].update(state="post")
    _check(_mq3(_fin, "2026-09-18T09:00") == "DET at BUF", fails,
           f"SC-3 canary: the morning after, the marquee was "
           f"{_mq3(_fin, '2026-09-18T09:00')}, not the night's result")
    _check(_mq3(_fin, "2026-09-18T12:30") != "DET at BUF", fails,
           "SC-3 canary: the final still held the marquee after noon the next day")
    # Sunday: the 1 PM slate takes over from inside ninety minutes
    _check(_mq3(_fin, "2026-09-20T12:30") == "CAR at ATL", fails,
           f"SC-3 canary: at 12:30 on Sunday the marquee was "
           f"{_mq3(_fin, '2026-09-20T12:30')}, not the 1 PM slate")
    # M-20: upcoming sorts by league before kickoff
    _up = [_g3("Soccer", "CHE", "BRE", "2026-09-19T15:00", "pre"),
           _g3("NFL", "CAR", "ATL", "2026-09-20T13:00", "pre")]
    _check(_mq3(_up, "2026-09-19T09:00") == "CAR at ATL", fails,
           f"SC-3 canary: an earlier soccer fixture outranked the NFL game "
           f"({_mq3(_up, '2026-09-19T09:00')})")
    # M-21: a recent final outranks an upcoming game in the card order
    _check(_sb._sb_state_rank(_fin[0], _at3("2026-09-18T09:00"))
           < _sb._sb_state_rank(_thu[3], _at3("2026-09-18T09:00")), fails,
           "SC-3 canary: a final from last night ranked below a fixture three days out")

    # N-7b: A LISTING BELONGS TO THE DAY IT WAS SEEN, AND A REPEAT IS TWO LISTINGS.
    # The merge kept a player once, at his first sighting, so a player inactive on the
    # 13th and again on the 17th carried only the 13th and the 17th's list undercounted
    # him. It keeps every sighting now, keyed on the Eastern day it was seen, with one
    # exception that is not an exception: a list put up for a Sunday game is still on
    # the feed on Monday, and an NFL team never plays on consecutive days, so a sighting
    # on the day after a day the player was already seen is the same list still
    # standing.
    import tempfile as _tf7, os as _os7, json as _js7
    import inactives as _ia7
    _t7 = _tf7.mkdtemp()

    def _snap7(day, stamp, names):
        _js7.dump({"day": day, "last_poll": stamp, "teams": {"2": {
            "id": "2", "team": "Acme Rockets",
            "players": {n: {"name": n, "pos": "DT", "first_seen": stamp}
                        for n in names}}}},
            open(_os7.path.join(_t7, f"inactives-{day}.json"), "w"))

    # Sunday's list, the same list still on the feed on Monday, then Thursday's list.
    _snap7("2026-09-13", "2026-09-13T18:03:08Z", ["Repeat Player", "Week One Only"])
    _snap7("2026-09-14", "2026-09-14T13:00:00Z", ["Repeat Player", "Week One Only"])
    _snap7("2026-09-17", "2026-09-17T23:06:43Z", ["Repeat Player", "Week Two Only"])
    _old7 = _ia7.SNAP_DIR
    try:
        _ia7.SNAP_DIR = _t7
        _b7 = _ia7.board()
        _tm7 = _b7["teams"][0]
        _days7 = {d["day"]: [p["name"] for p in d["players"]] for d in _tm7["by_day"]}
        _check(sorted(_days7) == ["2026-09-13", "2026-09-17"], fails,
               f"N-7b canary: listings grouped under {sorted(_days7)}, expected the "
               f"13th and the 17th (Monday is Sunday's list still standing)")
        _check("Repeat Player" in _days7.get("2026-09-13", []), fails,
               "N-7b canary: the repeat is missing from the 13th")
        _check("Repeat Player" in _days7.get("2026-09-17", []), fails,
               "N-7b canary: the repeat is missing from the 17th")
        _check("Week Two Only" in _days7.get("2026-09-17", []), fails,
               "N-7b canary: the 17th's own listing is missing")
        _check(_tm7["first_seen"].startswith("2026-09-17"), fails,
               f"N-7b canary: the team is stamped {_tm7['first_seen']}, "
               f"not its latest list")
        _seen7 = {}
        for d in _tm7["by_day"]:
            for _pp in d["players"]:
                _seen7.setdefault(_pp["name"], set()).add(_pp.get("first_seen"))
        _check(len(_seen7.get("Repeat Player", set())) == 2, fails,
               "N-7b canary: the repeat's two listings do not carry their own dates")
        # and a stray file in the directory must not take a real day's place
        _js7.dump({"day": "x", "teams": {}},
                  open(_os7.path.join(_t7, "inactives-2026-09-17 2.json"), "w"))
        _js7.dump({"day": "x", "teams": {}},
                  open(_os7.path.join(_t7, "inactives-backup.json"), "w"))
        # A window of three must be the three latest DATES, not the three last
        # filenames: with the old slice the two strays and one real file were the
        # window and two real days fell out.
        _w7 = _ia7.load_week(days=3) or {"teams": {}}
        _days7b = sorted({p.get("day") for t in (_w7.get("teams") or {}).values()
                          for p in (t.get("players") or {}).values() if p.get("day")})
        # Two days, not three: the 14th is the 13th's list still standing, so it
        # carries the 13th's date. What this proves is that the 13th survived a window
        # of three; with the old filename slice the strays took its place and the
        # window held only the 17th.
        _check(_days7b == ["2026-09-13", "2026-09-17"], fails,
               f"N-7b canary: stray files took a real day's place; window held "
               f"{_days7b}")
    finally:
        _ia7.SNAP_DIR = _old7

    # A-5: THE FANTASY CORRECTIONS. Each one was a shallow test answering yes about
    # the whole week when the question was about one game.
    import datetime as _dt5
    _ET5 = _sb._ET

    def _gm5(away, home, aid, hid, kick_et):
        _k = _dt5.datetime.fromisoformat(kick_et).replace(tzinfo=_ET5) \
                  .astimezone(_dt5.timezone.utc)
        return {"away": away, "home": home, "away_id": aid, "home_id": hid,
                "kickoff_utc": _k.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kickoff_et": "1:00 PM ET", "day_et": "Sun 20 Sep"}

    def _pl5(name, seen_et):
        _t = _dt5.datetime.fromisoformat(seen_et).replace(tzinfo=_ET5) \
                  .astimezone(_dt5.timezone.utc)
        return {"name": name, "pos": "WR", "day": seen_et[:10],
                "first_seen": _t.strftime("%Y-%m-%dT%H:%M:%SZ")}

    # ATL's list is up for the 1 PM game; TEN's 4:25 list is not.
    _atl5 = {"team": "Atlanta Falcons", "id": "1", "count": 1,
             "players": [_pl5("Posted Player", "2026-09-20T11:31")],
             "first_seen": "2026-09-20T15:31:00Z"}
    _ten5 = {"team": "Tennessee Titans", "id": "10", "count": 1,
             "players": [_pl5("Last Week Only", "2026-09-13T14:03")],
             "first_seen": "2026-09-13T18:03:00Z"}
    _board5 = {"teams": [_atl5, _ten5], "total": 2}
    _w2w5 = {"weeks": [{"week": 2, "games": [
        _gm5("CAR", "ATL", "29", "1", "2026-09-20T13:00"),
        _gm5("PHI", "TEN", "21", "10", "2026-09-20T16:25")]}]}

    _old5 = getattr(_sb, "W2W_DATA", None)
    _oldwk = _sb._ia_week
    try:
        _sb.W2W_DATA = _w2w5
        _sb._ia_week = lambda: (2, False)
        # the flag only where the list has posted
        _r_atl = _sb._dg_ruling({"team": "Atlanta Falcons", "name": "Posted Player"},
                                _board5, _w2w5, set())
        _check("active" in _r_atl, fails,
               f"A-5 canary: a posted list produced no ruling: {_r_atl!r}")
        _r_ten = _sb._dg_ruling({"team": "Tennessee Titans", "name": "Someone"},
                                _board5, _w2w5, set())
        _check("active" not in _r_ten and "inactive" not in _r_ten, fails,
               f"A-5 canary: a team whose list has not posted was ruled on: {_r_ten!r}")
        _check("posts about" in _r_ten, fails,
               f"A-5 canary: the row did not say when the list posts: {_r_ten!r}")
        # the hub counts the week, not the merge
        _lists, _players = _sb._ia_week_totals(_board5, _w2w5)
        _check((_lists, _players) == (1, 1), fails,
               f"A-5 canary: the hub counted {_lists} lists and {_players} players, "
               f"not this week's one and one")
    finally:
        _sb.W2W_DATA = _old5
        _sb._ia_week = _oldwk

    # the league tag is checked against the teams the story names
    _sb._TEAM_VOCAB = {"NFL": {"Buffalo Bills", "Detroit Lions", "Atlanta Falcons"},
                       "CFB": {"Vanderbilt", "NC State"}}
    _vandy = {"title": "Vanderbilt defeats NC State 35-31 on a final-play fumble",
              "dek": "", "tags": ["nfl", "scores-results", "college"]}
    _check(_sb._league_from_teams(_vandy) == "CFB", fails,
           "A-5 canary: a college recap did not read as college from its teams")
    _check("nfl" not in [t.lower() for t in _sb.display_tags(_vandy)], fails,
           f"A-5 canary: the nfl chip survived on a college recap: "
           f"{_sb.display_tags(_vandy)}")
    _bills = {"title": "Buffalo Bills open Highmark Stadium against the Detroit Lions",
              "dek": "", "tags": ["nfl"]}
    _check(_sb._league_from_teams(_bills) == "NFL", fails,
           "A-5 canary: an NFL story did not read as NFL from its teams")
    # NO EVIDENCE MEANS NO OVERRIDE. The vocabulary is full names, because half the
    # NFL's nicknames are ordinary English, so a story that only says "Bills" gives
    # this check nothing to go on and keeps exactly the tags the desk gave it.
    _nick = {"title": "Bills open Highmark Stadium in a Lions matchup", "dek": "",
             "tags": ["nfl"]}
    _check(_sb._league_from_teams(_nick) == "", fails,
           "A-5 canary: a bare nickname was treated as evidence of a league")
    _check([t.lower() for t in _sb.display_tags(_nick)] == ["nfl"], fails,
           f"A-5 canary: a story with no team evidence lost its tag: "
           f"{_sb.display_tags(_nick)}")
    _sb._TEAM_VOCAB = {"NFL": set(), "CFB": {"Buffalo"}}
    _check(_sb._league_from_teams(_bills) == "", fails,
           "A-5 canary: the check ran without an NFL vocabulary to subtract")
    _sb._TEAM_VOCAB = None

    # N-7c: A LISTING BELONGS TO A GAME. N-7b kept every sighting with its own date,
    # which is right, and the page still grouped by team across the whole eight-day
    # window: on Friday /fantasy/inactives read "Week 2 inactives, 207 players, 31
    # teams" when Week 2 had two lists and fourteen players, Detroit's section under DET
    # at BUF carried its 13 September list as well, and the homepage rail said Sunday's
    # lists were posted.
    import datetime as _dt7c
    _ET7 = _sb._ET

    def _gm7(away, home, aid, hid, kick_et):
        _k = _dt7c.datetime.fromisoformat(kick_et).replace(tzinfo=_ET7) \
                  .astimezone(_dt7c.timezone.utc)
        return {"away": away, "home": home, "away_id": aid, "home_id": hid,
                "kickoff_utc": _k.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kickoff_et": "8:15 PM ET", "day_et": "Thu 17 Sep"}

    def _pl7(name, seen_et, day):
        _t = _dt7c.datetime.fromisoformat(seen_et).replace(tzinfo=_ET7) \
                  .astimezone(_dt7c.timezone.utc)
        return {"name": name, "pos": "DT", "day": day,
                "first_seen": _t.strftime("%Y-%m-%dT%H:%M:%SZ")}

    # Detroit carries both weeks' listings, as the board does after N-7b.
    _det7 = {"team": "Detroit Lions", "id": "8", "count": 3,
             "players": [_pl7("Week Two Player", "2026-09-17T19:05", "2026-09-17"),
                         _pl7("Both Weeks", "2026-09-17T19:05", "2026-09-17"),
                         _pl7("Week One Only", "2026-09-13T14:03", "2026-09-13")],
             "first_seen": "2026-09-17T23:05:00Z"}
    _buf7 = {"team": "Buffalo Bills", "id": "2", "count": 2,
             "players": [_pl7("Bills One", "2026-09-17T19:06", "2026-09-17"),
                         _pl7("Bills Two", "2026-09-17T19:06", "2026-09-17")],
             "first_seen": "2026-09-17T23:06:00Z"}
    _car7 = {"team": "Carolina Panthers", "id": "29", "count": 2,
             "players": [_pl7("Panther One", "2026-09-13T14:03", "2026-09-13"),
                         _pl7("Panther Two", "2026-09-13T14:03", "2026-09-13")],
             "first_seen": "2026-09-13T18:03:00Z"}
    _board7 = {"teams": [_det7, _buf7, _car7], "total": 7}
    _games7 = [_gm7("DET", "BUF", "8", "2", "2026-09-17T20:15"),
               _gm7("CAR", "ATL", "29", "1", "2026-09-20T13:00")]

    _got7 = _sb._ia_team_for_game(_det7, _games7[0])
    _check(_got7 and _got7["count"] == 2, fails,
           f"N-7c canary: Detroit's section under DET at BUF held "
           f"{_got7 and _got7['count']} listings, not the two from that game")
    _check(_got7 and all("Week One" not in p["name"] for p in _got7["players"]), fails,
           "N-7c canary: a 13 September listing appeared under the 17 September game")
    _check(_sb._ia_team_for_game(_car7, _games7[1]) is None, fails,
           "N-7c canary: Carolina showed a list for a game whose list has not posted")
    _sum7 = _sb._ia_week_summary(_board7, _games7)
    _check(_sum7.startswith("2 lists posted, 4 players"), fails,
           f"N-7c canary: the header read {_sum7!r}, not this week's lists")
    # D-2: this assertion used to read "post about 11:30 AM ET" from a 20 September
    # fixture, which is a forecast of a time that passed months ago and is the exact
    # defect checkpoint 4 found on the live page. The fixture keeps its posted lists and
    # gains a game that is genuinely ahead, so the header is still tested for saying
    # when the rest post, against a game where "the rest" are still to come.
    import datetime as _d7
    _ahead7 = (_sb._build_now() + _d7.timedelta(hours=26))
    _games7b = _games7 + [_gm7("NYJ", "MIA", "20", "15",
                               _ahead7.astimezone(_sb._ET).strftime("%Y-%m-%dT%H:%M"))]
    _sum7b = _sb._ia_week_summary(_board7, _games7b)
    _check("post about " + _sb._et_clock(_ahead7 - _d7.timedelta(minutes=90))
           in _sum7b, fails,
           f"N-7c canary: the header did not say when the rest post: {_sum7b!r}")
    _check("post about" not in _sum7, fails,
           f"N-7c canary: a slate whose games have all kicked off still forecast a "
           f"posting time (D-2): {_sum7!r}")
    _check("posts about" in _sb._ia_expected(_games7[1]), fails,
           f"N-7c canary: the awaiting card read {_sb._ia_expected(_games7[1])!r}")
    # and nothing is lost: what is not this week's is on the earlier page
    _earlier7 = _sb._ia_earlier(_board7, _games7)
    _n7 = sum(t["count"] for t in _earlier7)
    _check(_n7 == 3, fails,
           f"N-7c canary: {_n7} earlier listings kept, expected the 3 from 13 September")

    # H-1: THIS GAME'S LIST COMES FROM THIS GAME'S DAY, NOT THE WEEK'S MERGE.
    # board() merges eight days and keeps a player's FIRST sighting, so a team that had
    # a list in Week 1 carries a Week 1 stamp forever and the game-page window rejected
    # it for every later game; a player inactive in both weeks also kept his Week 1
    # stamp and vanished from Week 2's list. On 17 Sep that left tonight's game page
    # saying "post about 6:45 PM ET" at 7:07 PM with both lists already up.
    import tempfile as _tf, os as _os1, json as _js1, datetime as _dt1
    import inactives as _ia1
    _kick = _dt1.datetime.now(_dt1.timezone.utc) + _dt1.timedelta(hours=1)
    _day = _kick.astimezone(_sb._ET).strftime("%Y-%m-%d")
    _tmp = _tf.mkdtemp()
    _js1.dump({"day": _day, "teams": {"2": {
        "id": "2", "team": "Acme Rockets",
        "players": {"p1": {"name": "Tonight Player", "pos": "DT",
                           "first_seen": (_kick - _dt1.timedelta(minutes=90))
                           .strftime("%Y-%m-%dT%H:%M:%SZ")}}}}},
        open(_os1.path.join(_tmp, f"inactives-{_day}.json"), "w"))
    _old_dir = _ia1.SNAP_DIR
    try:
        _ia1.SNAP_DIR = _tmp
        _g1 = {"league": "NFL", "start_utc": _kick.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "home": {"id": "2", "abbr": "ACM"}, "away": {"id": "99", "abbr": "OTH"}}
        # the merged board says this team was last seen a week ago
        _stale = {("NFL", "2"): {"team": "Acme Rockets", "id": "2", "count": 8,
                                 "first_seen": (_kick - _dt1.timedelta(days=4))
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"), "players": []}}
        _got1 = _sb._ia_for_game(_g1, _stale, "home")
        _check(bool(_got1), fails,
               "H-1 canary: tonight's day-file list was rejected because the week's "
               "merge stamped the team with an earlier week")
        _check(bool(_got1) and _got1.get("count") == 1, fails,
               f"H-1 canary: wrong list returned: {_got1 and _got1.get('count')}")
        # and a team with no list for this day still returns nothing
        _g2 = dict(_g1, home={"id": "77", "abbr": "NON"})
        _check(_sb._ia_for_game(_g2, {}, "home") is None, fails,
               "H-1 canary: a team with no list for this game returned one")
    finally:
        _ia1.SNAP_DIR = _old_dir

    # H-6: THE COUNT LINE NAMES WHAT THE TAB HOLDS. A panel showing fifteen final
    # scorecards said "No games today - 1 game Thursday", because the finals branch sat
    # after the upcoming-games branch and a pool that holds yesterday's finals almost
    # always holds the next fixture too. Finals are named first when the panel has them.
    import datetime as _dt6
    import re as _re6
    import site_build as _sb
    _now6 = _dt6.datetime.now(_dt6.timezone.utc)

    def _g6(state, dd):
        # ANCHORED IN EASTERN, not in UTC. This built "yesterday" as now-1day at 23:10
        # UTC, and after 8 PM Eastern the UTC date has already rolled, so the finals
        # landed at 7:10 PM TODAY and the count line correctly said "15 games today".
        # A fixture that changes meaning with the hour it runs at is not a fixture.
        _et_now = _now6.astimezone(_sb._ET)
        _t = (_et_now + _dt6.timedelta(days=dd)).replace(
            hour=19, minute=10, second=0, microsecond=0).astimezone(_dt6.timezone.utc)
        return {"league": "MLB", "id": f"x{dd}{state}", "state": state,
                "status_short": "Final" if state == "post" else "",
                "start_utc": _t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "away": {"abbr": "PHI", "name": "Phillies", "score": "4"},
                "home": {"abbr": "NYM", "name": "Mets", "score": "2"}}

    def _count6(games):
        _h = _sb.scoreboard_band({"leagues": [{"league": "MLB", "games": games}],
                                  "fetched_at": _now6.strftime("%Y-%m-%dT%H:%M:%SZ")},
                                 None, None)
        _m = _re6.findall(r'class="tk-count"[^>]*>([^<]*)<', _h)
        return _m[0] if _m else ""

    _c6 = _count6([_g6("post", -1) for _ in range(15)] + [_g6("pre", 7)])
    _check(_c6.startswith("15 final"), fails,
           f"H-6 canary: a panel of 15 finals plus an upcoming game said {_c6!r}")
    _check("next" in _c6, fails,
           f"H-6 canary: the finals line did not name the next fixture: {_c6!r}")
    _c6b = _count6([_g6("pre", 1) for _ in range(3)])
    _check(_c6b.startswith("No games today"), fails,
           f"H-6 canary: a panel with only upcoming games said {_c6b!r}")

    # S-L3 DATA-ABBR CARRIES AN ABBREVIATION. The folded band rows put the side name in
    # data-abbr ("away", "home"), so anything reading that attribute across the band met
    # 34 of each before it met a single team, and the my-teams reorder silently matched
    # nothing. The attribute is a contract now: the side lives in data-side.
    _fold = _sb._tk_fold({"league": "NFL", "state": "pre",
                          "away": {"abbr": "BUF", "name": "Bills", "score": None},
                          "home": {"abbr": "DET", "name": "Lions", "score": None}}, {}) \
        if hasattr(_sb, "_tk_fold") else ""
    if _fold:
        import re as _re2
        _abbrs = _re2.findall(r'data-abbr="([^"]*)"', _fold)
        _check(_abbrs and not ({"away", "home"} & set(_abbrs)), fails,
               f"band canary: data-abbr carries a side name, not a team: {_abbrs[:4]}")

    # TAG-INTEGRITY REGRESSION (owner directive 2026-07-28, proven test case): the
    # "Severe weather" chip once linked a Tour de France story whose dek mentioned a
    # wildfire once. That exact mismatch must fail the build forever.
    import re as _re
    import site_build as _sb
    _rx = _re.compile(r"\b(?:hurricane|tropical storm|landfall|wildfire|evacuation order)\b", _re.I)
    _tdf = {"title": "Tadej Pogacar wins 2026 Tour de France, his fifth title",
            "dek": "The final stage was shortened due to police reassignment for "
                   "wildfire emergency response in southwest France.",
            "key_fact": "Pogacar sealed the win in Paris."}
    _wx = {"title": "Wildfire advances to nine miles from Bordeaux amid evacuation order",
           "dek": "Crews battled the blaze overnight.", "key_fact": "42,000 hectares burned."}
    _check(_sb.tracking_match(_tdf, _rx) is False, fails,
           "tag integrity: a passing 'wildfire' mention still hijacks the Severe weather "
           "chip (the exact 2026-07-27 mislink)")
    _check(_sb.tracking_match(_wx, _rx) is True, fails,
           "tag integrity: a genuine severe-weather story no longer matches its chip")

    # full offline replay end-to-end over the fixture
    e2e_fails = _replay_e2e()
    fails.extend(e2e_fails)
    fails.extend(_dedupe_guard_canary())
    fails.extend(_boundary_canary())
    fails.extend(_merge_state_canary())
    fails.extend(_edition_repair_canary())

    # fail-closed canaries
    fails.extend(_failclosed_canaries(cfg))

    # contract ladder + slot recovery (the 2026-07-15 self-healing layer)
    fails.extend(_contract_ladder_canary(cfg))

    if fails:
        for f in fails:
            gh("error", "canary: " + f)
        print(f"\nLAYER 1 CANARY: FAIL ({len(fails)} problem(s)) -> promotion BLOCKED (exit 1)")
        return 1
    print("LAYER 1 CANARY: PASS -> pipeline wired, shill/dedupe belts work, offline replay "
          "end-to-end produces a DRAFT-tagged review queue, and every fail-closed gate holds.")
    return 0


def _boundary_canary():
    """The inverted-advisory failure, pinned as fixtures.

    On 2026-07-30 the desk drafted a hardware-wallet firmware advisory twice and the approver
    rejected it twice on accuracy, correctly: the second draft implied users on the PATCHED
    version were the ones at risk. These cases lock the four properties that stop that draft
    ever existing, plus the one case that must still publish, because a gate that holds every
    security story is just a slower way to leave readers uninformed."""
    fails = []
    import boundary as bnd
    import publish as pubmod
    import researcher
    import writer

    # CHASSIS SYNC, same discipline as dedupe.py: one file, three repositories, one hash.
    _sha = __import__("hashlib").sha256(open(bnd.__file__, "rb").read()).hexdigest()[:16]
    _check(_sha == "0cf27e0f447f1031", fails,
           f"boundary: this desk's boundary.py is {_sha}, the chassis copy is 0cf27e0f447f1031. "
           f"The module was changed in one repo and not the others; re-sync all three.")

    # (1) CLASSIFICATION. A firmware advisory with a version in it is boundary-class; a
    # security story with no boundary in it is not, or every story becomes a held story.
    _check(bnd.is_boundary_story(
        "Conference bans the bat model, with the rule taking effect from August 1",
        "The recall notice covers model years 2023 through 2025."), fails,
        "boundary: a firmware advisory naming a version is not classified boundary-class; "
        "the fields that stop an inverted range would never be required")
    # Both negatives fire exactly ONE half of the classifier. That is deliberate: an earlier
    # pair fired neither, so relaxing the rule from AND to OR left them passing and the
    # sabotage run went clean. A negative fixture that no plausible break can flip is not a
    # test, and this is the second time on this desk a canary has passed over nothing.
    _check(not bnd.is_boundary_story(
        "Home side wins 4 to 2 before a crowd of more than 60,000",
        "The result moves them above their rivals in the table."), fails,
        "boundary: an ordinary market story is classified boundary-class on its numbers "
        "alone; the gate will hold stories that have no boundary to confirm")
    _check(not bnd.is_boundary_story(
        "Equipment maker issues a product recall and names no models yet",
        "The company said a full notice would follow and gave no further detail."), fails,
        "boundary: a security story with no version, date or threshold anywhere in it is "
        "classified boundary-class, so it can never satisfy fields that do not exist for it")

    # (2) VERBATIM, NOT PARAPHRASE. This is the whole point: "4.0.1 and earlier" tidied into
    # "up to 4.0.1" means the same thing to a reader and means the check has stopped running.
    advisory = [{"url": "https://blog.coinkite.com/advisory-2026-07",
                 "source_text": "Affected: Mk4 firmware 4.0.0 and earlier. Fixed in firmware "
                                "4.0.1. Users should update to 4.0.1 immediately."}]
    good = {"affected": "Mk4 firmware 4.0.0 and earlier", "fixed": "firmware 4.0.1",
            "user_action": "update to 4.0.1 immediately",
            "advisory_url": "https://blog.coinkite.com/advisory-2026-07"}
    ok, why = bnd.check_against_sources(good, advisory)
    _check(ok, fails, f"boundary: a block quoted verbatim from the advisory failed the "
                      f"check ({why}); the gate would hold every advisory story")

    tidied = dict(good, affected="versions up to 4.0.0")
    ok2, _ = bnd.check_against_sources(tidied, advisory)
    _check(not ok2, fails,
           "boundary: a paraphrased affected-versions string passed as verbatim; paraphrase "
           "is the exact step that inverted the Coldcard draft")

    inverted = dict(good, affected="Mk4 firmware 4.0.1 and later")
    ok3, _ = bnd.check_against_sources(inverted, advisory)
    _check(not ok3, fails,
           "boundary: an INVERTED range passed the advisory check; this is the published "
           "claim the whole change exists to prevent")

    # (3) SECOND-HAND IS NOT PRIMARY. A field quoted out of a news write-up of the advisory
    # is where the direction flips, so only text fetched from the advisory URL counts.
    ok4, why4 = bnd.check_against_sources(
        good, [{"url": "https://example.test/news-story",
                "source_text": "Affected: Mk4 firmware 4.0.0 and earlier. Fixed in firmware "
                               "4.0.1."}])
    _check(not ok4 and any("primary" in r for r in why4), fails,
           "boundary: the check accepted a news write-up as the advisory; second-hand "
           "sourcing is where a version range gets restated and inverted")

    for f in ("affected", "fixed", "user_action", "advisory_url"):
        ok5, _ = bnd.check_against_sources({k: v for k, v in good.items() if k != f}, advisory)
        _check(not ok5, fails, f"boundary: a block missing {f!r} passed as complete")

    # (4) THE WRITER GETS NO SAY. writer.py COPIES the block; if it ever starts trusting the
    # model's rendering of it, a paraphrase is back in the pipeline.
    art = {"title": "T", "body": "b", "boundary": {"affected": "WHATEVER THE MODEL SAID",
                                                   "fixed": "x", "user_action": "y",
                                                   "advisory_url": "z"}}
    writer._carry_boundary(art, {"brief": {"boundary": good, "boundary_required": True,
                                           "boundary_ok": True}})
    _check(art.get("boundary") == good, fails,
           "boundary: writer._carry_boundary did not overwrite the model's block with the "
           "brief's; the writer is restating the version range again")
    _check("_carry_boundary" in inspect.getsource(writer.validate), fails,
           "boundary: writer.validate no longer calls _carry_boundary, so nothing copies the "
           "fields and the draft carries whatever the model wrote")

    # (5) THE GATE IS FAIL-CLOSED AND READS THE DRAFT. An unconfirmed boundary holds, with no
    # retry path: retrying cannot make a vendor advisory fetchable.
    # Built fresh, NOT from art: _carry_boundary stamped boundary_ok=True onto art above, so
    # reusing it made the never-checked case inherit that True and pass for the wrong reason.
    # The absent-key case is the one that matters most here, so it has to be genuinely absent.
    base = {"title": "T", "body": "b", "boundary": dict(good)}
    _check(pubmod.boundary_block({"article_draft": dict(base, boundary_required=True,
                                                        boundary_ok=True)}) == "", fails,
           "boundary: publish is holding a story whose boundary IS confirmed")
    for bad in ({"boundary_required": True, "boundary_ok": False},
                {"boundary_required": True, "boundary_ok": None},
                {"boundary_required": True}):
        _check(pubmod.boundary_block({"article_draft": dict(base, **bad)}) != "", fails,
               f"boundary: publish let a boundary-class story through with {bad}; an "
               f"unconfirmed who-is-affected claim reached a reader")
    _check(pubmod.boundary_block({"article_draft": {"boundary_required": True,
                                                    "boundary_ok": True}}) != "", fails,
           "boundary: publish let through a story marked confirmed that carries no block to "
           "render; the panel would be absent and the prose says nothing about it, by design")
    _check(pubmod.boundary_block({"article_draft": {"title": "ordinary story"}}) == "", fails,
           "boundary: publish is holding an ordinary story that has no boundary at all")
    _check("boundary_block(" in inspect.getsource(pubmod.run), fails,
           "boundary: publish.run no longer calls boundary_block; the gate is unreachable "
           "and this canary is testing dead code")

    # (6) THE RESEARCHER STAMPS BOTH DIRECTIONS. A missing key and a negative answer look
    # identical downstream, and only one of them means the check ran.
    brief = {"id": "c011", "core_claim": "Coinkite patched a firmware flaw in 4.0.1."}
    researcher._stamp_boundary(brief, {"headline": "Coldcard firmware vulnerability lets an "
                                                   "attacker extract the seed",
                                       "source_texts": advisory})
    _check(brief.get("boundary_required") is True and brief.get("boundary_ok") is False, fails,
           f"boundary: a boundary-class brief with no block was stamped "
           f"required={brief.get('boundary_required')!r} ok={brief.get('boundary_ok')!r}; "
           f"the publish gate reads these and would let it through")
    plain = {"id": "c020", "core_claim": "Bitcoin traded near flat."}
    researcher._stamp_boundary(plain, {"headline": "Bitcoin holds steady", "source_texts": []})
    _check(plain.get("boundary_required") is False, fails,
           "boundary: an ordinary story was stamped boundary_required; every story would "
           "need a vendor advisory to publish")
    _check("_stamp_boundary" in inspect.getsource(researcher.validate), fails,
           "boundary: researcher.validate no longer calls _stamp_boundary, so no brief is "
           "ever classified and the gate never fires")

    # (7) RENDERING. Nothing is composed into a sentence, and an incomplete block renders
    # nothing at all rather than a panel with a blank row where the fix version goes.
    _check([lab for lab, _ in bnd.rows(good)] == ["Affected", "Fixed in", "What to do",
                                                  "Advisory"], fails,
           "boundary: the rendered panel changed shape; a reader scanning for the fix version "
           "should find it in the same place on every advisory story")
    _check(bnd.rows({"affected": "x"}) == [], fails,
           "boundary: an incomplete block still renders; a panel missing the fixed version "
           "answers the question wrong by omission")
    return fails


def _dedupe_guard_canary():
    """The three-in-one-day failure, pinned as fixtures.

    On 2026-07-30 the desk published one Treasury designation three times. same_event() was
    never the problem: it matched all three pairs. These cases lock the four things that were
    wrong downstream, and the one case that must still get through, because a guard that
    holds everything is just a slower way to publish nothing."""
    fails = []
    import datetime as _dt
    import autopilot as ap
    import dedupe

    # THE FIXTURES BELOW CARRY ABSOLUTE DATES, so the clock they are judged against is pinned
    # beside them. Without this the canary is a time bomb: classify_published builds a 21-day
    # window from the wall clock, the Ostium origin is dated 2026-07-16, and on 2026-08-06 it
    # walked out of that window. The follow-up stopped matching, classified 'new' instead of
    # 'update', this canary's own assertion fired, and because layer 1 is a HARD GATE all
    # three desks stopped publishing for two days. Nothing was wrong with the guard.
    NOW = _dt.datetime(2026, 7, 31, 12, 0, tzinfo=_dt.timezone.utc)

    # CHASSIS SYNC. dedupe.py is one file copied into three repositories, so the only thing
    # keeping them honest is this hash plus the shared fixtures below. Editing the guard in
    # one desk and not the others reds every desk that was not updated.
    _sha = __import__("hashlib").sha256(
        open(dedupe.__file__, "rb").read()).hexdigest()[:16]
    _check(_sha == "49730f35f8d91525", fails,
           f"dedupe: this desk's dedupe.py is {_sha}, the chassis copy is 49730f35f8d91525. "
           f"The guard was changed in one repo and not the others; re-sync all three.")

    # (4) Title Case is not evidence. A headline yields capitalised tokens for ordinary
    # words, so novelty must be read from sentence-cased prose.
    title_sig = dedupe._signature(
        "US Sanctions Iranian Marine Insurers Accepting Bitcoin for Strait of Hormuz Passage")
    _check({"accepting", "insurers", "passage"} <= title_sig, fails,
           "dedupe: this fixture assumed Title Case pollutes _signature and it no longer "
           "does; re-check whether _claim_signature still needs to avoid headlines")
    # The fixture MUST carry a title, or pulling the headline back into the claim signature
    # changes nothing and this assertion tests nothing.
    claim = dedupe._claim_signature(
        {"title": "US Sanctions Iranian Marine Insurers Accepting Bitcoin for Strait of "
                  "Hormuz Passage",
         "key_fact": "HormuzSafe, an Iranian state-linked firm, accepts Bitcoin to collect "
                     "mandatory insurance fees from vessels transiting the Strait of Hormuz."})
    _check(not ({"accepting", "insurers", "passage"} & claim), fails,
           "dedupe: _claim_signature is reading the headline again; a reworded headline will "
           "look like new reporting and the same event will publish twice")

    # (1)(2) A retelling that adds nothing is a rehash, even when the wording differs enough
    # to beat a word-overlap threshold, and even when an older unrelated story also matched.
    pub = {"title": "US Treasury Sanctions Iranian Firms Using Bitcoin for Maritime Extortion",
           "key_fact": "US Treasury sanctioned two Iranian firms accepting Bitcoin to fund "
                       "IRGC operations via a coercive maritime insurance extortion scheme.",
           # Verbatim from the story that actually published at 18:40, not a paraphrase.
           # A shortened body made this fixture pass for the wrong reason on first run:
           # the retelling looked novel only because the excerpt omitted the Strait.
           "body": ["HormuzSafe Marine Services Authority and Persian Gulf Marine Insurance "
                    "Company were designated under Executive Order 13902.",
                    "HormuzSafe advertises itself as offering digital insurance, traffic "
                    "control, security and emergency response to vessels transiting the "
                    "Strait of Hormuz."]}
    retell = {"key_fact": "HormuzSafe, an Iranian state-linked firm, accepts Bitcoin and "
                          "digital assets to collect mandatory insurance fees from vessels "
                          "transiting the Strait of Hormuz, generating revenue for the IRGC."}
    covered = dedupe._covered_signature(pub)
    _check(len(dedupe._claim_signature(retell) - covered - dedupe._OUTLETS)
           < dedupe.NOVELTY_MIN, fails,
           "dedupe: a retelling that adds no new fact scores as novel; this is the shape "
           "that published one Treasury designation three times")

    # the case that MUST still pass: a real development adds a new actor and a new amount
    # Verbatim from the two stories the desk actually published on 2026-07-16. A paraphrase
    # here failed to trip same_event at all, so the follow-up came back "new" and the
    # assertion tested nothing.
    followup = {"key_fact": "The Ostium OLP vault lost approximately $24M USDC via oracle "
                            "manipulation; the exploiter converted stolen stablecoins to "
                            "12,086 ETH total and routed 10,540 ETH through Tornado Cash."}
    origin = {"title": "Ostium Suffers $18 Million Exploit as Oracle Attack Wave Continues "
                       "to Hit DeFi",
              "key_fact": "An attacker drained $18 million in USDC from Ostium's vault by "
                          "submitting oracle reports with future-dated timestamps, exposing "
                          "a critical gap in price-feed validation.",
              "body": ["The attack targeted Ostium's price-feed validation."]}
    _check(len(dedupe._claim_signature(followup) - dedupe._covered_signature(origin)
               - dedupe._OUTLETS) >= dedupe.NOVELTY_MIN, fails,
           "dedupe: a genuine follow-up with a new actor and a new amount is being held as a "
           "rehash; the guard has become a publish-nothing gate")

    # (2) NOVELTY AGAINST ALL PRIOR COVERAGE, exercised end to end against a controlled
    # corpus rather than inspected in source. An earlier version of this check only grepped
    # classify_published for "min(matches" and a revert to the oldest-match rule passed it
    # clean, which is the same weakness that let a canary sit over dead code for two days.
    stale = {"id": "c001", "slug": "iran-strikes",
             "title": "Crypto Little Changed as U.S. Launches Fresh Iran Strikes",
             "date": "2026-07-12",
             "key_fact": "Markets held steady after a reported Strait of Hormuz closure.",
             "body": ["Traders shrugged off the escalation."]}
    first = dict(pub, id="c112", slug="iran-sanctions-first", date="2026-07-30",
                 published_utc="2026-07-30T15:25:01Z")
    corpus = [stale, first]
    verdict, _t, _s = dedupe.classify_published(
        "US Sanctions Iranian Marine Insurers Accepting Bitcoin for Strait of Hormuz Passage",
        retell["key_fact"], corpus=corpus, now=NOW)
    _check(verdict == "rehash", fails,
           f"dedupe: a same-day retelling classified as {verdict!r} with an unrelated older "
           f"story in the corpus; that older story is exactly what made all three Iran "
           f"duplicates look novel on 2026-07-30")

    # and the same corpus must still let a real development through
    verdict2, _t2, _s2 = dedupe.classify_published(
        "Ostium Vault Exploiter Routes 10,540 ETH to Tornado Cash",
        followup["key_fact"], corpus=[dict(origin, id="c900", slug="ostium-origin",
                                           date="2026-07-16",
                                           published_utc="2026-07-16T07:33:18Z")],
        now=NOW)
    _check(verdict2 == "update", fails,
           f"dedupe: a genuine follow-up classified as {verdict2!r}; the guard has become a "
           f"publish-nothing gate")

    # (3) the guard must judge the shipped title
    _check('_shipped_title' in inspect.getsource(ap.main), fails,
           "dedupe: main() is judging the editor's headline again rather than the writer's "
           "title; the string checked must be the string shipped")
    return fails

def _edition_repair_canary():
    """The edition floor (family audit 2026-09-02): sentence-grain cuts of what the
    trace checker flagged, belt repairs at the same grain, and the digest built only
    from published stories. Each must refuse when it would damage the product."""
    import edition_repair as er
    import wrap as wrapmod
    fails = []
    body = ("The first paragraph carries a real fact from the inputs. It also carries "
            "an invented figure of 412 goals that no input supports. A third sentence "
            "closes the paragraph honestly.\n\n"
            + "The second paragraph is long enough to keep the body over the floor once a "
              "sentence is cut, so the repair is legal rather than refused. " * 6)
    obj = {"hook_title": "A day of results and one invented number", "dek": "A dek.",
           "key_takeaway": "k", "body": body,
           "bottom_line": "The theme was results. The checkpoints are Friday's slate."}
    new, cuts = er.excise_claims(
        obj, ["It also carries an invented figure of 412 goals that no input supports."])
    _check(new is not None and cuts == 1 and "412 goals" not in new["body"], fails,
           "edition repair: a flagged sentence was not cut cleanly")
    _check(er.excise_claims(obj, ["a claim that appears nowhere in this edition"])[0] is None,
           fails, "edition repair: an unlocatable claim must refuse the cut")
    _check(er.excise_claims(obj, ["The theme was results.",
                                  "The checkpoints are Friday's slate."])[0] is None,
           fails, "edition repair: hollowing out The Bottom Line must refuse")
    short = dict(obj, body="One short paragraph with the invented figure of 412 goals. Two.")
    _check(er.excise_claims(short, ["invented figure of 412 goals"])[0] is None, fails,
           "edition repair: a cut that leaves the body under the floor must refuse")

    def belts(o):
        return wrapmod.belts(str(o.get("body", "")), str(o.get("dek", "")),
                                     str(o.get("bottom_line", "")))
    dirty = dict(obj, bottom_line=obj["bottom_line"] + " The favorite is poised to rally.")
    _check(belts(dirty), fails, "edition repair: the lane belt did not fire on the fixture")
    fixed, _ = er.belt_repair(dirty, belts, er.sentence_probe(belts))
    _check(fixed is not None and not belts(fixed) and "poised" not in fixed["bottom_line"],
           fails, "edition repair: a lane violation was not cut at sentence grain")

    stories = [{"title": f"Story {i} headline", "summary": "A verified summary sentence. "
                "Another sentence with a number, 12.", "key_fact": f"Key fact {i}.",
                "first_paragraphs": ["First paragraph of the story, verified and published."],
                "bottom_line": "The next checkpoint is the filing deadline on September 9.",
                "date": "2026-09-0" + str(1 + i % 2), "url": f"/articles/s{i}.html"}
               for i in range(6)]
    dg = er.digest_edition(stories, belts, wrapmod.bottom_line_lint)
    _check(dg is not None and dg.get("digest") is True and not belts(dg)
           and er.word_count(dg["body"]) >= er.MIN_BODY_WORDS, fails,
           "edition repair: the digest floor did not build a belts-clean edition")
    _check(er.digest_edition([], belts, wrapmod.bottom_line_lint) is None, fails,
           "edition repair: a digest with no stories must be None")
    return fails


def _merge_state_canary():
    """Lock the resolution rules for the file(s) two overlapping publishes always collide on.

    The brief's retry rebases when main moves mid-run, and the watcher's drifted retries
    land in pairs, so this happens. site/content/ is per-slug and never conflicts;
    editorial-log.json and site/data/scores.json are rewritten by every run and always does. These assertions pin what each merge
    must preserve, because getting editorial-log wrong silently deletes another run's
    editorial record and nothing else would notice."""
    fails = []
    import merge_state as ms

    up = [{"date": "2026-07-29", "approved": 3, "rejected": [{"id": "other"}]}]
    mine = [{"date": "2026-07-29", "approved": 5, "rejected": [{"id": "mine"}]}]
    got = ms.merge_editorial_log(up, mine)
    ids = [r["id"] for e in got for r in e.get("rejected", [])]
    _check("other" in ids and "mine" in ids, fails,
           "merge_state: editorial-log merge dropped a run's record")
    _check(ms.merge_editorial_log(up, up) == up, fails,
           "merge_state: editorial-log merge duplicated an identical record")
    _check(ms.merge_editorial_log(None, mine) == mine
           and ms.merge_editorial_log(up, None) == up, fails,
           "merge_state: editorial-log merge mishandled a missing side")

    # snapshot, not a record: newer generated_utc wins, tie goes to upstream
    a = {"generated_utc": "2026-07-30T08:00:00Z", "leagues": {"n": 1}}
    b = {"generated_utc": "2026-07-30T09:00:00Z", "leagues": {"n": 2}}
    _check(ms.merge_scores(a, b) is b, fails, "merge_state: scores ignored the newer snapshot")
    _check(ms.merge_scores(b, a) is b, fails,
           "merge_state: an older replayed snapshot overwrote a newer upstream one")
    _check(ms.merge_scores(a, a) is a, fails, "merge_state: scores tie did not go to upstream")

    _check(set(ms.KNOWN) == {"editorial-log.json", "site/data/scores.json"}, fails,
           "merge_state: the auto-resolve allowlist changed; anything added here can "
           "silently overwrite real work during a rebase")
    return fails

def _replay_e2e():
    """Run the whole pipeline in replay mode over the fixture and assert the invariants."""
    fails = []
    os.environ["DESK_LLM_MODE"] = "replay"
    cfg = common.load_config()
    client = llmlib.Client(cfg, mode="replay")
    import aggregate, editor, verifier, researcher, writer, approver, digest
    try:
        rc = aggregate.run(fixture=FIXTURE, out_path=os.path.join(common.OUT_DIR, "items.json"))
        _check(rc == 0, fails, f"replay: aggregate exit {rc}")
        items = common.read_out("items.json")
        _check(items["_meta"]["clusters"] == 5, fails,
               f"replay: expected 5 fixture clusters, got {items['_meta']['clusters']}")

        ed = editor.run(client=client)
        _check(len(ed["ranked"]) == 3 and len(ed["rejected"]) == 2, fails,
               f"replay: editor split expected 3/2, got {len(ed['ranked'])}/{len(ed['rejected'])}")

        ve = verifier.run(client=client)
        verds = {v["verdict"] for v in ve["verdicts"]}
        _check(verds == {"VERIFIED", "NEEDS-HUMAN-REVIEW", "REJECT"}, fails,
               f"replay: expected all three verdicts, got {sorted(verds)}")

        # Researcher: every draftable story gets a brief with a measured source_chars, and
        # REJECT stories are never briefed (no tokens spent on the dead).
        re_ = researcher.run(client=client)
        briefed = {b["id"] for b in re_["briefs"]}
        draftable = {v["id"] for v in ve["verdicts"] if v["verdict"] != "REJECT"}
        _check(briefed == draftable, fails,
               f"replay: researcher briefed {sorted(briefed)}, expected {sorted(draftable)}")
        _check(all("source_chars" in b for b in re_["briefs"]), fails,
               "replay: a brief is missing its measured source_chars")

        wr = writer.run(client=client)
        drafted = {d["id"] for d in wr["drafts"]}
        rejected_ids = {v["id"] for v in ve["verdicts"] if v["verdict"] == "REJECT"}
        _check(drafted and drafted.isdisjoint(rejected_ids), fails,
               f"replay: writer drafted a REJECT story or drafted nothing (drafted={drafted})")
        for d in wr["drafts"]:
            art = d["article_draft"]
            _check(art["status"] == "DRAFT", fails, f"replay: draft {d['id']} not DRAFT-tagged")
            _check(art["human_take"] == "", fails, f"replay: draft {d['id']} human_take not empty")
            _check("betting" in art["not_financial_advice"].lower()
                   and "advice" in art["not_financial_advice"].lower(), fails,
                   f"replay: draft {d['id']} missing not-betting-advice disclaimer")

        # Approver: one categorized decision per draft; an unjudged draft would REJECT
        # (fail-closed coverage is exercised by the validate path itself).
        ap = approver.run(client=client)
        judged = {a["id"] for a in ap["approvals"]}
        _check(judged == drafted, fails,
               f"replay: approver judged {sorted(judged)}, expected {sorted(drafted)}")
        _check(all(a.get("category") in approver.CATEGORIES
                   for a in ap["approvals"] if a["decision"] == "REJECT"), fails,
               "replay: an approver REJECT is missing its category")

        # Depth gate (deterministic): short body + rich sources holds; short body + thin
        # sources passes (honest brevity); long body always passes.
        import autopilot
        _check(autopilot.depth_gate_holds(40, 5000) is True, fails,
               "depth gate: 40 words from 5000 chars of source material was NOT held")
        _check(autopilot.depth_gate_holds(40, 0) is False, fails,
               "depth gate: honest-thin story (40 words, no sources) was wrongly held")
        _check(autopilot.depth_gate_holds(450, 5000) is False, fails,
               "depth gate: full-length story was wrongly held")

        # BREAKING two-source gate (deterministic, fail-closed): a single-source breaking
        # story HOLDS unless its headline carries the unconfirmed label; two independent
        # sources publish; duplicate source names do not count as independence.
        _check(autopilot.breaking_two_source_holds(
                   "Star quarterback traded to Acme Falcons", ["ESPN"]) is True, fails,
               "breaking gate: single-source story published as fact was NOT held")
        _check(autopilot.breaking_two_source_holds(
                   "Star quarterback traded to Acme Falcons", ["ESPN", "The Athletic"]) is False, fails,
               "breaking gate: two-source story was wrongly held")
        _check(autopilot.breaking_two_source_holds(
                   "Unconfirmed: star quarterback may be traded to Acme Falcons", ["ESPN"]) is False,
               fails, "breaking gate: labeled-unconfirmed single-source was wrongly held")
        _check(autopilot.breaking_two_source_holds(
                   "Star quarterback traded to Acme Falcons", ["ESPN", "espn", ""]) is True, fails,
               "breaking gate: duplicate source names wrongly counted as independent")
        # INDEPENDENCE IS BY PUBLISHER (2026-07-31): this desk carries eight ESPN feeds, so
        # two ESPN URLs are ONE source, not two. Measured that 64% of apparently
        # corroborated clusters were a single publisher wearing two feed names; that must
        # never satisfy the two-source gate.
        _check(autopilot.breaking_two_source_holds(
                   "League suspends executive after investigation",
                   ["https://www.espn.com/nfl/story/a", "https://www.espn.com/mlb/story/b"]) is True,
               fails, "breaking gate: two feeds from ONE publisher counted as independent")
        _check(autopilot.breaking_two_source_holds(
                   "League suspends executive after investigation",
                   ["https://www.espn.com/nfl/story/a", "https://www.bbc.co.uk/sport/b"]) is False,
               fails, "breaking gate: two genuinely independent publishers wrongly held")

        # Daily edition (wrap): replay dry-run must produce a belts-clean edition item
        # that leads the page (negative rank) and carries the desk's stories as sources.
        # A desk with ZERO published stories honestly declines the edition (no preview
        # exists to assert against); the full check runs whenever content exists.
        import subprocess
        import wrap as wrapmod
        env = dict(os.environ, DESK_LLM_MODE="replay")
        r = subprocess.run([sys.executable, os.path.join(HERE, "wrap.py"),
                            "--dry-run", "--edition", "morning"],
                           capture_output=True, text=True, env=env)
        _check(r.returncode == 0, fails, f"wrap dry-run failed: {(r.stdout + r.stderr)[-200:]}")
        if r.returncode == 0 and wrapmod.gather_stories():
            wp = common.read_out("wrap-preview.json")
            _check(wp.get("rank", 0) < 0, fails, "wrap: edition rank must be negative (leads the page)")
            _check(wp.get("human_take") == "", fails, "wrap: human_take must be empty")
            _check("—" not in json.dumps(wp), fails, "wrap: em dash leaked into the edition")
            _check(wp.get("sources"), fails, "wrap: edition must cite the desk's own stories")
        elif r.returncode == 0:
            print("canary: wrap dry-run had no published stories to synthesize "
                  "(fresh desk); preview assertions run once content exists")

        digest.run(date="canary")
        qmd = os.path.join(common.OUT_DIR, "review_queue", "canary.md")
        _check(os.path.exists(qmd), fails, "replay: digest did not write the review queue")
        tmpl = common.read_out("approval_template.json")
        _check(all(s["decision"] == "hold" for s in tmpl["stories"].values()), fails,
               "replay: approval template must default every story to 'hold'")
        _check(all(v["id"] not in tmpl["stories"] for v in ve["verdicts"] if v["verdict"] == "REJECT"),
               fails, "replay: a REJECT story leaked into the approval template")
    except Exception as e:
        fails.append(f"replay: end-to-end raised {type(e).__name__}: {e}")
    return fails


def _contract_ladder_canary(cfg):
    """The recovery layer (2026-07-15): a contract violation retries on the same model,
    then escalates ONE call to the rescue model, and replay mode never escalates."""
    fails = []

    class StubClient(llmlib.Client):
        def __init__(self, cfg, answers):
            super().__init__(cfg, mode="live")
            self.answers = list(answers)
            self.models_used = []

        def _live_raw(self, stage, model_cfg, system, user):
            self.models_used.append(model_cfg["model"])
            return self.answers.pop(0)

    def need_ranked(o):
        if "ranked" not in o:
            raise llmlib.LLMError("editor output missing 'ranked'")
        return o

    # (a) bad shape then good on rung 2: recovered, no escalation
    c = StubClient(cfg, ['{"id": "c000"}', '{"ranked": [], "rejected": []}'])
    try:
        obj = c.call_json("editor", "sys", "user", validate=need_ranked)
        _check("ranked" in obj and len(c.models_used) == 2, fails,
               f"ladder: retry did not recover (calls={c.models_used})")
        _check(c.models_used[0] == c.models_used[1], fails,
               "ladder: rung 2 must reuse the configured model")
    except llmlib.LLMError as e:
        fails.append(f"ladder: recoverable violation wrongly failed: {e}")

    # (b) two bad answers: rung 3 runs on the rescue model
    c2 = StubClient(cfg, ['nonsense', '{"wrong": 1}', '{"ranked": [], "rejected": []}'])
    try:
        c2.call_json("editor", "sys", "user", validate=need_ranked)
        _check(len(c2.models_used) == 3 and c2.models_used[2] == llmlib.RESCUE_MODEL, fails,
               f"ladder: third rung was not the rescue model (calls={c2.models_used})")
    except llmlib.LLMError as e:
        fails.append(f"ladder: rescue rung wrongly failed: {e}")

    # (c) three bad answers: fails closed
    c3 = StubClient(cfg, ['x', 'y', 'z'])
    try:
        c3.call_json("editor", "sys", "user", validate=need_ranked)
        fails.append("ladder: triple violation did NOT fail closed")
    except llmlib.LLMError:
        pass

    # (d) replay never retries/escalates: a fixture that fails validation fails the canary
    rc = llmlib.Client(cfg, mode="replay")
    try:
        rc.call_json("editor", "sys", "user",
                     validate=lambda o: (_ for _ in ()).throw(llmlib.LLMError("fixture bad")))
        fails.append("ladder: replay validation failure did NOT raise")
    except llmlib.LLMError:
        _check(rc.budget.calls == 1, fails,
               f"ladder: replay made {rc.budget.calls} calls (must be exactly 1, no ladder)")

    # (e) watcher slot recovery: past deadline + missing edition -> that slot; edition
    # present -> quiet; before deadline -> quiet
    import datetime as _dt
    import tempfile
    import watcher
    # PROGRAM 4, T-1 (2026-09-16): this tested the MORNING slot, which no longer runs.
    # The three properties it was checking are properties of slot recovery itself, not
    # of the morning slot, so they are checked against the slot that survives: past the
    # deadline with no edition it fires, with the edition present it stays quiet, and
    # before the deadline it stays quiet.
    #
    # A fourth check is added, and it is the one that would have caught tonight: NO
    # SLOT THE DESK NO LONGER RUNS MAY BE RECOVERABLE. A slot left in SLOT_DEADLINES
    # with no cron is re-fired on every tick forever, and each fire spends a full model
    # run. The table and the workflow's cron list must change together.
    # These three run in their OWN directory. Writing the evening edition into the one
    # the window audit below uses would satisfy that audit's "missed evening" case for
    # it, and the test would pass for the wrong reason.
    with tempfile.TemporaryDirectory() as td_r:
        late = _dt.datetime(2026, 7, 16, 2, 0, tzinfo=_dt.timezone.utc)
        _check(watcher.missed_slot(late, td_r) == "evening-brief", fails,
               "watcher recovery: past the deadline with no edition, did not fire")
        open(os.path.join(td_r, "2026-07-15-evening-brief.json"), "w").write("{}")
        _check(watcher.missed_slot(late, td_r) is None, fails,
               "watcher recovery: fired despite the edition existing")
        early = _dt.datetime(2026, 7, 15, 20, 0, tzinfo=_dt.timezone.utc)
        _check(watcher.missed_slot(early, td_r) is None, fails,
               "watcher recovery: fired before the deadline")
    _check({s[0] for s in watcher.SLOT_DEADLINES} == {"evening-brief"}, fails,
           "watcher recovery: a slot with no cron is in SLOT_DEADLINES and would be "
           "re-fired on every tick for the rest of time")

    # (i) H-11: VENUE CORRECTIONS EXPIRE BY THEMSELVES. Each entry records the name
    # the feed carried when it was entered. If the feed now says something else, the
    # source has either fixed its record or drifted, and either way the entry must not
    # sit there quietly: the canary fails naming it so it can be deleted.
    _here = os.path.dirname(os.path.abspath(__file__))
    _vc = os.path.join(_here, "site", "data", "venue_corrections.json")
    _sb = os.path.join(_here, "site", "data", "scoreboard.json")
    if os.path.exists(_vc):
        _fix = (json.load(open(_vc, encoding="utf-8")) or {}).get("corrections") or {}
        _feed = {}
        if os.path.exists(_sb):
            for _L in (json.load(open(_sb, encoding="utf-8")) or {}).get("leagues", []):
                for _g in _L.get("games") or []:
                    _ab = (_g.get("home") or {}).get("abbr")
                    if _g.get("venue") and _ab:
                        # LEAGUE:TEAM. HOU is the Texans at NRG and the Astros at
                        # Daikin Park; the first cut keyed on the abbreviation alone
                        # and this check failed on the collision, which is the whole
                        # reason the key carries the league.
                        _feed[f'{_L.get("league") or ""}:{_ab}'] = _g["venue"]
        # A team not playing at home this week is simply absent from the feed; that is
        # not evidence the correction is stale, so only a name we can actually see is
        # compared.
        for _vid, _e in _fix.items():
            _check(bool(_e.get("feed_name") and _e.get("name") and _e.get("source")
                        and _e.get("entered") and _e.get("owner")), fails,
                   f"venue correction {_vid}: needs feed_name, name, source, entered "
                   f"and owner")
            _check(_e.get("feed_name") != _e.get("name"), fails,
                   f"venue correction {_vid}: corrects a name to itself")
            _seen = _feed.get(_vid)
            if _seen:
                _check(_seen == _e.get("feed_name"), fails,
                       f"venue correction {_vid}: the feed now says {_seen!r}, not "
                       f"{_e.get('feed_name')!r}; the source changed its record, so "
                       f"delete this entry")

    # (j) C-4: THE DESK REGISTER AND THE WORKFLOW FILES MUST AGREE, EXACTLY. desk.json
    # is how a person knows the newsroom is configured the way they think it is, and a
    # register nobody checks is a comment. Every active cron in a file must be in the
    # register, and every cron in the register must be in a file: no more and no less,
    # so a stale cron or a placeholder that never fires cannot survive a push.
    #
    # Comment out a cron and forget the register and this fails. Add one to the register
    # and forget the file and this fails. That is the point.
    _dj = os.path.join(_here, "desk.json")
    _wfdir = os.path.join(_here, ".github", "workflows")
    if os.path.exists(_dj):
        _reg = json.load(open(_dj, encoding="utf-8"))
        _regwf = _reg.get("workflows") or {}
        _seen = set()
        for _fn in sorted(os.listdir(_wfdir)):
            if not _fn.endswith((".yml", ".yaml")):
                continue
            _seen.add(_fn)
            _txt = open(os.path.join(_wfdir, _fn), encoding="utf-8").read()
            # active cron lines only: a commented one is not a schedule
            # Strip the comment FIRST, then the quotes: a cron line reads
            #   - cron: "38 23 * * *"   # Evening Wrap slot
            # and stripping quotes before the comment leaves the closing one attached.
            _live = set(re.findall(r'^\s*-\s*cron:\s*["\']([^"\']+)["\']',
                                   _txt, re.M))
            _check(_fn in _regwf, fails,
                   f"desk register: {_fn} is not in desk.json")
            _want = {c.get("utc") for c in (_regwf.get(_fn) or {}).get("crons") or []}
            _check(_live == _want, fails,
                   f"desk register: {_fn} crons {sorted(_live)} do not match the "
                   f"register's {sorted(_want)}")
        for _fn in _regwf:
            _check(_fn in _seen, fails,
                   f"desk register: desk.json lists {_fn}, which has no workflow file")
        # the served slots are the recovery table, in one place (C-3)
        _check(set(_reg.get("served_slots") or []) ==
               {s[0] for s in watcher.SLOT_DEADLINES}, fails,
               f"desk register: served_slots {_reg.get('served_slots')} do not match "
               f"watcher.SLOT_DEADLINES")

    # (h) PROGRAM 4, X-2: THE SLOT GUARD, ON ITS NO-MODEL PATH. The guard lives in the
    # workflow YAML, so it is extracted and executed here with origin/main mocked. It
    # is the rule that makes "one Edition a day" true regardless of who dispatches, and
    # it was gated on EVENT == "schedule" until tonight, which let every dispatch spend.
    import re as _re
    import tempfile as _tf
    _wf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       ".github", "workflows", "sports-news-brief.yml")

    def _guard_code():
        s = open(_wf, encoding="utf-8").read()
        m = _re.search(r"python3 - <<'PYEOF'\n(.*?)\n          PYEOF", s, _re.S)
        if not m:
            return None
        return "\n".join(l[10:] if l.startswith(" " * 10) else l
                          for l in m.group(1).split("\n"))

    def _guard(code, event, slot, cron, breaking, served):
        out = _tf.NamedTemporaryFile("w+", delete=False, suffix=".txt"); out.close()
        env = {"EVENT": event, "SLOT_NAME": slot, "SLOT_CRON": cron,
               "BREAKING": "1" if breaking else "0", "GITHUB_OUTPUT": out.name}
        old = dict(os.environ); os.environ.update(env)

        class _R:
            returncode = 0 if served else 1
            stdout = stderr = b""
        import io as _io
        import subprocess as _sp
        real, so = _sp.run, sys.stdout
        _sp.run = lambda *a, **k: _R()
        sys.stdout = _io.StringIO()
        try:
            exec(compile(code, "<guard>", "exec"), {"__name__": "__main__"})
        finally:
            sys.stdout = so; _sp.run = real
            os.environ.clear(); os.environ.update(old)
        res = dict(l.split("=", 1) for l in open(out.name).read().strip().split("\n")
                   if "=" in l)
        os.unlink(out.name)
        return res.get("serve")

    _code = _guard_code()
    _check(_code is not None, fails, "slot guard: could not read the guard from the workflow")
    if _code:
        # C-1: THE EDITION PATH, AS ONE TEST. The desk promises one Edition a day and
        # this is the rule that keeps that promise: at the slot, with no Edition file
        # for that slot and day on origin/main, the run WRITES one, whatever else
        # happened that day; with the file present it stands down at zero.
        #
        # On 2026-09-16 the crypto slot run never reached this guard. It died at the
        # offline canary gate on an assertion about a slot that had been removed an
        # hour earlier, and the desk got its Edition by luck, from a breaking run at
        # 8:43 PM. The rule was never the problem; nothing was checking that the rule
        # could be reached.
        _check(_guard(_code, "schedule", "", "38 23 * * *", False, False) == "true", fails,
               "C-1: at the slot with no Edition for the day, the run must write one")
        _check(_guard(_code, "schedule", "", "38 23 * * *", False, True) == "false", fails,
               "C-1: with the Edition already on origin/main, the run must stand down")
        _cases = [
            ("a cron for a slot already served must stand down",
             "schedule", "", "38 23 * * *", False, True, "false"),
            ("a cron for an unserved slot must run",
             "schedule", "", "38 23 * * *", False, False, "true"),
            ("a DISPATCH for a slot already served must stand down",
             "workflow_dispatch", "evening-brief", "", False, True, "false"),
            ("a dispatch naming no slot must stand down even with nothing served",
             "workflow_dispatch", "", "", False, False, "false"),
            ("a breaking run must still pass the guard",
             "workflow_dispatch", "evening-brief", "", True, True, "true"),
            # X-2b: the old Worker names slots on its old schedule until the deploy
            # lands. A dispatch naming a slot the desk no longer serves must stand
            # down even with nothing served, or it spends a run writing an Edition
            # for a retired slot.
            ("a dispatch naming a slot the desk no longer serves must stand down",
             "workflow_dispatch", "morning-brief", "", False, False, "false"),
            ("the same for afternoon-brief",
             "workflow_dispatch", "afternoon-brief", "", False, False, "false"),
        ]
        for _label, _ev, _slot, _cron, _brk, _served, _want in _cases:
            _check(_guard(_code, _ev, _slot, _cron, _brk, _served) == _want, fails,
                   "slot guard: " + _label)

    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, "2026-07-15-morning-brief.json"), "w").write("{}")
        # (f) closed-window audit: a served window stays quiet after it closes; a missed
        # evening is only checkable the next morning and must be reported then
        afternoon = _dt.datetime(2026, 7, 15, 15, 0, tzinfo=_dt.timezone.utc)
        _check("2026-07-15-morning-brief" not in watcher.missed_windows(afternoon, td),
               fails, "missed-edition audit: flagged a window whose edition exists")
        next_morning = _dt.datetime(2026, 7, 16, 9, 0, tzinfo=_dt.timezone.utc)
        _check("2026-07-15-evening-brief" in watcher.missed_windows(next_morning, td),
               fails, "missed-edition audit: yesterday's missed evening not detected")
        evening = _dt.datetime(2026, 7, 15, 23, 50, tzinfo=_dt.timezone.utc)
        _check(watcher.missed_slot(evening, td) == "evening-brief", fails,
               "watcher recovery: missed evening slot not detected")
        # (g) the evening window crosses midnight (2026-09-03): a 00:17 tick recovers
        # yesterday's missing evening, dated to yesterday, and the closed-window audit
        # does not call it permanently missed until the window ends at 05:00
        after_midnight = _dt.datetime(2026, 7, 16, 0, 17, tzinfo=_dt.timezone.utc)
        _check(watcher.missed_slot(after_midnight, td) == "evening-brief", fails,
               "watcher recovery: yesterday's missed evening not recovered after midnight")
        _check("2026-07-15-evening-brief" not in watcher.missed_windows(after_midnight, td),
               fails, "missed-edition audit: flagged an evening still inside its recovery window")
        open(os.path.join(td, "2026-07-15-evening-brief.json"), "w").write("{}")
        _check(watcher.missed_slot(after_midnight, td) is None, fails,
               "watcher recovery: fired after midnight despite yesterday's evening existing")

    # THE BOTTOM LINE lane gate (owner directive 2026-07-15): the signature element's
    # own guardrail must block directional/predictive language and pass clean synthesis.
    import wrap as wrapmod
    clean = ("The day's theme was the trade deadline outpacing the contenders: two front "
             "offices dealt and the standings barely budged. The honest read is that the "
             "sellers stayed patient while the headlines ran hot. The coming checkpoints "
             "are Thursday's arbitration hearing and the league's next injury report.")
    _check(wrapmod.bottom_line_lint(clean) == [], fails,
           f"Bottom Line lane: clean synthesis wrongly flagged: {wrapmod.bottom_line_lint(clean)}")
    dirty = "Tonight's sweep sets up for a move higher in the seeding race."
    _check(len(wrapmod.bottom_line_lint(dirty)) >= 1, fails,
           "Bottom Line lane: 'sets up for a move higher' was NOT blocked")
    _check(len(wrapmod.bottom_line_lint("The Rockets look poised to rally, brace for a wild deadline week.")) >= 2,
           fails, "Bottom Line lane: poised-to/brace-for was NOT blocked")
    return fails


def _failclosed_canaries(cfg):
    fails = []
    # (a) missing key fails the LLM call closed
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        live = llmlib.Client(cfg, mode="live")
        try:
            live.call_json("editor", "sys", "user")
            fails.append("fail-closed: live call with no API key did NOT raise")
        except llmlib.LLMError:
            pass
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved

    # (b) budget cap trips
    tiny = llmlib.Budget(max_tokens=10, max_usd=100)
    try:
        tiny.record("claude-opus-4-8", {"input_tokens": 1000, "output_tokens": 1000})
        fails.append("fail-closed: budget cap did NOT trip on overspend")
    except llmlib.BudgetError:
        pass

    # (c) publish refuses a replay-mode approval and an unapproved/hold story
    import publish
    tmp = os.path.join(common.OUT_DIR, "approval_replay.json")
    common.write_out(os.path.basename(tmp), {"mode": "replay", "stories": {
        "c000": {"decision": "approve", "human_take": "x"}}})
    res = publish.run(approval_path=tmp)
    _check(res["published"] == [], fails, "fail-closed: publish accepted a replay-mode approval")

    common.write_out(os.path.basename(tmp), {"mode": "live", "stories": {
        "c000": {"decision": "hold", "human_take": ""}}})
    res2 = publish.run(approval_path=tmp)
    _check(res2["published"] == [], fails, "fail-closed: publish accepted a 'hold' story")
    return fails


# ---- Layer 2 -----------------------------------------------------------------

def _entry_count(body):
    """Count RSS <item> / Atom <entry> elements in a lowercased feed body. Regex, not
    ElementTree: this check must never throw on a malformed document, and a feed that
    uses a namespace prefix it never declares hard-fails a real parse (see
    aggregate._declare_missing_namespaces) while still carrying readable items."""
    return len(re.findall(r"<(?:[a-z0-9_.-]+:)?(?:item|entry)[\s/>]", body))


def layer2_sources():
    cfg = common.load_config()
    fails = []
    for f in cfg["sources"]["rss"]:
        name, url = f["name"], f["url"]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": common.ua_for(url)})
            with urllib.request.urlopen(req, timeout=30) as r:
                code = r.getcode()
                # Read the WHOLE body, not the first 2000 bytes: the shape check below
                # still only needs the head, but the item count added after it needs the
                # channel. These are ~25 small feeds, so the full read costs nothing.
                body = r.read().decode("utf-8", "replace").lower()
                head = body[:2000]
        except Exception as e:
            gh("warning", f"sources: '{name}' fetch failed ({url}): {e} -- soft warning only, NOT failing")
            continue
        if code != 200:
            # A feed with a configured API fallback is healthy when the FALLBACK serves
            # (the ESPN RSS hosts answer runner IPs with HTTP 202 bot challenges by
            # design; the pipeline never reads those URLs from CI, the aggregate's API
            # fallback does). Only a feed with no working fallback is a real liveness
            # failure. The probe gets two attempts: the 2026-08 Monday reds were
            # transient probe misses dressed up as seven dead feeds.
            fb = f.get("fallback_api")
            fb_note = "no fallback configured"
            if fb:
                fb_note = "fallback probe failed twice"
                for attempt in (1, 2):
                    try:
                        freq = urllib.request.Request(fb, headers={"User-Agent": common.ua_for(fb)})
                        with urllib.request.urlopen(freq, timeout=30) as fr:
                            if fr.getcode() == 200:
                                fb_note = "fallback OK"
                                break
                    except Exception:
                        pass
                    if attempt == 1:
                        time.sleep(3)
                if fb_note == "fallback OK":
                    print(f"LAYER 2 sources: OK '{name}' -> RSS {code} but API "
                          f"fallback resolves 200 (the path the pipeline uses).")
                    continue
            why = ("HTTP 202 bot challenge (runner-IP block)" if code == 202
                   else f"HTTP {code}")
            gh("error", f"sources: '{name}' -> {why}; {fb_note}: {url}")
            fails.append({"feed": name, "url": url, "status": why, "fallback": fb_note})
            continue
        if not ("<rss" in head or "<feed" in head or "<rdf" in head or "<?xml" in head):
            gh("error", f"sources: '{name}' did not look like an RSS/Atom feed: {url}")
            fails.append({"feed": name, "url": url,
                          "status": "HTTP 200 but not feed-shaped", "fallback": "n/a"})
        else:
            # A feed-shaped body is not a working feed: a channel can be perfectly valid
            # and carry ZERO items, and the shape check above calls that healthy forever.
            # On 2026-09-03 all four Google News lanes served 0 items in production (12
            # each an hour earlier) and this layer reported nothing wrong. Same two
            # attempts as the fallback probe above, and for the same reason: an empty read
            # is usually a transient miss, and one empty read is not a dead feed.
            n_items = _entry_count(body)
            if n_items == 0:
                # Second attempt (the read above was the first), same 3 second pause.
                time.sleep(3)
                try:
                    rreq = urllib.request.Request(url, headers={"User-Agent": common.ua_for(url)})
                    with urllib.request.urlopen(rreq, timeout=30) as rr:
                        if rr.getcode() == 200:
                            n_items = _entry_count(
                                rr.read().decode("utf-8", "replace").lower())
                except Exception:
                    pass
            if n_items == 0:
                gh("error", f"sources: '{name}' served a feed with zero items on two reads: {url}")
                fails.append({"feed": name, "url": url,
                              "status": "HTTP 200 but zero items", "fallback": "n/a"})
            else:
                print(f"LAYER 2 sources: OK '{name}' -> HTTP 200, feed-shaped.")
    if fails:
        # Machine-readable failure list: the verify workflow's flag issue names the
        # feeds from this file instead of sending the owner into the run logs.
        os.makedirs("out", exist_ok=True)
        with open(os.path.join("out", "layer2_failures.json"), "w", encoding="utf-8") as fh:
            json.dump(fails, fh, indent=1)
        print(f"\nLAYER 2 SOURCES: {len(fails)} feed(s) failing -> notify (exit 3). Does NOT block a run.")
        return 3
    print("LAYER 2 SOURCES: PASS -> all configured feeds resolve 200 and look like feeds.")
    return 0

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "canary":
        sys.exit(layer1_canary())
    if cmd == "sources":
        sys.exit(layer2_sources())
    c = layer1_canary()
    s = layer2_sources()
    print(f"\n[gate] Layer1 canary = {'PASS' if c == 0 else 'FAIL'} | "
          f"Layer2 sources = {'PASS' if s == 0 else 'MISMATCH (notify, non-blocking)'}")
    sys.exit(c)  # ONLY Layer 1 blocks


if __name__ == "__main__":
    main()
