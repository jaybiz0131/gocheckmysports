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
    Fetches each configured RSS feed and asserts HTTP 200 + looks-like-a-feed. A broken feed
    -> ::error:: + exit 3 (CI marks it failed / opens an issue) but never blocks. A network
    error -> ::warning:: only.

USAGE
  python3 verify_pipeline.py canary     # Layer 1 only (exit 0 pass / 1 fail)
  python3 verify_pipeline.py sources    # Layer 2 only (exit 0 pass / 3 mismatch)
  python3 verify_pipeline.py            # both; only Layer 1 affects the exit code
"""

import inspect
import glob
import json
import os
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


def layer1_canary():
    fails = []
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
    _check(_sha == "0c87d51bc15b7246", fails,
           f"dedupe: this desk's dedupe.py is {_sha}, the chassis copy is 0c87d51bc15b7246. "
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
    with tempfile.TemporaryDirectory() as td:
        noon = _dt.datetime(2026, 7, 15, 13, 0, tzinfo=_dt.timezone.utc)
        _check(watcher.missed_slot(noon, td) == "morning-brief", fails,
               "watcher recovery: missed morning slot not detected")
        open(os.path.join(td, "2026-07-15-morning-brief.json"), "w").write("{}")
        _check(watcher.missed_slot(noon, td) is None, fails,
               "watcher recovery: fired despite the edition existing")
        early = _dt.datetime(2026, 7, 15, 10, 30, tzinfo=_dt.timezone.utc)
        _check(watcher.missed_slot(early, td) is None, fails,
               "watcher recovery: fired before the deadline")
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

def layer2_sources():
    cfg = common.load_config()
    fails = []
    for f in cfg["sources"]["rss"]:
        name, url = f["name"], f["url"]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": common.UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                code = r.getcode()
                head = r.read(2000).decode("utf-8", "replace").lower()
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
                        freq = urllib.request.Request(fb, headers={"User-Agent": common.UA})
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
