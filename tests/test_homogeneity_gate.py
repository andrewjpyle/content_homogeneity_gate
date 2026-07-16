"""Tests for the homogeneity gate.

The decision matrix — block / pass / shadow / fail-closed / calibration — ported
to the corpus-supplied API. Stdlib unittest, no dependencies.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from homogeneity_gate import (  # noqa: E402
    HomogeneityGate, GateResult, SignalRecord, gate_signal, PROVISIONAL_THRESHOLD,
)
from sports_stopwords import SPORTS_STOPWORDS  # noqa: E402

BODY_A = ("The Bills defeated the Dolphins 32 to 29 behind Josh Allen four scoring drives "
          "at Highmark Stadium in a divisional showdown that came down to a late field goal.")
NEAR_DUP = ("The Bills defeated the Dolphins 32 to 29 behind Josh Allen four scoring drives "
            "at Highmark Stadium in a divisional showdown that came down to a late field goal today.")
DISTINCT = ("The Chiefs edged the Ravens 27 to 24 as Patrick Mahomes engineered a closing march "
            "in Kansas City to clinch the division on a snowy afternoon.")


def gate(**kw) -> HomogeneityGate:
    kw.setdefault("prefilter_stopwords", SPORTS_STOPWORDS)
    return HomogeneityGate(**kw)


class EmptyAndTrivial(unittest.TestCase):
    def test_empty_corpus_passes(self):
        r = gate(enforce=True, threshold=0.4).evaluate(BODY_A, [])
        self.assertTrue(r.passed)
        self.assertEqual(r.corpus_size_compared, 0)


class DecisionMatrix(unittest.TestCase):
    def test_near_duplicate_blocks_when_enforcing(self):
        r = gate(enforce=True, threshold=0.4).evaluate(NEAR_DUP, [("recap-prior", BODY_A)])
        self.assertFalse(r.passed)
        self.assertEqual(r.match_ref, "recap-prior")
        self.assertGreaterEqual(r.score, 0.4)
        self.assertGreaterEqual(r.corpus_size_compared, 1)

    def test_distinct_document_passes_when_enforcing(self):
        r = gate(enforce=True, threshold=0.4).evaluate(DISTINCT, [("recap-prior", BODY_A)])
        self.assertTrue(r.passed)  # different teams/players → pre-filter prunes, low score

    def test_shadow_mode_measures_but_never_blocks(self):
        r = gate(enforce=False, threshold=0.4).evaluate(NEAR_DUP, [("recap-prior", BODY_A)])
        self.assertTrue(r.passed)          # shadow NEVER blocks
        self.assertTrue(r.would_block)     # but records that it would have
        self.assertGreaterEqual(r.score, 0.4)
        self.assertIsNone(r.match_ref)     # nothing was actually blocked

    def test_below_threshold_passes_silently(self):
        r = gate(enforce=True, threshold=0.99).evaluate(NEAR_DUP, [("recap-prior", BODY_A)])
        self.assertTrue(r.passed)
        self.assertFalse(r.would_block)
        self.assertEqual(r.match_ref, None)


class FailClosed(unittest.TestCase):
    """A gate that crashes must HOLD when enforcing (fail closed) and PASS when
    only measuring (a monitor must never drop content). We force a crash by
    handing the scorer a corpus whose 'text' explodes on read."""

    class _Boom:
        def __iter__(self):  # consumed by the list comprehension in evaluate()
            raise RuntimeError("boom")

    def test_fail_closed_when_enforcing(self):
        # corpus is not a real sequence of tuples → the comprehension raises.
        r = gate(enforce=True).evaluate(BODY_A, self._Boom())
        self.assertFalse(r.passed)
        self.assertTrue(r.failed_closed)
        self.assertTrue(r.reason.startswith("fail-closed"))

    def test_shadow_never_fails_closed(self):
        r = gate(enforce=False).evaluate(BODY_A, self._Boom())
        self.assertTrue(r.passed)               # shadow never blocks, even on error
        self.assertFalse(r.failed_closed)

    def test_evaluate_never_raises(self):
        # The public contract: no input makes evaluate() raise.
        for enforce in (True, False):
            try:
                gate(enforce=enforce).evaluate(BODY_A, self._Boom())
            except Exception as exc:  # noqa: BLE001
                self.fail(f"evaluate raised {exc!r} (enforce={enforce})")


class Calibration(unittest.TestCase):
    def test_provisional_threshold_reads_as_uncalibrated(self):
        self.assertFalse(HomogeneityGate(threshold=PROVISIONAL_THRESHOLD).threshold_is_calibrated())

    def test_moved_threshold_reads_as_calibrated(self):
        self.assertTrue(HomogeneityGate(threshold=0.42).threshold_is_calibrated())

    def test_custom_provisional_value_is_honored(self):
        g = HomogeneityGate(threshold=0.7, provisional_threshold=0.7)
        self.assertFalse(g.threshold_is_calibrated())


class Observability(unittest.TestCase):
    def _rec(self, **kw) -> SignalRecord:
        base = dict(scored=True, compared=1, blocked=False, failed_closed=False, still_held=False)
        base.update(kw)
        return SignalRecord(**base)

    def test_block_rate_and_counts(self):
        recs = [
            self._rec(),                                   # scored, passed
            self._rec(blocked=True, still_held=True),      # blocked, still held
            self._rec(blocked=True, failed_closed=True, still_held=False),  # fail-closed, cleared
            self._rec(compared=0),                         # scored but nothing compared
        ]
        s = gate_signal(recs)
        self.assertEqual(s["scored"], 4)
        self.assertEqual(s["with_comparisons"], 3)
        self.assertEqual(s["blocked"], 2)
        self.assertEqual(s["block_rate"], round(2 / 4, 4))
        self.assertEqual(s["fail_closed"], 1)

    def test_review_queue_depth_is_all_time_not_windowed(self):
        """The one number that must NOT respect the window: a held draft stays a
        problem until a human clears it. Two held items, both counted, even though
        neither was 'blocked in this window'."""
        recs = [
            self._rec(scored=False, blocked=False, still_held=True),
            self._rec(scored=False, blocked=False, still_held=True),
        ]
        s = gate_signal(recs)
        self.assertEqual(s["review_queue_depth"], 2)
        self.assertEqual(s["blocked"], 0)  # not blocked in-window, but still held

    def test_empty_batch_does_not_divide_by_zero(self):
        s = gate_signal([])
        self.assertEqual(s["block_rate"], 0.0)
        self.assertEqual(s["scored"], 0)


if __name__ == "__main__":
    unittest.main()
