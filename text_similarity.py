"""
Domain-agnostic text-similarity primitive.

Deterministic, pure-stdlib similarity. Written with NO domain coupling so it can
back any near-duplicate check. Two moving parts:

  * ``shingle_jaccard(a, b, k=...)`` — Jaccard overlap of k-word shingles. This
    is the SCORING function. Verbatim / near-verbatim reuse scores high; text
    about different subjects scores near zero. Identical == 1.0, disjoint == 0.0.

  * ``max_similarity(candidate, corpus, ...)`` — scores a candidate against a
    corpus and returns the single best match, but FIRST applies a keyword
    pre-filter so a candidate is only shingle-compared against corpus documents
    that share enough *distinctive* keywords. Without a pre-filter this is
    O(candidate x whole-corpus) on every call.

Why a *distinctive*-keyword pre-filter and not a bare ">= 1 shared keyword" one:
text in a single domain shares a heavy generic vocabulary (a sports recap corpus
shares "quarterback", "touchdown", "defeated", "championship"), so a naive
shared-keyword pre-filter degenerates to "compare against everything". Callers
pass ``prefilter_stopwords`` (e.g. a domain-vocabulary set) so the pre-filter
keys on the tokens that actually distinguish one document from another — proper
nouns, places, numbers. See ``tests/`` for the realistic-prose pre-filter case.

SCALE NOTE: this is an exact O(n) shingle compare behind a keyword block. At
corpus sizes where that stops being cheap, the next step is MinHash + LSH (e.g.
``datasketch``) for approximate near-duplicate blocking. This module
deliberately does NOT pull that dependency in — stdlib only, deterministic, and
easy to reason about.
"""
from __future__ import annotations

import re
from typing import Iterable, NamedTuple, Optional, Sequence

# --- tuning defaults --------------------------------------------------------
DEFAULT_SHINGLE_K = 5
# Minimum count of shared *distinctive* keywords for a corpus doc to survive the
# pre-filter and get shingle-scored. 2 keeps genuine near-dups (which share many
# distinctive tokens) while pruning unrelated docs (which share ~0-1).
DEFAULT_PREFILTER_MIN_OVERLAP = 2

# Generic English stop words stripped before keyword extraction. This is NOT a
# domain vocabulary — domain stop words (e.g. football terms) are passed in by
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
_NON_WORD_RE = re.compile(r'[^\w\s]')
_WS_RE = re.compile(r'\s+')


class MaxSimilarity(NamedTuple):
    """Result of ``max_similarity``.

    Tuple-compatible ``(score, best_index)`` for the simple callers described in
    the plan, plus ``num_compared`` for observability (persisted as
    ``corpus_size_compared``).
    """
    score: float
    best_index: Optional[int]
    num_compared: int


def normalize_text(text: str) -> str:
    """Lowercase, strip HTML tags + punctuation, collapse whitespace.

    Pure-stdlib (regex tag strip, not bs4) so the primitive has zero heavy
    dependencies. Callers that already have plain text lose nothing.
    """
    if not text:
        return ''
    t = _TAG_RE.sub(' ', text)
    t = t.lower()
    t = _NON_WORD_RE.sub(' ', t)
    t = _WS_RE.sub(' ', t).strip()
    return t


def tokenize(text: str) -> list[str]:
    """Normalized word list (order preserved — needed for shingles)."""
    norm = normalize_text(text)
    return norm.split() if norm else []


def keyword_set(text: str, *, extra_stopwords: Iterable[str] = ()) -> set[str]:
    """Distinctive-token set: normalized words minus generic + extra stop words.

    Length-1 tokens are dropped (single letters carry no signal). ``extra_stopwords``
    lets a caller remove a domain vocabulary so the remaining tokens are the ones
    that distinguish documents (proper nouns, scores, places).
    """
    extra = {w.lower() for w in extra_stopwords}
    out: set[str] = set()
    for w in tokenize(text):
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


def shingle_jaccard(a: str, b: str, k: int = DEFAULT_SHINGLE_K) -> float:
    """Jaccard similarity of the two texts' k-word shingle sets.

    Deterministic. Identical text -> 1.0; texts with no shared k-gram -> 0.0.
    """
    sa = _shingles(tokenize(a), k)
    sb = _shingles(tokenize(b), k)
    if not sa and not sb:
        return 1.0  # two empties are trivially identical
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def max_similarity(
    candidate_text: str,
    corpus_texts: Sequence[str],
    *,
    k: int = DEFAULT_SHINGLE_K,
    prefilter_min_overlap: int = DEFAULT_PREFILTER_MIN_OVERLAP,
    prefilter_stopwords: Iterable[str] = (),
) -> MaxSimilarity:
    """Best shingle-Jaccard of ``candidate_text`` against ``corpus_texts``.

    Applies the distinctive-keyword pre-filter first: a corpus document is only
    shingle-scored if it shares at least ``prefilter_min_overlap`` distinctive
    keywords with the candidate. ``num_compared`` reports how many documents
    actually cleared the pre-filter (the whole point of condition 10 — this must
    be materially smaller than ``len(corpus_texts)`` on shared-vocab prose).

    Returns ``(score=0.0, best_index=None, num_compared=0)`` for an empty corpus.
    """
    if not corpus_texts:
        return MaxSimilarity(0.0, None, 0)

    cand_kw = keyword_set(candidate_text, extra_stopwords=prefilter_stopwords)

    best_score = 0.0
    best_index: Optional[int] = None
    num_compared = 0
    for idx, doc in enumerate(corpus_texts):
        doc_kw = keyword_set(doc, extra_stopwords=prefilter_stopwords)
        # Pre-filter: skip docs that share too few distinctive keywords. An empty
        # candidate keyword set (all-generic prose) can't distinctively match
        # anything, so nothing clears the filter — we do NOT fall back to
        # comparing everything.
        if len(cand_kw & doc_kw) < prefilter_min_overlap:
            continue
        num_compared += 1
        score = shingle_jaccard(candidate_text, doc, k)
        if score > best_score:
            best_score = score
            best_index = idx

    return MaxSimilarity(best_score, best_index, num_compared)
