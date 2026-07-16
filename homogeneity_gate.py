"""
Pre-publish homogeneity gate — the anti-templating quality floor for
AI-generated content at scale.

THE PROBLEM IT SOLVES

When you generate content programmatically — 500 city pages, 10,000 game
recaps — the failure that gets a site de-indexed is not thin content, it is
*near-duplicate* content: pages that read like each other because the same model
filled the same template. Search engines collapse them. This gate scores a draft
against the corpus your own engine already published and blocks the ones that are
too similar, BEFORE they go live.

It is deliberately an *intra-corpus* check: near-duplicate of YOUR OTHER PAGES,
not of the open web (that is Copyscape's job). The distinction matters — scaled
self-cannibalization is the failure mode of programmatic SEO, and nobody else
gates it.

Scoring is ``text_similarity.max_similarity`` — deterministic stdlib
shingle-Jaccard behind a distinctive-keyword pre-filter. No ML, no network, no
database. YOU supply the corpus (see ``evaluate``); the gate never queries
anything, so it drops into a Django ``pre_save`` / publish pipeline, a Celery
task, a CLI, or a plain script identically.

THE ARMING CONTRACT — why it ships INERT

A similarity threshold you have not calibrated against your own content is a
number you made up, and enforcing a made-up threshold will silently cap your
throughput or drop good pages. So the gate ships in SHADOW mode:

  * ``enforce=False`` (default): the gate computes and returns the score and a
    ``would_block`` flag, but ALWAYS passes. You run it live, collect the score
    distribution, and pick a real threshold from data.
  * ``threshold_is_calibrated()`` is False while the threshold sits at its
    provisional default. Wire this into your arming precondition so nobody flips
    ``enforce=True`` before the threshold means anything. (This gate does not
    enforce that coupling for you — it exposes the signal so you can.)
  * Only with ``enforce=True`` does a block actually hold a draft — and only then
    is the fail-closed contract active: a *crashed* gate holds the draft for
    review rather than letting it auto-publish. In shadow mode a crash records
    the error and passes, because a measurement tool must never drop content.

On a brand-new engine the corpus is empty, so the gate is a safe no-op until
content accumulates. Pure stdlib; no dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

import text_similarity as ts

# Provisional default. It is intentionally a round guess: leaving the threshold
# here is what threshold_is_calibrated() reads as "not yet calibrated".
PROVISIONAL_THRESHOLD = 0.55

FAILCLOSED_REASON_PREFIX = "fail-closed"


@dataclass
class GateResult:
    """Outcome of the gate for one candidate document."""
    passed: bool
    score: float = 0.0
    match_ref: Optional[str] = None
    corpus_size_compared: int = 0
    failed_closed: bool = False
    would_block: bool = False   # shadow mode: over threshold but not enforced
    reason: str = ""


@dataclass
class HomogeneityGate:
    """A configured gate. Construct once with your policy, call ``evaluate`` per
    candidate with the corpus you want it compared against.

    Every knob is explicit — nothing is read from a global. In Django, build this
    from ``settings`` at call time; the README shows the wiring.
    """
    threshold: float = PROVISIONAL_THRESHOLD
    enforce: bool = False
    shingle_k: int = ts.DEFAULT_SHINGLE_K
    prefilter_stopwords: frozenset = field(default_factory=frozenset)
    prefilter_min_overlap: int = ts.DEFAULT_PREFILTER_MIN_OVERLAP
    # What "uncalibrated" means. Overridable so a caller with a different
    # provisional value still gets a meaningful calibration signal.
    provisional_threshold: float = PROVISIONAL_THRESHOLD

    def threshold_is_calibrated(self) -> bool:
        """True once the threshold has moved off its provisional default. Gate
        arming should refuse while this is False."""
        return self.threshold != self.provisional_threshold

    def evaluate(
        self,
        candidate_text: str,
        corpus: Sequence[tuple[str, str]],
    ) -> GateResult:
        """Score ``candidate_text`` against ``corpus`` and decide pass/block.

        ``corpus`` is ``[(ref, text), ...]`` — YOU supply it (a Django queryset's
        rows, a list of files, whatever). ``ref`` is any identifier you want back
        in ``match_ref`` to point at the offending near-duplicate.

        NEVER raises. In ENFORCE mode any internal error fails closed (blocks,
        held for review). In SHADOW mode the gate only measures — it records the
        score and a ``would_block`` flag but always passes, so an uncalibrated
        threshold can neither cap throughput nor drop content.
        """
        try:
            corpus_texts = [t for _, t in corpus]
            m = ts.max_similarity(
                candidate_text,
                corpus_texts,
                k=self.shingle_k,
                prefilter_min_overlap=self.prefilter_min_overlap,
                prefilter_stopwords=self.prefilter_stopwords,
            )
        except Exception as exc:  # noqa: BLE001 — the gate must never raise
            if self.enforce:
                return GateResult(
                    passed=False,
                    failed_closed=True,
                    reason=f"{FAILCLOSED_REASON_PREFIX}: scoring error: {exc}",
                )
            return GateResult(
                passed=True,
                reason=f"shadow: scoring error (not blocked): {exc}",
            )

        score = round(m.score, 4)
        over = m.best_index is not None and m.score >= self.threshold
        result = GateResult(
            passed=True,
            score=score,
            corpus_size_compared=m.num_compared,
        )
        if not over:
            return result

        match_ref = corpus[m.best_index][0]
        detail = (
            f"similarity {score:.3f} >= threshold {self.threshold:.3f} "
            f"(match={match_ref})"
        )
        if self.enforce:
            result.passed = False
            result.match_ref = match_ref
            result.reason = detail
        else:
            result.would_block = True
            result.match_ref = None  # shadow: nothing was actually blocked
            result.reason = f"shadow: WOULD-BLOCK — {detail}"
        return result


@dataclass
class SignalRecord:
    """The minimum a persisted gate outcome must expose for ``gate_signal`` to
    summarize it. Map your own stored rows onto this (or pass GateResults plus a
    ``blocked`` flag)."""
    scored: bool           # did the gate run and produce a score?
    compared: int          # corpus docs actually shingle-compared
    blocked: bool          # was this draft HELD by the gate?
    failed_closed: bool    # was the block a fail-closed (gate error), not a hit?
    still_held: bool       # is it STILL held now (not yet cleared by a human)?


def gate_signal(records: Iterable[SignalRecord]) -> dict:
    """Roll a batch of persisted gate outcomes into an observability summary.

    Pure function — no clock, no DB. The caller decides the window (pass only the
    records inside it) EXCEPT for ``review_queue_depth``, which is intentionally
    all-time: a held draft stays held until a human clears it, so an undrained
    review queue must stay loud no matter how old. A windowed queue-depth would
    quietly report zero the day after a block, which is the exact blind spot this
    number exists to prevent.
    """
    recs = list(records)
    scored = sum(1 for r in recs if r.scored)
    with_comparisons = sum(1 for r in recs if r.scored and r.compared > 0)
    blocked = sum(1 for r in recs if r.blocked)
    fail_closed = sum(1 for r in recs if r.blocked and r.failed_closed)
    review_queue_depth = sum(1 for r in recs if r.still_held)

    denom = scored or 1
    return {
        "scored": scored,
        "with_comparisons": with_comparisons,
        "blocked": blocked,
        "block_rate": round(blocked / denom, 4),
        "fail_closed": fail_closed,
        "review_queue_depth": review_queue_depth,
    }
