#!/usr/bin/env python3
"""
boundary.py: structured fields for the stories where a BOUNDARY decides who is affected.

WHY THIS EXISTS
  The desk drafted a hardware-wallet firmware advisory twice and the approver rejected it
  twice, both times on accuracy, both times correctly. The second draft had the direction
  inverted: it implied users ON the patched version were at risk, when that version WAS the
  fix. The gate did its job. But the gate is the last line, and asking a writer to re-read
  its own prose for directional correctness is asking the wrong question of the wrong stage.

  The defect was upstream. A version range is a boundary: everything on one side is affected
  and everything on the other is not. Turn that into a sentence and the sentence can be
  wrong in a way no amount of careful reading reliably catches, because "4.0.1 and earlier"
  and "4.0.1 and later" are one word apart and both read as fluent English. Keep it as a
  FIELD and there is nothing to invert: the value is lifted from the vendor advisory and
  rendered, not restated.

THE PATTERN, which is broader than firmware (owner's instruction, 2026-07-31)
  Any story where a VERSION, a DATE RANGE, or a THRESHOLD determines who is affected gets
  this treatment. Vulnerabilities are the loudest case, not the only one. Protocol upgrades
  ("nodes below v1.14.2 fork off at block X"), regulatory effective dates ("filers with over
  $50M AUM, from 1 January"), and eligibility cutoffs have exactly the same shape and exactly
  the same failure mode.

THE DISCIPLINE
  1. The RESEARCHER emits the fields, quoted verbatim from the primary source.
  2. The WRITER does not touch them. writer.py COPIES the block from the brief into the
     draft, the same way it forces status=DRAFT and the disclaimer. A model cannot paraphrase
     what the code copies.
  3. The VERIFIER checks the FIELDS against the advisory text, not the prose against a
     recollection: each field value must appear verbatim in the fetched primary source.
  4. If the boundary cannot be confirmed from a primary source, the story does NOT publish.
     Silence beats an inverted claim on a security story.

WHAT THIS MODULE IS
  Deterministic only. No model calls, no network. It classifies, it checks, it explains why
  it refused. Every function is pure so the canary can hold it to fixtures.

CHASSIS. This file is byte-identical across the three desks and pinned by sha256 in each
verify_pipeline canary. Edit it in one place and port, or the canary will say so.
"""

import re

# --- Classification -----------------------------------------------------------------------

# A story is boundary-class when it reports something that DIVIDES an audience: this build is
# affected, that one is not. The trigger words are deliberately about the EVENT, not about the
# subject matter, because "security" alone is a topic and topics do not have boundaries.
#
# ONE LIST FOR THREE DESKS, and a SHORT one. The vocabulary is shared rather than split per
# desk because this file is hash-pinned byte-identical and a per-desk word list would be the
# first thing to drift.
#
# It is short because it was measured, not guessed. A first draft added league vocabulary
# (suspension, eligibility, waiver window) and it was wrong on both counts. It over-fired, and
# more importantly a player suspension is not this pattern at all: it decides what happens to
# one athlete, not which READERS are covered. The test a candidate word has to pass is whether
# a reader could be on either side of it. "Recall covering model years 2019 through 2022" and
# "nodes below v1.14.2 fork off" pass. "Suspended six games" does not.
#
# Two words also had to be narrowed from their obvious form. Bare "patch" matched a jersey
# patch deal, so only the verb forms survive. Bare "recalled" matched a player recalled from
# Triple-A, so a recall has to name itself as a product or safety recall.
#
# Final measurement over the three desks' published corpora, classifying on headline, dek and
# key fact the way the pipeline does: 5 of 157 crypto stories (all genuine, four protocol or
# exploit stories carrying a version or block height, plus the Coldcard advisory), 0 of 121
# news, 0 of 158 sports.
_TRIGGER = re.compile(
    # software and protocol advisories: the reader's own device or node is on one side or the other
    r"\b(vulnerabilit\w*|security\s+advisor(?:y|ies)|cve-\d{4}-\d+|exploitab\w*|"
    r"patch(?:ed|ing)|hotfix|firmware|"
    r"hard\s?fork|soft\s?fork|upgrade\s+deadline|mandatory\s+upgrade|"
    # rules with a stated start: whether the reader is covered depends on a date or a threshold
    r"effective\s+date|effective\s+(?:on|from)|compliance\s+deadline|takes?\s+effect|"
    r"filing\s+deadline|enrollment\s+(?:deadline|period)|"
    # what an agency or a company issues when some readers are covered and others are not
    r"(?:product|safety|voluntary|consumer)\s+recall(?:s|ed|ing)?|recall(?:s|ed|ing)?\s+(?:notice|covering|affecting)|safety\s+notice|do\s+not\s+(?:use|eat|drink)|"
    r"evacuation\s+order|shelter[- ]in[- ]place|boil[- ]water)\b", re.I)

# ...and only when an actual boundary is stated. A vulnerability story with no version, date
# or threshold anywhere in it is a story ABOUT security, not a story that tells a reader
# whether they personally are exposed, and it has nothing for these fields to carry.
#
# EVERY alternative here has to touch a number, a version or a date. A bare comparator does
# not qualify, and that is not a detail: "His death comes days before his 15th anniversary"
# paired with "mental health vulnerabilities" was the one false positive left in 437 published
# stories, and both halves of it are ordinary English used in an ordinary sense. Requiring the
# comparator to point AT something removes that whole class.
_BOUNDARY_SHAPE = re.compile(
    r"(\bv?\d+\.\d+(?:\.\d+)?\w*\b"                       # 4.0.1, v1.14, 2.0, 1.5.0Q
    r"|\b(?:versions?|builds?|releases?|model\s+years?|lot(?:\s+numbers?)?)\s+"
    r"[\w.]*\d"                                           # version 5.6.0, model years 2019
    r"|\bblock\s+(?:height\s+)?\d[\d,]*\b"
    r"|\b(?:before|after|prior\s+to|on\s+or\s+(?:before|after)|through|up\s+to|"
    r"earlier\s+than|later\s+than|from)\s+"
    r"(?:v?\d|versions?\b|builds?\b|releases?\b|firmware\b|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b)"
    r"|\d\s*(?:,\s*)?(?:and\s+)?(?:earlier|later|below|above|onward)\b"
    r"|\b(?:over|under|above|below|at\s+least|more\s+than|less\s+than)\s+"
    r"[\$€£]?\d)", re.I)

# The four fields. Naming them here, once, is the point: every stage reads this list rather
# than repeating a literal, so adding a fifth field cannot be half-applied.
FIELDS = ("affected", "fixed", "user_action", "advisory_url")

FIELD_LABELS = {
    "affected": "Affected",
    "fixed": "Fixed in",
    "user_action": "What to do",
    "advisory_url": "Advisory",
}


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

# Headline and key-fact length. A field longer than this is a paragraph, and paragraphs are
# where the loose match came from.
_SHORT_FIELD = 200


def is_boundary_story(*texts):
    """True when a version, date range or threshold decides who this story applies to.

    Both halves must be CO-LOCATED. Accepting them anywhere in the story was measured over
    the three desks' corpora and classified 38% of crypto, 28% of sports and 17% of news as
    boundary-class, which would have held most of what the desks publish: "Trump imposes 50%
    tariffs" has a threshold in the headline and a "takes effect" four hundred words later,
    and the two have nothing to do with each other.

    A real boundary states itself in one breath, because that is the only way to state it:
    "Mk3 versions 4.0.1 through 4.1.9 are affected", "covering model years 2019 through 2022".
    So the rule is the same sentence, with one deliberate relaxation: short fields may pair
    across the gap between them, because a headline carrying the trigger over a claim carrying
    the range ("Coldcard firmware flaw" / "Mk4 and Mk5 before version 5.6.0 are affected") is
    one thought split over two lines, and the strict rule missed it. A paragraph is not a short
    field, so body copy still has to state the whole boundary in a single sentence.

    The cost of a false positive here is a held story, so the bias is deliberately toward
    missing one rather than holding the desk. A boundary story wrongly classified ordinary
    still publishes, just without the panel; the prose rules in writer.md still forbid the
    writer restating a range it was not given."""
    for chunk in texts:
        for sent in _SENTENCE.split(str(chunk or "")):
            if _TRIGGER.search(sent) and _BOUNDARY_SHAPE.search(sent):
                return True
    # A headline carries the trigger and the claim carries the range often enough that a
    # strict same-sentence rule alone missed real advisories ("Coldcard firmware flaw" /
    # "Mk4 and Mk5 before version 5.6.0 are affected"). Short fields are allowed to pair
    # across the boundary between them, because a headline is one thought and pairing it
    # with the claim beneath it is not the loose whole-document match that over-fired.
    short = [str(t or "") for t in texts if 0 < len(str(t or "")) <= _SHORT_FIELD]
    return bool(short and any(_TRIGGER.search(t) for t in short)
                and any(_BOUNDARY_SHAPE.search(t) for t in short))


def story_is_boundary_class(story, brief=None):
    """Classify from the material a stage actually holds: headline, claim, snippet, body."""
    parts = [story.get("headline", ""), story.get("why_it_matters", ""),
             story.get("snippet", ""), story.get("title", "")]
    if brief:
        parts += [brief.get("core_claim", ""), brief.get("angle", "")]
        parts += [str(dp.get("claim", "")) for dp in (brief.get("data_points") or [])]
    return is_boundary_story(*parts)


# --- Shape checking -----------------------------------------------------------------------

def missing_fields(b):
    """Which required fields a boundary block does not carry, in FIELDS order."""
    if not isinstance(b, dict):
        return list(FIELDS)
    return [f for f in FIELDS if not str(b.get(f) or "").strip()]


def is_complete(b):
    return not missing_fields(b)


def _norm(s):
    """Compare on visible characters only.

    Advisories are copied out of HTML, so the same string differs by a non-breaking space, a
    typographic quote, or a line wrap between the source page and the brief. None of those
    are paraphrase, and treating them as one would make the check fire on correct work,
    which is how a check gets disabled."""
    s = str(s or "")
    for a, b in ((" ", " "), ("’", "'"), ("‘", "'"),
                 ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def quoted_from(value, texts):
    """Does this field value appear VERBATIM in one of the fetched primary sources?

    Verbatim is the whole point. A field that merely paraphrases the advisory has reproduced
    the failure this module exists to prevent, one layer earlier and less visibly."""
    v = _norm(value)
    if not v:
        return False
    return any(v in _norm(t) for t in texts)


# --- Verification against the primary source ----------------------------------------------

# The fields that must be traceable to the advisory text. user_action is excluded on purpose:
# vendors phrase the instruction across a numbered list or a heading, so requiring a verbatim
# match there would fail honest work. It is still the vendor's instruction and still must not
# be invented, which the advisory link lets a reader check directly. affected and fixed are
# the two that invert, and those are held to the letter.
VERBATIM_FIELDS = ("affected", "fixed")


def check_against_sources(b, source_texts):
    """Deterministic verdict on a boundary block. Returns (ok, [reasons]).

    This is what "the verifier checks the fields against the advisory" means concretely: not
    re-reading prose for directional correctness, which is the judgment that already failed,
    but asserting that the string in the field is the string on the vendor's page."""
    reasons = []
    miss = missing_fields(b)
    if miss:
        reasons.append("boundary fields missing: " + ", ".join(miss))
        return False, reasons

    url = str(b.get("advisory_url") or "").strip()
    if not re.match(r"^https?://", url):
        reasons.append(f"advisory_url is not a URL: {url!r}")

    # Only text fetched FROM the advisory counts. A field quoted out of a news write-up of
    # the advisory is second-hand, and second-hand is exactly where the direction flips.
    primary = [t.get("source_text", "") for t in (source_texts or [])
               if _norm(t.get("url", "")).rstrip("/") == _norm(url).rstrip("/")]
    if not primary:
        reasons.append(f"no fetched text for the advisory itself ({url or 'no url'}); "
                       f"the boundary cannot be confirmed from a primary source")
        return False, reasons

    for f in VERBATIM_FIELDS:
        if not quoted_from(b.get(f), primary):
            reasons.append(f"{f}={str(b.get(f))!r} does not appear verbatim in the advisory "
                           f"at {url}")
    return (not reasons), reasons


# --- Rendering ----------------------------------------------------------------------------

def rows(b):
    """(label, value) pairs in FIELDS order, for a callout rendered ABOVE the prose.

    The requirement is that a reader learns whether they are affected before anything else,
    with unambiguous direction. The obvious way to meet it is to compose a lede sentence from
    the fields, and that is a trap: any template that turns two version strings into English
    has to assert a relation between them ("X is affected, Y is not", "anything below Y"),
    and asserting a relation is exactly the step that inverted the draft in the first place.
    A vendor writes "4.0.1 and earlier" in one advisory and "up to but not including 4.0.1"
    in the next; no template is right for both.

    So nothing is composed. The fields are shown, labeled, in the vendor's own words, at the
    top of the story. That answers the question in the first thing the reader sees and there
    is no sentence to get backwards."""
    if not is_complete(b):
        return []
    return [(FIELD_LABELS[f], str(b[f]).strip()) for f in FIELDS]


def summary(b):
    """One line for a log or a warning."""
    if not isinstance(b, dict):
        return "no boundary block"
    return " | ".join(f"{FIELD_LABELS[f]}: {b.get(f) or '-'}" for f in FIELDS)
