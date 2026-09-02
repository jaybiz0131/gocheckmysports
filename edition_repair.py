#!/usr/bin/env python3
"""
edition_repair.py: deterministic repairs and the fallback digest for the daily edition.

THE CHASSIS COPY. Identical in gocheckmycrypto, gocheckmynews and gocheckmysports.

WHY THIS EXISTS (family audit 2026-09-02). In the week of Aug 25 to Sep 2 the three
desks filed 40+ "Edition stage failed" issues between them, nearly one per slot on the
crypto desk. The story pipeline was fine every time; the slot died at wrap.py, and the
run log shows the same two shapes over and over:

  1. the trace checker (Haiku) listed an "absent" or "contradicted" item whose OWN
     reasoning said the edition was right ("No contradiction found; this is supported
     paraphrase", "all cited facts align with source material", "This section reads as
     analysis and is permitted"), the hand-kept phrase lists in wrap.check() did not
     contain that particular wording, the adjudicator was asked a fact question about a
     synthesis sentence, and the edition died twice, Haiku and then Sonnet;
  2. a deterministic belt (a directional price claim at the wrong window, an advice
     phrase, a lane violation in The Bottom Line) failed every ladder rung because the
     model kept restating the same sentence, and the slot died on one clause.

The desk already has the right doctrine for stories: THE STORY IS NOT THE SENTENCE
(owner directive 2026-08-21; approver._repair_rejects cuts the named sentence and
publishes the rest). This module applies that doctrine to the edition, and adds the
one thing a guaranteed product needs: a floor. Nothing here calls a model, so nothing
here can invent a fact.

  excise_claims(obj, claims)        cut the sentences a checker flagged, publish the rest
  belt_repair(obj, belts, probe)    cut the sentences that trip a deterministic belt
  digest_edition(...)               a plain digest built ONLY from the desk's own
                                    published, verified stories, when synthesis fails:
                                    the slot is served, the reader gets the day's
                                    verified news, and the recovery net stops re-firing
                                    the whole pipeline every 30 minutes for a slot the
                                    stories already filled

Every repair is refused when it would damage the product: an unlocatable claim, a claim
in the title, a hollowed-out Bottom Line, or a body under the minimum. Those cases fall
through to the next rung exactly as before.
"""
import re

MIN_BODY_WORDS = 120
MAX_BODY_WORDS = 1050

# Sentence boundaries: end punctuation followed by whitespace and an upper-case, digit
# or quote start. Abbreviations are re-joined afterwards (see _ABBREV).
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[“])")
_ABBREV = re.compile(
    r"(?:\b(?:[A-Z]|St|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec|Mr|Mrs|Ms|Dr|Jr|Sr|"
    r"vs|No|Nos|Gov|Sen|Rep|Lt|Gen|Col|Capt|Sgt|Inc|Ltd|Co|Corp|Ave|Blvd|Ft|Mt|"
    r"approx|est|dept|fig|vol|pp?)\.|\b[A-Z]\.[A-Z]\.|\ba\.m\.|\bp\.m\.)$")
_STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "is", "was",
         "were", "be", "by", "with", "as", "that", "this", "its", "it", "from", "has",
         "have", "had", "not", "but", "s", "against", "over", "after", "before",
         "between", "during", "amid", "versus", "vs", "into", "per", "which", "who",
         "than", "then", "also", "are", "their", "his", "her", "they", "he", "she"}


def sentences(text):
    """Split prose into sentences, re-joining splits made after common abbreviations."""
    parts = [p for p in _SPLIT.split(str(text or "").strip()) if p.strip()]
    out = []
    for p in parts:
        if out and _ABBREV.search(out[-1]):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def _norm(s):
    s = re.sub(r"(?<=\d),(?=\d)", "", str(s or ""))
    return " ".join(re.sub(r"[^a-z0-9$%.]+", " ", s.lower()).split())


def _content_words(s):
    return [w for w in _norm(s).split() if w not in _STOP and len(w) > 1]


def _coverage(claim, candidate):
    """Fraction of the claim's content words present in the candidate; 1.0 when the
    normalized claim is a verbatim substring of the candidate."""
    nc, nk = _norm(claim), _norm(candidate)
    if nc and nk and nc in nk:
        return 1.0
    cw = _content_words(claim)
    if len(cw) < 2:
        return 0.0
    kw = set(_norm(candidate).split())
    return sum(1 for w in cw if w in kw) / len(cw)


def _fields(obj):
    """The editable prose fields, as (name, list-of-paragraphs)."""
    out = []
    for k in ("body", "dek", "bottom_line", "key_takeaway"):
        v = obj.get(k)
        if isinstance(v, list):
            paras = [str(x) for x in v if str(x).strip()]
        else:
            paras = [p for p in str(v or "").split("\n") if p.strip()]
        out.append((k, paras))
    return out


def locate(claim, obj, floor=0.6):
    """Every (field, paragraph index, sentence indices) carrying this claim, or [].

    Single sentences are tried first; adjacent pairs only when no single sentence
    reaches the floor, because a checker's quoted claim can span a boundary. A
    near-verbatim hit (>= 0.9) is cut wherever it occurs (an edition that repeats a
    flagged sentence must lose every copy); a fuzzier match cuts only the best one."""
    singles, pairs = [], []
    for field, paras in _fields(obj):
        for pi, para in enumerate(paras):
            sents = sentences(para)
            for si in range(len(sents)):
                score = _coverage(claim, sents[si])
                if score >= floor:
                    singles.append((score, field, pi, (si,)))
            for si in range(len(sents) - 1):
                score = _coverage(claim, sents[si] + " " + sents[si + 1])
                if score >= floor:
                    pairs.append((score, field, pi, (si, si + 1)))
    pool = singles or pairs
    if not pool:
        return []
    strong = [c for c in pool if c[0] >= 0.9]
    chosen = strong or [max(pool, key=lambda c: c[0])]
    return [(field, pi, idx) for _s, field, pi, idx in chosen]


def _rebuild(obj, edits):
    """Apply {(field, para_idx): set(sentence indices to drop)} and return a new obj."""
    new = dict(obj)
    for field, paras in _fields(obj):
        changed = False
        rebuilt = []
        for pi, para in enumerate(paras):
            drop = edits.get((field, pi))
            if not drop:
                rebuilt.append(para)
                continue
            changed = True
            kept = [s for si, s in enumerate(sentences(para)) if si not in drop]
            if kept:
                rebuilt.append(" ".join(kept))
        if changed:
            new[field] = "\n\n".join(rebuilt) if field == "body" else " ".join(rebuilt)
    return new


def word_count(text):
    return len(str(text or "").split())


def excise_claims(obj, claims, min_words=MIN_BODY_WORDS):
    """Cut every sentence carrying a flagged claim. Returns (new_obj, cuts) or (None, why).

    Refuses when a claim cannot be located (the offending text might survive), when the
    claim lives in the title (nothing to cut around), when the cut would hollow out The
    Bottom Line, or when the body would drop under the minimum."""
    edits = {}
    for c in claims:
        c = str(c or "").strip()
        if not c:
            continue
        locs = locate(c, obj)
        if not locs:
            if _coverage(c, obj.get("hook_title", "")) >= 0.8:
                return None, f"claim is the title itself: {c[:60]!r}"
            return None, f"could not locate the flagged claim: {c[:60]!r}"
        for field, pi, idx in locs:
            edits.setdefault((field, pi), set()).update(idx)
    if not edits:
        return None, "nothing to cut"
    new = _rebuild(obj, edits)
    if not str(new.get("bottom_line", "")).strip():
        return None, "the cut would empty The Bottom Line"
    if word_count(new.get("body")) < min_words:
        return None, (f"too little of the edition survives the cut "
                      f"({word_count(new.get('body'))} words)")
    if not str(new.get("dek", "")).strip():
        # the dek is a summary line; the first surviving body sentence is an honest one
        first = sentences(str(new.get("body", "")).split("\n")[0])
        new["dek"] = first[0] if first else str(obj.get("hook_title", ""))
    cuts = sum(len(v) for v in edits.values())
    return new, cuts


def sentence_probe(belts):
    """A per-sentence probe built from a whole-edition belt set: judges one sentence as
    if it were the whole of its field, with the other fields empty and the length band
    ignored (no single sentence can satisfy it). Belts that read the fields jointly
    still see exactly one sentence, so a hit means THIS sentence trips the belt."""
    def _probe(field, sentence):
        trial = {"hook_title": "", "key_takeaway": "",
                 "body": sentence if field == "body" else "",
                 "dek": sentence if field == "dek" else "",
                 "bottom_line": sentence if field == "bottom_line" else ""}
        return [p for p in belts(trial) if "words outside" not in p]
    return _probe


def belt_repair(obj, belts, probe, min_words=MIN_BODY_WORDS):
    """Cut the sentences that trip a deterministic belt, then re-run the full belts.

    `belts(obj) -> [problems]` is the desk's whole-edition belt set; `probe(field,
    sentence) -> [problems]` judges one sentence of one field in isolation (the caller
    decides which belts make sense at sentence grain: direction/window claims, advice
    phrases, lane violations; never the length band). Returns (new_obj, cuts) or
    (None, why)."""
    edits = {}
    for field, paras in _fields(obj):
        if field == "key_takeaway":
            continue
        for pi, para in enumerate(paras):
            for si, s in enumerate(sentences(para)):
                try:
                    hits = probe(field, s)
                except Exception:
                    hits = []
                if hits:
                    edits.setdefault((field, pi), set()).add(si)
    if not edits:
        return None, "no single sentence trips a belt on its own"
    new = _rebuild(obj, edits)
    if not str(new.get("bottom_line", "")).strip():
        return None, "the cut would empty The Bottom Line"
    if word_count(new.get("body")) < min_words:
        return None, "too little of the edition survives the cut"
    if not str(new.get("dek", "")).strip():
        first = sentences(str(new.get("body", "")).split("\n")[0])
        new["dek"] = first[0] if first else str(obj.get("hook_title", ""))
    remaining = belts(new)
    if remaining:
        return None, "belts still fail after the cut: " + "; ".join(remaining)[:200]
    return new, sum(len(v) for v in edits.values())


def digest_edition(stories, belts, lint_bottom_line, max_words=900,
                   window_hours=36, label="digest"):
    """A plain digest of the desk's own published, verified stories: the floor under the
    guaranteed edition. Deterministic; no model; nothing that is not already live on the
    site can appear here. Returns the edition object (hook_title, dek, key_takeaway,
    body, bottom_line, digest=True) or None when even the digest cannot pass the belts
    (which means the published stories themselves carry a belt violation, and the
    caller falls back to honest silence)."""
    if not stories:
        return None
    ordered = sorted(stories, key=lambda s: str(s.get("date") or ""), reverse=True)
    paras, words = [], 0
    for s in ordered:
        title = str(s.get("title") or "").strip().rstrip(".")
        summary = str(s.get("summary") or s.get("key_fact") or "").strip()
        first = s.get("first_paragraphs") or []
        first = str(first[0]).strip() if first else ""
        para = title + "." if title else ""
        if summary:
            para += " " + summary
        elif first:
            para += " " + first
        n = word_count(para)
        if words + n > max_words and paras:
            break
        paras.append(para.strip())
        words += n
    body = "\n\n".join(p for p in paras if p)
    lead = ordered[0]
    n = len(paras)
    hook = (f"{n} verified stor{'y' if n == 1 else 'ies'} from the desk, in brief")
    dek = (f"A {label} edition: the desk's verified and published stories from the last "
           f"{window_hours} hours, each in a sentence or two, newest first.")
    key = str(lead.get("key_fact") or lead.get("title") or "").strip()
    bottom = ""
    for s in ordered:
        cand = str(s.get("bottom_line") or "").strip()
        if cand and not lint_bottom_line(cand):
            bottom = cand
            break
    if not bottom:
        bottom = (f"The desk published {n} verified stor{'y' if n == 1 else 'ies'} in "
                  f"the last {window_hours} hours; the lead was {lead.get('title', '')}. "
                  f"Each story above carries its own sources and its own Bottom Line.")
    if word_count(body) < MIN_BODY_WORDS:
        # a quiet window: extend honestly with the stories' own first paragraphs
        # (still verified, published text) until the body clears the floor
        for s in ordered:
            if word_count(body) >= MIN_BODY_WORDS:
                break
            first = (s.get("first_paragraphs") or [""])[0]
            if str(first).strip():
                body += "\n\n" + str(first).strip()
    if word_count(body) < MIN_BODY_WORDS:
        return None
    obj = {"hook_title": hook, "dek": dek, "key_takeaway": key, "body": body,
           "bottom_line": bottom, "digest": True}
    probs = belts(obj)
    if probs:
        # a published story's own sentence trips an edition belt: cut it, keep the rest
        repaired, _ = belt_repair(obj, belts, sentence_probe(belts))
        if repaired is None:
            return None
        obj = repaired
    return obj
