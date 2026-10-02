"""
Domain-agnostic text-similarity primitive.

Deterministic, pure-stdlib similarity. Written with NO domain coupling so it can
back any near-duplicate check. Two moving parts:

  * ``shingle_jaccard(a, b, k=...)``: Jaccard overlap of k-word shingles. This
    is the SCORING function. Verbatim / near-verbatim reuse scores high; text
    about different subjects scores near zero. Identical == 1.0, disjoint == 0.0.

  * ``max_similarity(candidate, corpus, ...)``: scores a candidate against a
    corpus and returns the single best match, but FIRST applies a keyword
    pre-filter so a candidate is only shingle-compared against corpus documents
    that share enough *distinctive* keywords (or, via the template rescue,
    most of their vocabulary). It still reads every document, so the scan stays
    linear; what it skips is the shingle comparison for documents that cannot
    be near-duplicates.

Why a *distinctive*-keyword pre-filter and not a bare ">= 1 shared keyword" one:
text in a single domain shares a heavy generic vocabulary (a sports recap corpus
shares "quarterback", "touchdown", "defeated", "championship"), so a naive
shared-keyword pre-filter degenerates to "compare against everything". Callers
pass ``prefilter_stopwords`` (e.g. a domain-vocabulary set) so the pre-filter
keys on the tokens that actually distinguish one document from another: proper
nouns, places, numbers. See ``tests/`` for the realistic-prose pre-filter case.

The trap: if the stop word list also strips the TEMPLATE's own words, two
find-and-replace pages share no distinctive keyword (only the swapped names
remain) and a keyword-only filter would never compare them. The template rescue
keeps any document whose keyword set overlaps the candidate's by
``prefilter_rescue_ratio`` or more, so a stop word list no longer hides a page
that reuses most of another page's vocabulary.

SCALE NOTE: this is an exact O(n) shingle compare behind a keyword block. At
corpus sizes where that stops being cheap, the next step is MinHash + LSH (e.g.
``datasketch``) for approximate near-duplicate blocking. This module
deliberately does NOT pull that dependency in: stdlib only, deterministic, and
easy to reason about.
"""
from __future__ import annotations

import html
import re
from typing import Iterable, NamedTuple, Optional, Sequence

# --- tuning defaults --------------------------------------------------------
DEFAULT_SHINGLE_K = 5
# Minimum count of shared *distinctive* keywords for a corpus doc to survive the
# pre-filter and get shingle-scored. 2 keeps genuine near-dups (which share many
# distinctive tokens) while pruning unrelated docs (which share ~0-1).
DEFAULT_PREFILTER_MIN_OVERLAP = 2
# Template rescue. A corpus doc that failed the distinctive-keyword test is
# still scored if its keyword set (generic stop words removed, caller stop words
# KEPT) overlaps the candidate's by at least this Jaccard ratio. Find-and-replace
# templated pages share almost their whole vocabulary, so they clear this even
# when the caller's stop word list has stripped every template word. Unrelated
# same-domain prose shares far less. The rescue can only ADD comparisons, never
# change a score, so its worst case is lost speed, not a missed duplicate.
DEFAULT_PREFILTER_RESCUE_RATIO = 0.5

# Generic English stop words stripped before keyword extraction. This is NOT a
# domain vocabulary. Domain stop words (e.g. football terms) are passed in by
# the caller via ``prefilter_stopwords`` so this module stays domain-agnostic.
STOP_WORDS = frozenset({
    'the', 'a', 'an', 'and', 'or', 'but', 'if', 'of', 'to', 'in', 'on', 'at',
    'for', 'by', 'with', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'it', 'its', 'this', 'that', 'these', 'those', 'they', 'them',
    'their', 'he', 'she', 'his', 'her', 'him', 'we', 'our', 'you', 'your',
    'i', 'my', 'me', 'not', 'no', 'so', 'than', 'then', 'up', 'out', 'over',
    'into', 'about', 'after', 'before', 'during', 'while', 'when', 'where',
    'which', 'who', 'whom', 'what', 'how', 'all', 'any', 'both', 'each', 'more',
    'most', 'other', 'some', 'such', 'only', 'own', 'same', 'too', 'very', 'can',
    'will', 'just', 'had', 'has', 'have', 'do', 'does', 'did', 'would', 'could',
    'should', 'there', 'here', 'also',
})

_TAG_RE = re.compile(r'<[^>]+>')
# Markup whose text is never visible page content: scripts, styles, comments.
_INVISIBLE_RE = re.compile(
    r'<!--.*?-->|<(script|style|noscript|template)\b[^>]*>.*?</\1\s*>',
    re.IGNORECASE | re.DOTALL,
)
_NON_WORD_RE = re.compile(r'[^\w\s]')
_WS_RE = re.compile(r'\s+')


class MaxSimilarity(NamedTuple):
    """Result of ``max_similarity``.

    Tuple-compatible ``(score, best_index)`` for simple callers, plus
    ``num_compared`` for observability (the gate reports it as
    ``corpus_size_compared``).
    """
    score: float
    best_index: Optional[int]
    num_compared: int


def _element_re(tag: str) -> re.Pattern:
    return re.compile(
        rf'<{re.escape(tag)}\b[^>]*>.*?</{re.escape(tag)}\s*>',
        re.IGNORECASE | re.DOTALL,
    )


def normalize_text(text: str, *, ignore_tags: Iterable[str] = ()) -> str:
    """Lowercase, strip HTML + punctuation, collapse whitespace.

    Drops text that is never visible content (``<script>``, ``<style>``,
    ``<noscript>``, ``<template>``, HTML comments) and decodes entities, so an
    analytics snippet or ``&amp;`` does not become shingles. ``ignore_tags``
    removes whole elements by tag name, e.g. ``("header", "nav", "footer")`` to
    keep site chrome that every page shares out of the score.

    Pure-stdlib (regex, not bs4) so the primitive has zero heavy dependencies.
    Callers that already have plain text lose nothing.
    """
    if not text:
        return ''
    t = _INVISIBLE_RE.sub(' ', text)
    for tag in ignore_tags:
        t = _element_re(tag).sub(' ', t)
    t = _TAG_RE.sub(' ', t)
    t = html.unescape(t)
    t = t.lower()
    t = _NON_WORD_RE.sub(' ', t)
    t = _WS_RE.sub(' ', t).strip()
    return t


def tokenize(text: str, *, ignore_tags: Iterable[str] = ()) -> list[str]:
    """Normalized word list (order preserved, needed for shingles)."""
    norm = normalize_text(text, ignore_tags=ignore_tags)
    return norm.split() if norm else []


def keyword_set(
    text: str,
    *,
    extra_stopwords: Iterable[str] = (),
    ignore_tags: Iterable[str] = (),
) -> set[str]:
    """Distinctive-token set: normalized words minus generic + extra stop words.

    Length-1 tokens are dropped (single letters carry no signal). ``extra_stopwords``
    lets a caller remove a domain vocabulary so the remaining tokens are the ones
    that distinguish documents (proper nouns, scores, places).
    """
    extra = {w.lower() for w in extra_stopwords}
    out: set[str] = set()
    for w in tokenize(text, ignore_tags=ignore_tags):
        if len(w) < 2:
            continue
        if w in STOP_WORDS or w in extra:
            continue
        out.add(w)
    return out


def _shingles(tokens: Sequence[str], k: int) -> set[tuple[str, ...]]:
    """Set of k-word shingles. Texts shorter than k collapse to one shingle so
    short strings still compare meaningfully (identical short strings -> 1.0)."""
    n = len(tokens)
    if n == 0:
        return set()
    if n < k:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + k]) for i in range(n - k + 1)}


def shingle_jaccard(
    a: str,
    b: str,
    k: int = DEFAULT_SHINGLE_K,
    *,
    ignore_tags: Iterable[str] = (),
) -> float:
    """Jaccard similarity of the two texts' k-word shingle sets.

    Deterministic. Identical text -> 1.0; texts with no shared k-gram -> 0.0.
    """
    sa = _shingles(tokenize(a, ignore_tags=ignore_tags), k)
    sb = _shingles(tokenize(b, ignore_tags=ignore_tags), k)
    if not sa and not sb:
        return 1.0  # two empties are trivially identical
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _rescued(a: set[str], b: set[str], ratio: Optional[float]) -> bool:
    """Template rescue: True when two keyword sets overlap by >= ``ratio``."""
    if ratio is None or not a or not b:
        return False
    return len(a & b) / len(a | b) >= ratio


def max_similarity(
    candidate_text: str,
    corpus_texts: Sequence[str],
    *,
    k: int = DEFAULT_SHINGLE_K,
    prefilter_min_overlap: int = DEFAULT_PREFILTER_MIN_OVERLAP,
    prefilter_stopwords: Iterable[str] = (),
    prefilter_rescue_ratio: Optional[float] = DEFAULT_PREFILTER_RESCUE_RATIO,
    ignore_tags: Iterable[str] = (),
) -> MaxSimilarity:
    """Best shingle-Jaccard of ``candidate_text`` against ``corpus_texts``.

    Applies the distinctive-keyword pre-filter first: a corpus document is only
    shingle-scored if it shares at least ``prefilter_min_overlap`` distinctive
    keywords with the candidate, OR its full keyword set (caller stop words kept)
    overlaps the candidate's by a Jaccard ratio of at least
    ``prefilter_rescue_ratio`` (the template rescue; ``None`` disables it).
    ``num_compared`` reports how many documents cleared the pre-filter.
    ``prefilter_min_overlap=0`` turns the pre-filter off (compare everything).

    Returns ``(score=0.0, best_index=None, num_compared=0)`` for an empty corpus.
    """
    if not corpus_texts:
        return MaxSimilarity(0.0, None, 0)

    extra = {w.lower() for w in prefilter_stopwords}
    cand_all = keyword_set(candidate_text, ignore_tags=ignore_tags)
    cand_kw = cand_all - extra

    best_score = 0.0
    best_index: Optional[int] = None
    num_compared = 0
    for idx, doc in enumerate(corpus_texts):
        doc_all = keyword_set(doc, ignore_tags=ignore_tags)
        doc_kw = doc_all - extra
        # Pre-filter: skip docs that share too few distinctive keywords. An empty
        # candidate keyword set (all-generic prose) can't distinctively match
        # anything, so it only clears via the template rescue below; we do NOT
        # fall back to comparing everything.
        if len(cand_kw & doc_kw) < prefilter_min_overlap:
            if not _rescued(cand_all, doc_all, prefilter_rescue_ratio):
                continue
        num_compared += 1
        score = shingle_jaccard(candidate_text, doc, k, ignore_tags=ignore_tags)
        if score > best_score:
            best_score = score
            best_index = idx

    return MaxSimilarity(best_score, best_index, num_compared)
