"""V3 v1 gate — regex-based claim extractor (Day 2a).

Pure function. Not wired into streaming.py yet — just a callable for
measuring compliance on captured prose + assert lists.

Usage:
    from server.claim_gate import extract_and_tag
    result = extract_and_tag(prose, asserts)

Heuristics (cheap and obvious; Day 3 upgrades to Haiku-based matcher):

  - Sentence split on . ! ? followed by whitespace or end-of-string.
  - A sentence is a CLAIM CANDIDATE iff:
      * it contains a digit, OR a quoted string (", ', `), OR a capitalized
        word that is not sentence-initial (proper-noun proxy)
      * AND it is not a question (ends with ?)
      * AND it is not already wrapped in [speculation] or [unverified]
      * AND it is not purely procedural (starts with "I'll", "I will",
        "Let me", "Now I", "Next ")
  - A claim is GROUNDED iff it matches any assert.text via bidirectional
    lowercase substring containment (claim in assert OR assert in claim).
  - Unmatched claims are UNVERIFIED; tagged_prose wraps them in
    [unverified]...[/unverified].
  - Sentences already wrapped in [speculation] pass through untouched.

Known failure modes (flagged, not fixed here):
  - Capitalized word heuristic catches "Monday" as proper noun (proper-ish).
  - Substring match is lossy: "Mars orbits the Sun" vs assert "Mars orbits
    the Sun (revised)" matches via `in`, good. "The server is at PID 61964"
    vs assert "dev server PID is 61964" matches via digit-string overlap
    in the longer direction, marginal.
  - Compound sentences with both a grounded and a speculative clause are
    treated as one unit.
"""
from __future__ import annotations

import re
from typing import Iterable


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_DIGIT_RE = re.compile(r"\d")
# Note: single-quote excluded on purpose — it matches apostrophes in
# contractions ("don't", "it's") and would force those sentences through
# the factual-claim path. Double quotes and backticks are enough signal.
_QUOTE_RE = re.compile(r'["`]')
_PROPER_NOUN_RE = re.compile(r"(?<!^)(?<!\. )\b[A-Z][a-zA-Z]{2,}")
_SPEC_OPEN = "[speculation]"
_SPEC_CLOSE = "[/speculation]"
_UNV_OPEN = "[unverified]"
_UNV_CLOSE = "[/unverified]"

_PROCEDURAL_PREFIXES = (
    "i'll", "i will", "let me", "now i", "next ", "i'm going to",
    "i am going to", "first,", "then,", "finally,",
)


def _is_question(s: str) -> bool:
    return s.rstrip().endswith("?")


def _is_speculation_wrapped(s: str) -> bool:
    stripped = s.strip()
    return stripped.startswith(_SPEC_OPEN) and _SPEC_CLOSE in stripped


def _is_unverified_wrapped(s: str) -> bool:
    stripped = s.strip()
    return stripped.startswith(_UNV_OPEN) and _UNV_CLOSE in stripped


def _is_procedural(s: str) -> bool:
    low = s.strip().lower()
    return any(low.startswith(pfx) for pfx in _PROCEDURAL_PREFIXES)


def _has_factual_signal(s: str) -> bool:
    if _DIGIT_RE.search(s):
        return True
    if _QUOTE_RE.search(s):
        return True
    if _PROPER_NOUN_RE.search(s):
        return True
    return False


def _sentences(prose: str) -> list[str]:
    # Preserve trailing punctuation in each sentence.
    parts = _SENTENCE_RE.split(prose.strip())
    return [p for p in (s.strip() for s in parts) if p]


def _grounded_by_assert(sentence: str, assert_texts: Iterable[str]) -> bool:
    low_s = sentence.lower()
    for at in assert_texts:
        low_a = at.lower().strip()
        if not low_a:
            continue
        if low_a in low_s or low_s in low_a:
            return True
    return False


def extract_and_tag(prose: str, asserts: list[dict]) -> dict:
    """Classify each sentence of `prose` against the turn's `asserts`.

    Args:
        prose: assistant's output text
        asserts: list of dicts each with at least a 'text' field (the
                 arguments the model passed to claim_assert this turn)

    Returns:
        {
          "tagged_prose": prose with [unverified]...[/unverified] wrapping
                          around factual claims the model did not assert,
          "extracted_claims": [sentence, ...] — all factual-claim candidates
          "grounded":    [sentence, ...] — subset that matched an assert
          "unverified":  [sentence, ...] — subset without an assert match
          "speculation": [sentence, ...] — sentences already [speculation]-wrapped
          "tag_rate":    grounded / (grounded + unverified), 0.0 if none
        }
    """
    assert_texts = [a.get("text", "") for a in asserts]
    sents = _sentences(prose)

    extracted: list[str] = []
    grounded: list[str] = []
    unverified: list[str] = []
    speculation: list[str] = []
    out_parts: list[str] = []

    for s in sents:
        if _is_speculation_wrapped(s):
            speculation.append(s)
            out_parts.append(s)
            continue
        if _is_unverified_wrapped(s):
            # Already self-tagged by the model — pass through, do not double-wrap.
            out_parts.append(s)
            continue
        if _is_question(s) or _is_procedural(s):
            out_parts.append(s)
            continue
        if not _has_factual_signal(s):
            out_parts.append(s)
            continue

        # Factual-claim candidate.
        extracted.append(s)
        if _grounded_by_assert(s, assert_texts):
            grounded.append(s)
            out_parts.append(s)
        else:
            unverified.append(s)
            out_parts.append(f"{_UNV_OPEN}{s}{_UNV_CLOSE}")

    denom = len(grounded) + len(unverified)
    tag_rate = (len(grounded) / denom) if denom > 0 else 0.0

    return {
        "tagged_prose": " ".join(out_parts),
        "extracted_claims": extracted,
        "grounded": grounded,
        "unverified": unverified,
        "speculation": speculation,
        "tag_rate": tag_rate,
    }
