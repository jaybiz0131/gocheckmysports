#!/usr/bin/env python3
"""
wrap.py: the DAILY EDITION (The Morning Brief / The Closing Wrap), 2026-07-14.

Jack's product call: the desk is a full media outlet, and a media outlet never posts a
zero-content morning. This stage produces the flagship twice-daily synthesis: what is
really going on, why, and what to watch in the coming days: the voice of reason for a
sport-news cycle in constant shout. It runs AFTER autopilot in the brief workflow and can
ALWAYS publish, because its raw material is already gated: the desk's own published,
verified stories plus the desk's own boards when available. No new facts enter here.

Gates (fail-closed for the edition, fail-open for the brief: a wrap failure never blocks
story publishing):
  - the writer model is contract-bound to the provided inputs (prompts/wrap.md);
  - a separate checker call (stage "wrapcheck") verifies every specific fact traces to
    the inputs and nothing reads as advice or prediction; one retry with the reasons;
  - deterministic belts: destyle, no em dashes, advice-word lint, length bounds, NFA.

Editions: UTC hour < 14 -> morning (The Morning Brief), else closing (The Closing Wrap).
One edition file per slot per day (rerun-safe). The edition leads the site for its slot
via negative rank (load_content sorts rank ascending within the date; the day's #1 story
is rank 1, morning wrap -1, closing wrap -2 so the newest edition leads).

USAGE
  python3 wrap.py                          # live: write site/content/<date>-<edition>.json
  python3 wrap.py --dry-run                # write out/wrap-preview.json only
  python3 wrap.py --edition morning|closing  # override the clock (tests, replay)
"""

import datetime
import glob
import json
import os
import re
import sys

import common
import llm as llmlib

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "site", "content")
NFA = "GoCheckMySports reports events. It never advises bets. Nothing here is betting or gambling advice."

EDITIONS = {
    "morning": {"name": "The Morning Brief", "slug": "morning-brief", "rank": -1,
                "id_prefix": "wrap-am"},
    "midday": {"name": "The Afternoon Brief", "slug": "afternoon-brief", "rank": -2,
               "id_prefix": "wrap-md"},
    "evening": {"name": "The Evening Brief", "slug": "evening-brief", "rank": -3,
                "id_prefix": "wrap-pm"},
    # legacy alias (pre-3-slot cadence); resolves to the evening edition
    "closing": {"name": "The Evening Brief", "slug": "evening-brief", "rank": -3,
                "id_prefix": "wrap-pm"},
}

# THE BOTTOM LINE LANE (owner directive 2026-07-15): the desk's signature element runs
# three times daily forever and is the most interpretation-heavy output the desk
# generates, so it gets its own deterministic guardrail on top of the prompt lane.
# Reporting-synthesis only: no future price direction, no setup/positioning language,
# no advice, no speculative causation.
BOTTOM_LINE_LINT = [
    r"\bsets?\s+(it\s+|us\s+)?up\s+for\b", r"\bpoised\s+(to|for)\b", r"\bbrace\s+for\b",
    r"\bpositioned\s+(to|for)\b", r"\bon\s+track\s+(to|for)\b",
    r"\b(likely|expected|expect(s|ed)?)\s+to\s+(rise|fall|rally|drop|climb|slide|rebound|recover)\b",
    r"\bcould\s+(surge|plunge|rally|crash|moon|tank|soar|collapse)\b",
    r"\bnext\s+leg\b", r"\bbreak(out|down)\s+(toward|to|above|below)\b",
    r"\bmove\s+(higher|lower)\b", r"\b(up|down)side\s+(ahead|coming|from\s+here)\b",
    r"\bprice\s+target\b", r"\bpath\s+to\s+\$", r"\bheading\s+(higher|lower|toward)\b",
]


def bottom_line_lint(text):
    """Return the list of directional/predictive lane violations (empty = clean)."""
    low = (text or "").lower()
    return [pat for pat in BOTTOM_LINE_LINT if re.search(pat, low)]

# SPORTS-REGISTER ALLOWLIST (owner ruling 2026-08-03): this belt was copied from the
# finance desk, where bare buy/sell/guaranteed are advice words. On this beat they are
# ordinary reporting vocabulary: guaranteed contracts and guaranteed money are contract
# facts, and teams buy and sell at the trade deadline. Three consecutive editions died
# on exactly those words (2026-08-02 afternoon through 2026-08-03 morning, all three
# quoted in the run logs) while the \|\| echo fail-open kept the jobs green. The intent
# stands, no betting or financial advice to the reader, so the bans stay but carry
# deterministic exceptions for player-market and contract contexts.
ADVICE_LINT = [r"\byou should\b", r"\bgood entry\b",
               r"\bwill (rally|crash|pump|dump|10x|moon)\b",
               r"(?<!fully )\bguaranteed\b(?!\s+(?:contract|contracts|money|salary|salaries|deal|deals|year|years|base|rate|roster spot))",
               r"\b(?:buy|sell)\b(?![-\s]+(?:low|high|out|off|side|window|mode))(?![^.]{0,45}\b(?:deadline|trade|trades|roster|contract|franchise|team|club|stake|ownership)\b)",
               r"\btime to (buy|sell|enter|exit|bet)\b"]


def gather_stories(hours=36):
    """The desk's own published stories from the window: already verified + approved, so
    they are legal fact inputs. Editions themselves are excluded (no wrap-of-wraps)."""
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(hours=hours))
    out = []
    for p in sorted(glob.glob(os.path.join(CONTENT, "*.json"))):
        if os.path.basename(p).startswith("example"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("id", "").startswith("wrap-"):
            continue
        ts = d.get("published_utc") or (d.get("date", "") + "T00:00:00Z")
        try:
            when = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if when < cutoff:
            continue
        body = d.get("body", [])
        body = body if isinstance(body, list) else [str(body)]
        out.append({
            "title": d.get("title", ""), "summary": d.get("dek", ""),
            "key_fact": d.get("key_fact", ""),
            "first_paragraphs": body[:2],
            "bottom_line": d.get("bottom_line", ""),
            "date": d.get("date", ""),
            "url": f"/articles/{d.get('slug','')}.html",
        })
    return out


def belts(article_body, dek, bottom_line):
    """Deterministic checks; returns a list of problems (empty = pass)."""
    problems = []
    text = " ".join([article_body, dek, bottom_line])
    if "—" in text or "–" in text:
        problems.append("em/en dash in the edition")
    low = text.lower()
    for pat in ADVICE_LINT:
        if re.search(pat, low):
            problems.append(f"advice-lint hit: {pat}")
    # The Bottom Line's own guardrail: directional/predictive language is a lane
    # violation in the signature element (and in the dek that frames it).
    for pat in bottom_line_lint(bottom_line + " " + dek):
        problems.append(f"Bottom Line lane violation (directional/predictive): {pat}")
    words = len(article_body.split())
    # The band is a runaway guard, not a style enforcer: the prompt's own cap is 850 and
    # the model aims there, so this belt exists to stop a 2,000-word ramble or a 50-word
    # stub. At 950 it killed the 2026-08-12 midday slot over a 952-word body, two words
    # of drift the reader cannot perceive; a near-miss burns a ladder rung (or the whole
    # slot on the last rung) that a real defect might need.
    if not 120 <= words <= 1050:
        problems.append(f"body {words} words outside 120-1050")
    return problems


def check(client, obj, stories, boards, extras=None):
    """Independent trace check: every specific fact must come from the inputs.

    CALIBRATION (2026-07-26): three straight days of good editions died here on false
    positives (identical dates in different formats, permitted arithmetic synthesis,
    relative weekdays resolved against a story's dateline). The checker's job is
    INVENTED OR CONTRADICTED SUBSTANCE, not formatting.

    THE VERDICT IS DERIVED, NOT ASKED FOR (2026-08-12): asking the model for a global
    APPROVE/REJECT alongside its reasons produced REJECTs whose own reasons said the
    edition was right ("The edition correctly uses 7.4-magnitude... supported by
    inputs" -> REJECT), and a word-list guard could not catch that because the essay
    also contained the word "contradicts". The checker now returns only a structured
    problem list; the verdict is computed here as len(problems) == 0. Fail-closed is
    preserved where it matters, per claim: any claim the checker cannot trace must be
    LISTED, and a malformed problem item fails the contract (climbing the ladder)
    rather than being silently dropped, so sloppy output can never soften the gate.

    `extras` carries any additional permitted inputs the edition was WRITTEN from
    (e.g. the jurisdiction tracker): auditing against fewer inputs than the writer had
    rejects legitimate claims as unverifiable, which cost the 2026-08-12 midday slot."""
    user = ("Audit this daily edition against its ONLY permitted inputs. Return every "
            "PROBLEM you find. A problem is exactly one of: a specific fact (number, "
            "name, date, event, outcome) that is ABSENT from the inputs; a specific fact "
            "CONTRADICTED by the inputs ON SUBSTANCE; language that reads as a price "
            "prediction, trade advice, or 'you should' (kind: advice); hype or panic "
            "register (kind: register). These are NOT problems and must never be listed: "
            "(a) the same date or number in a different format ('July 15' vs '15 July "
            "2026'; '60,000' vs 'nearly 60,000'); (b) sums or combinations of input "
            "numbers when the edition labels them as combined or in total; (c) a weekday "
            "reference consistent with an input story's own dateline; (d) paraphrase of "
            "an event the inputs carry; (e) phrasing that could be more precise but is "
            "not wrong. Connecting and synthesizing the inputs is allowed and expected; "
            "when two inputs differ because one is newer, the newer figure governs and "
            "citing it is correct. Respond ONLY with JSON: "
            '{"problems": [{"claim": "<the edition\'s exact words>", '
            '"kind": "absent"|"contradicted"|"advice"|"register", '
            '"evidence": "<for contradicted: the conflicting input text QUOTED '
            'VERBATIM, word for word; for absent: a short note; otherwise the '
            'offending words>"}]}. '
            "An edition with nothing wrong returns {\"problems\": []}. List ONLY "
            "problems; never list things the edition got right. If you are unsure "
            "whether a specific fact traces to the inputs, list it as a problem.\n\n"
            "EDITION:\n" + json.dumps(obj, indent=1)
            + "\n\nINPUT STORIES:\n" + json.dumps(stories, indent=1)
            + "\n\nINPUT BOARDS:\n" + json.dumps(boards, indent=1)
            + (("\n\nADDITIONAL PERMITTED INPUTS:\n" + json.dumps(extras, indent=1))
               if extras else ""))
    KINDS = {"absent", "contradicted", "advice", "register"}

    # EVIDENCE IS VERIFIED, NOT TRUSTED (2026-08-12, same evening as the derived
    # verdict): the structured contract exposed WHAT the checker was rejecting on, and
    # two of the first four items refuted themselves ("the input confirms 'per
    # intermediary' so no contradiction" -> listed as a contradiction; a claim listed
    # as ABSENT whose own evidence quoted the input story carrying it). A model cannot
    # be word-listed out of that, but its receipts can be checked mechanically: a
    # CONTRADICTED item must quote the conflicting input verbatim and the quote must
    # actually occur in the inputs; an ABSENT item is invalid if the claim's own words
    # occur verbatim in the inputs. An item that fails verification is a contract
    # violation and climbs the ladder, so the checker either brings real evidence or
    # drops the item; it can never kill a slot with a receipt that does not check out.
    def _norm(s):
        return " ".join(re.sub(r"[^a-z0-9$%.]+", " ", str(s).lower()).split())

    def _windows(s, n=6):
        w = _norm(s).split()
        if len(w) <= n:
            return [" ".join(w)] if w else []
        return [" ".join(w[i:i + n]) for i in range(len(w) - n + 1)]

    def check_shape(o):
        if not isinstance(o.get("problems"), list):
            raise llmlib.LLMError("wrapcheck output missing 'problems' list")
        inputs_text = _norm(json.dumps([stories, boards, extras or {}]))
        for p in o["problems"]:
            if not (isinstance(p, dict) and str(p.get("claim", "")).strip()
                    and p.get("kind") in KINDS):
                raise llmlib.LLMError(
                    f"wrapcheck: malformed problem item {str(p)[:120]!r}; every item "
                    f"needs a non-empty 'claim' and a 'kind' from "
                    f"absent/contradicted/advice/register")
            if p["kind"] == "contradicted":
                ev = str(p.get("evidence", ""))
                if not any(w in inputs_text for w in _windows(ev)):
                    raise llmlib.LLMError(
                        f"wrapcheck: 'contradicted' item's evidence does not quote the "
                        f"inputs verbatim ({str(p.get('claim'))[:80]!r}); quote the "
                        f"conflicting input text word for word, or drop the item if "
                        f"nothing in the inputs conflicts")
                # a quote that CONTAINS the claim (or vice versa) is agreement wearing
                # a contradiction label ("AS2032" rejected with "identified as AS2032")
                nc, ne = _norm(p["claim"]), _norm(ev)
                if nc and ne and (nc in ne or ne in nc):
                    raise llmlib.LLMError(
                        f"wrapcheck: 'contradicted' item's evidence quote contains the "
                        f"claim itself ({str(p.get('claim'))[:80]!r}); a quote that "
                        f"agrees with the claim is not a contradiction; state input "
                        f"words that say something INCOMPATIBLE, or drop the item")
            if p["kind"] == "absent":
                if any(w in inputs_text for w in _windows(p["claim"])):
                    raise llmlib.LLMError(
                        f"wrapcheck: 'absent' item's claim occurs verbatim in the "
                        f"inputs ({str(p.get('claim'))[:80]!r}); a claim the inputs "
                        f"carry is traced, not absent; drop the item")
        return o
    v = client.call_json("wrapcheck",
                         "You are an adversarial fact-trace checker for a news desk. "
                         "List invented or contradicted substance without mercy; never "
                         "list formatting, labeled arithmetic, or paraphrase. You return "
                         "only the problem list; the verdict is computed from it.",
                         user, validate=check_shape)

    # BINARY ADJUDICATION OF SURVIVORS (2026-08-13, the fourth live run of the night):
    # with the receipts verified, the checker's remaining rejections were quotes that
    # AGREED with the claim ("AS2032" rejected with evidence "identified as AS2032";
    # "above prescribed concentration limits" rejected with "exceeding prescribed
    # safety limits"). Whole-edition auditing is a task the checker demonstrably gets
    # wrong item by item, so each surviving 'contradicted' item is re-asked as the
    # narrowest possible question: input says X, edition says Y, can both be true?
    # Tightly-scoped binary comparison is the regime where these models are reliable;
    # this is the same narrowing that fixed the boundary classifier. An item judged
    # compatible is dropped with a note; a judged conflict stands and still kills the
    # edition (fail-closed on real contradictions is unchanged).
    # The same narrowing for 'absent' items, with retrieval: the sixth live run died on
    # an 'absent' rejection whose own evidence conceded the inputs carry the fact ("The
    # permitted input on Russia cites December 1, 2026 as a stated date") but the claim
    # wrote the date as prose while the input stores it as 2026-12-01, so the verbatim
    # window rule could not see the equivalence, and date-format equivalence is exactly
    # what the calibration says must never cause rejection. Deterministic retrieval
    # picks the input chunks sharing the most words with the claim; the model gets the
    # narrow question "does this excerpt support this statement, any format?".
    def _chunks():
        out = []
        for st in stories:
            out.append(json.dumps(st))
        if boards:
            for k, val in boards.items():
                out.append(json.dumps({k: val}))
        if extras:
            out.append(json.dumps(extras))
        return out

    def _best_excerpts(claim, n=2, size=500):
        cw = set(_norm(claim).split())
        scored = sorted(_chunks(), key=lambda c: -len(cw & set(_norm(c).split())))
        return [c[:size] for c in scored[:n]]

    kept = []
    for p in v["problems"]:
        if p["kind"] == "absent":
            ex = _best_excerpts(p["claim"])
            q = ("A fact-checker says the EDITION STATEMENT below appears nowhere in the "
                 "permitted inputs. Here are the closest input excerpts.\n"
                 + "\n".join(f"INPUT EXCERPT {i+1}: {e}" for i, e in enumerate(ex))
                 + f"\nEDITION STATEMENT: {str(p.get('claim', ''))[:400]}\n"
                 "Do the excerpts carry this statement's substance (the same fact in any "
                 "format; dates and numbers count as the same fact in any format)? "
                 'Respond ONLY with JSON: {"supported": true|false, "why": "<one '
                 'sentence>"}.')
            def _abs_shape(o):
                if not isinstance(o.get("supported"), bool):
                    raise llmlib.LLMError("wrapcheck adjudication missing boolean 'supported'")
                return o
            try:
                a = client.call_json("wrapcheck",
                                     "You judge whether an input excerpt carries a "
                                     "statement's substance. Format differences are "
                                     "irrelevant; substance is what matters.",
                                     q, validate=_abs_shape)
            except llmlib.LLMError:
                kept.append(p)  # adjudication unavailable -> the rejection stands
                continue
            if a["supported"]:
                print(f"::notice::wrapcheck: dropped 'absent' item the inputs carry "
                      f"({str(p.get('claim'))[:80]!r}): {str(a.get('why'))[:120]}")
            else:
                kept.append(p)
            continue
        if p["kind"] != "contradicted":
            kept.append(p)
            continue
        q = ("Two statements about the same event.\n"
             f"INPUT SAYS: {str(p.get('evidence', ''))[:400]}\n"
             f"EDITION SAYS: {str(p.get('claim', ''))[:400]}\n"
             "Could both be true at once (including when one merely rephrases, "
             "abbreviates, or rounds the other)? Respond ONLY with JSON: "
             '{"conflict": true|false, "why": "<one sentence>"}. '
             "conflict=true ONLY if they cannot both be true.")
        def _adj_shape(o):
            if not isinstance(o.get("conflict"), bool):
                raise llmlib.LLMError("wrapcheck adjudication missing boolean 'conflict'")
            return o
        try:
            a = client.call_json("wrapcheck",
                                 "You compare two short statements and say whether they "
                                 "conflict. Paraphrase and rounding are not conflicts.",
                                 q, validate=_adj_shape)
        except llmlib.LLMError:
            kept.append(p)  # adjudication unavailable -> the rejection stands (fail-closed)
            continue
        if a["conflict"]:
            kept.append(p)
        else:
            print(f"::notice::wrapcheck: dropped self-agreeing 'contradicted' item "
                  f"({str(p.get('claim'))[:80]!r}): {str(a.get('why'))[:120]}")
    v["problems"] = kept
    reasons = [f"{p['kind']}: {p['claim']}"
               + (f" [{p['evidence']}]" if str(p.get("evidence", "")).strip() else "")
               for p in v["problems"]]
    return not v["problems"], reasons


def build_item(edition, obj, stories, date, published_utc):
    ed = EDITIONS[edition]
    from site_build import destyle
    paras = [destyle(p.strip()) for p in str(obj.get("body", "")).split("\n") if p.strip()]
    return {
        "id": f"{ed['id_prefix']}-{date}",
        "slug": f"{ed['slug']}-{date}",
        "kind": "brief",
        "title": destyle(f"{ed['name']}: {obj.get('hook_title','').strip()}"),
        "dek": destyle(obj.get("dek", "")),
        "date": date, "published_utc": published_utc,
        "category": "daily edition",
        "rank": ed["rank"],
        "author": "GoCheckMySports",
        "key_fact": destyle(obj.get("key_takeaway", "")),
        "bottom_line": destyle(obj.get("bottom_line", "")),
        "human_take": "",
        "body": paras,
        "sources": [{"title": s["title"], "url": s["url"]} for s in stories],
    }


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    # three slots (Eastern audience clock): 10:40 UTC morning, 17:00 UTC midday,
    # 23:00 UTC evening; the hour windows resolve whichever slot is running
    # MIDNIGHT DRIFT (owner-approved fix, 2026-08-03): the evening cron regularly fires
    # after 00:00 UTC (measured scheduler drift of 1-3 hours), and wall-clock resolution
    # then reads it as the NEXT day's morning slot with an empty story window. Both this
    # desk (2026-08-02 evening, fired 00:07) and its sibling (fired 01:09) lost their
    # evening editions to exactly that. A fire before 05:00 UTC is the previous day's
    # evening slot, dated to the previous day; no scheduled slot legitimately runs in
    # that window.
    # WHICH SLOT IS THIS? Ask the cron that fired, not the clock (2026-08-04: the desk
    # had never once published all three slots in a day, best 2/3, usually 1/3). Cause:
    # wall-clock buckets plus GitHub's measured drift made runs land in the WRONG
    # bucket and steal each other's slots. A morning cron drifting past 14:00 resolved
    # as "midday" and published the midday edition; the real midday run then hit the
    # once-per-slot guard and skipped, so morning AND midday were lost from one drift.
    # github.event.schedule names the cron exactly; the clock is only the fallback for
    # dispatch and watcher-fired runs.
    CRON_SLOT = {"40 9 * * *": "morning", "38 15 * * *": "midday", "38 23 * * *": "evening",
                 "55 10 * * *": "morning", "25 11 * * *": "morning", "10 17 * * *": "midday"}
    cron = (os.environ.get("SLOT_CRON") or "").strip()
    # SLOT_NAME: the slot this run was fired FOR, named by the caller, and it outranks
    # both the cron and the clock. The watcher's slot recovery re-fires the pipeline for
    # a specific missed slot, but the fired run inherits the WATCHER'S cron in SLOT_CRON
    # (not a slot cron), so wrap fell through to the wall clock and regenerated whatever
    # slot the clock said instead (2026-08-12: every recovery of the missed morning brief
    # resolved 'midday' after 14:00, so a morning slot could never be recovered once the
    # clock moved on, and the watcher re-fired it uselessly all afternoon). Accepts the
    # EDITIONS key or the slug, because the watcher names slots by slug.
    slot_name = (os.environ.get("SLOT_NAME") or "").strip().lower()
    # first-wins: "closing" is a legacy alias sharing evening-brief's slug, and the
    # midnight day-anchor below matches on the canonical key
    slug_to_key = {}
    for k, v in EDITIONS.items():
        slug_to_key.setdefault(v["slug"], k)
    if "--edition" in argv:
        edition = argv[argv.index("--edition") + 1]
    elif slot_name in EDITIONS or slot_name in slug_to_key:
        edition = slug_to_key.get(slot_name, slot_name)
        # a recovered evening slot fired past midnight still belongs to its own day
        if edition == "evening" and now.hour < 5:
            now = now - datetime.timedelta(hours=now.hour + 1)
    elif cron in CRON_SLOT:
        edition = CRON_SLOT[cron]
        # an evening cron that drifts past midnight still belongs to its own day
        if edition == "evening" and now.hour < 5:
            now = now - datetime.timedelta(hours=now.hour + 1)
    elif now.hour < 5:
        edition = "evening"
        now = now - datetime.timedelta(hours=now.hour + 1)  # anchor date to the slot's day
    else:
        edition = "morning" if now.hour < 14 else "midday" if now.hour < 20 else "evening"
    if (cron and cron not in CRON_SLOT and "--edition" not in argv
            and slot_name not in EDITIONS and slot_name not in slug_to_key):
        common.gh("notice", f"wrap: unrecognised cron {cron!r}; resolved '{edition}' "
                            f"by clock. Add it to CRON_SLOT if it is a slot cron.")
    if edition not in EDITIONS:
        print(f"wrap: unknown edition '{edition}'"); return 1
    if os.path.exists(os.path.join(HERE, "PAUSE")):
        print("wrap: PAUSE file present -> skipping"); return 0
    date = now.date().isoformat()
    breaking = os.environ.get("BREAKING") == "1"
    # rerun-safe: one edition per slot per day, EXCEPT a breaking run REGENERATES the
    # current slot's edition in place (owner directive 2026-07-15: a Bottom Line that
    # does not know about the blockbuster trade from an hour ago reads as asleep). Same
    # file, same URL, refreshed read.
    final_path = os.path.join(CONTENT, f"{date}-{EDITIONS[edition]['slug']}.json")
    refreshing = os.path.exists(final_path)
    if not dry and refreshing and not breaking:
        print(f"wrap: {EDITIONS[edition]['name']} already published today -> skip"); return 0

    stories = gather_stories()
    if not stories:
        print("wrap: no published stories in the window; a quiet-day edition needs at "
              "least the boards, but with zero stories the desk stays silent (honest).")
        return 0
    # Desk boards were retired with the market modules; the edition synthesizes the desk's
    # own published stories, and the prompt treats absent boards as simply not citable.
    boards = None

    # within-day continuity: later editions UPDATE and EXTEND the day's coverage rather
    # than repeating it; give the model what already ran today so it can move forward
    earlier = []
    for slug in ("morning-brief", "afternoon-brief"):
        p = os.path.join(CONTENT, f"{date}-{slug}.json")
        if os.path.exists(p) and not p == final_path:
            try:
                e = json.load(open(p, encoding="utf-8"))
                earlier.append({"edition": e.get("title", ""), "dek": e.get("dek", ""),
                                "watch": e.get("bottom_line", "")})
            except Exception:
                pass

    cfg = common.load_config()
    client = llmlib.Client(cfg)
    system = common.load_prompt("wrap.md")
    user = (f"edition: {edition}\n\ntodays_stories:\n{json.dumps(stories, indent=1)}\n\n"
            + (f"desk_boards:\n{json.dumps(boards, indent=1)}\n\n" if boards else
               "desk_boards: (unavailable this run)\n\n")
            + (("earlier_editions_today (UPDATE and EXTEND, never repeat; lead with what "
                "changed since):\n" + json.dumps(earlier, indent=1) + "\n") if earlier else ""))

    def wrap_shape(o):
        # Shape AND belts ride the contract ladder (2026-07-15): a belt failure (length,
        # dash, advice, Bottom-Line lane) retries with the error explained and then gets
        # the Sonnet rescue rung, instead of a same-model retry repeating the mistake
        # (Haiku wrote 993 words against the cap twice before this).
        for k in ("hook_title", "dek", "body", "bottom_line"):
            if not str(o.get(k, "")).strip():
                raise llmlib.LLMError(f"wrap output missing '{k}'")
        # Dashes are mechanical house style and destyle() strips them at build time
        # anyway; scrub here so an otherwise-sound edition is not burned on punctuation
        # (the belt stays as the backstop). Substance belts (advice, lane, length)
        # still require a real rewrite.
        from site_build import destyle
        for k in ("hook_title", "dek", "body", "bottom_line", "key_takeaway"):
            if str(o.get(k) or "").strip():
                o[k] = destyle(str(o[k]))
        probs = belts(str(o.get("body", "")), str(o.get("dek", "")),
                      str(o.get("bottom_line", "")))
        if probs:
            raise llmlib.LLMError("edition failed deterministic belts: " + "; ".join(probs))
        return o

    obj = client.call_json("wrap", system, user, validate=wrap_shape)
    # Independent trace check (needs the inputs, so it lives outside the ladder): one
    # corrective retry through the full ladder, then fail closed.
    for attempt in (1, 2):
        ok, reasons = (True, [])
        if client.mode == "live":
            ok, reasons = check(client, obj, stories, boards or {})
        if ok:
            break
        if attempt == 2:
            common.gh("error", f"wrap: edition failed its trace check twice "
                      f"({'; '.join(reasons[:4])}) -> NOT published (stories unaffected)")
            common.write_out("wrap-rejected.json", {"edition": edition, "obj": obj,
                                                    "reasons": reasons})
            return 1
        # the corrective rewrite runs on the rescue model (stage wraprescue, Sonnet):
        # three same-day editions died on legit catches with Haiku retrying Haiku
        obj = client.call_json("wraprescue", system, user
                               + "\n\nYour previous attempt failed the fact-trace check; "
                                 "fix exactly these and return the full JSON again:\n- "
                               + "\n- ".join(reasons), validate=wrap_shape)

    item = build_item(edition, obj, stories, date, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if dry:
        common.write_out("wrap-preview.json", item)
        print(f"wrap: DRY RUN {EDITIONS[edition]['name']} "
              f"({len(' '.join(item['body']).split())} words, {len(stories)} input stories) "
              f"-> out/wrap-preview.json")
        return 0
    json.dump(item, open(final_path, "w", encoding="utf-8"), indent=2)
    print(f"wrap: published {EDITIONS[edition]['name']} "
          f"({len(' '.join(item['body']).split())} words) -> {os.path.relpath(final_path)} "
          f"[budget {client.budget.summary()}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
