#!/usr/bin/env python3
"""
wrap.py: the DAILY EDITION (The Morning Brief / The Closing Wrap), 2026-07-14.

Jack's product call: the desk is a full media outlet, and a media outlet never posts a
zero-content morning. This stage produces the flagship twice-daily synthesis: what is
really going on, why, and what to watch in the coming days: the voice of reason for a
market in constant panic. It runs AFTER autopilot in the brief workflow and can ALWAYS
publish, because its raw material is already gated: the desk's own published, verified
stories plus the desk's own boards. No new facts enter here.

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
NFA = "Crypto Cronkite reports events. It never advises trades. Nothing here is financial advice."

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

ADVICE_LINT = [r"\byou should\b", r"\bbuy\b", r"\bsell\b", r"\bgood entry\b",
               r"\bwill (rally|crash|pump|dump|10x|moon)\b", r"\bguaranteed\b",
               r"\btime to (buy|sell|enter|exit)\b"]


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
    if not 120 <= words <= 950:
        problems.append(f"body {words} words outside 120-950")
    return problems


def check(client, obj, stories, boards):
    """Independent trace check: every specific fact must come from the inputs."""
    user = ("Verify this daily edition against its ONLY permitted inputs. Rules: every "
            "specific number, name, date, and event in the edition must appear in the "
            "inputs; connecting/synthesizing them is allowed and expected; nothing may "
            "read as a price prediction, trade advice, or 'you should'; register must be "
            "calm (no hype, no panic language). Respond ONLY with JSON: "
            '{"decision": "APPROVE"|"REJECT", "reasons": ["<specific claim and why>"]}\n\n'
            "EDITION:\n" + json.dumps(obj, indent=1)
            + "\n\nINPUT STORIES:\n" + json.dumps(stories, indent=1)
            + "\n\nINPUT BOARDS:\n" + json.dumps(boards, indent=1))
    def check_shape(o):
        if o.get("decision") not in ("APPROVE", "REJECT"):
            raise llmlib.LLMError(f"wrapcheck: invalid decision {o.get('decision')!r}")
        return o
    v = client.call_json("wrapcheck",
                         "You are an adversarial fact-trace checker for a news desk. "
                         "Default to REJECT when uncertain.", user, validate=check_shape)
    return v.get("decision") == "APPROVE", v.get("reasons", [])


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
        "author": "Crypto Cronkite",
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
    edition = (argv[argv.index("--edition") + 1] if "--edition" in argv
               else ("morning" if now.hour < 14 else "midday" if now.hour < 20 else "evening"))
    if edition not in EDITIONS:
        print(f"wrap: unknown edition '{edition}'"); return 1
    if os.path.exists(os.path.join(HERE, "PAUSE")):
        print("wrap: PAUSE file present -> skipping"); return 0
    date = now.date().isoformat()
    breaking = os.environ.get("BREAKING") == "1"
    # rerun-safe: one edition per slot per day, EXCEPT a breaking run REGENERATES the
    # current slot's edition in place (owner directive 2026-07-15: a Bottom Line that
    # does not know about the hack from an hour ago reads as asleep). Same file, same
    # URL, refreshed read.
    final_path = os.path.join(CONTENT, f"{date}-{EDITIONS[edition]['slug']}.json")
    refreshing = os.path.exists(final_path)
    if not dry and refreshing and not breaking:
        print(f"wrap: {EDITIONS[edition]['name']} already published today -> skip"); return 0

    stories = gather_stories()
    if not stories:
        print("wrap: no published stories in the window; a quiet-day edition needs at "
              "least the boards, but with zero stories the desk stays silent (honest).")
        return 0
    boards = None
    try:
        import chartmaster
        boards = chartmaster.digest()
    except Exception as e:
        common.gh("warning", f"wrap: desk boards unavailable ({e}); edition from stories only")

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
